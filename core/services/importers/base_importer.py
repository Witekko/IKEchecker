import pandas as pd
import logging
from abc import ABC, abstractmethod
from core.models import Transaction, Asset
from core.config import SUFFIX_MAP
from core.services.market import fetch_asset_metadata
from .parsers import XtbParser, OtherBrokerParser

logger = logging.getLogger('core')

class BaseImporter(ABC):
    """Abstract base class for transaction importers."""

    def __init__(self, file, portfolio):
        self.file = file
        self.portfolio = portfolio
        self.stats = {'added': 0, 'updated': 0, 'skipped': 0, 'new_assets': 0}
        self.asset_cache = {}
        self.parsers = [XtbParser(), OtherBrokerParser()]

    @abstractmethod
    def load_dataframe(self):
        """Load file content into a standardized DataFrame."""
        pass

    def process(self):
        """Main processing loop."""
        df = self.load_dataframe()
        if df is None or df.empty:
            raise ValueError("Empty or invalid file content.")

        # Normalize columns
        df.columns = [str(c).strip() for c in df.columns]
        
        # Select parser
        parser = self._get_parser(df.columns)
        if not parser:
             raise ValueError("Unknown report format. Could not find a matching parser.")

        for _, row in df.iterrows():
            try:
                self._process_row(row, parser)
            except Exception as e:
                logger.warning(f"Skipping row due to error: {e}")
                continue

        return self.stats

    def _get_parser(self, columns):
        for p in self.parsers:
            if p.is_match(columns):
                return p
        return None

    def _process_row(self, row, parser):
        # Parse row using the selected parser
        data = parser.parse_row(row)
        
        if not data.get('xtb_id') or not data.get('date'):
            return

        # Resolve Asset
        asset_obj = self._resolve_asset(data.get('symbol'))

        # UPSERT
        obj, created = Transaction.objects.update_or_create(
            portfolio=self.portfolio,
            xtb_id=data['xtb_id'],
            defaults={
                'asset': asset_obj,
                'date': data['date'],
                'type': data['type'],
                'amount': data['amount'],
                'quantity': data['quantity'],
                'price': data['price'],
                'comment': data['comment']
            }
        )

        if created:
            self.stats['added'] += 1
        else:
            self.stats['updated'] += 1

    def _resolve_asset(self, sym):
        if not sym or sym.lower() == 'nan': return None

        if sym in self.asset_cache:
            return self.asset_cache[sym]

        asset_obj, created = self._get_or_create_asset_smart(sym)
        self.asset_cache[sym] = asset_obj
        if created:
            self.stats['new_assets'] += 1
        return asset_obj

    def _get_or_create_asset_smart(self, xtb_symbol):
        # 1. Search by exact symbol
        existing = Asset.objects.filter(symbol=xtb_symbol).first()
        if existing: return existing, False

        # 2. Search by exact name
        existing_by_name = Asset.objects.filter(name__iexact=xtb_symbol).first()
        if existing_by_name: return existing_by_name, False

        # 3. Create new
        yahoo_ticker = xtb_symbol
        currency = 'PLN'
        name = xtb_symbol
        asset_type = 'STOCK'
        sector = 'OTHER'

        # Guess suffix
        for suffix, rule in SUFFIX_MAP.items():
            if xtb_symbol.endswith(suffix):
                base = xtb_symbol.replace(suffix, '')
                yahoo_suf = rule['yahoo_suffix'] if rule['yahoo_suffix'] is not None else ''
                yahoo_ticker = f"{base}{yahoo_suf}"
                currency = rule['default_currency']
                break
        
        # Fetch metadata
        try:
            meta = fetch_asset_metadata(yahoo_ticker)
            if meta['success']:
                name = meta.get('name', name)
                asset_type = meta.get('asset_type', asset_type)
                sector = meta.get('sector', sector)
                currency = meta.get('currency', currency)
        except:
            pass

        return Asset.objects.create(
            symbol=xtb_symbol,
            yahoo_ticker=yahoo_ticker,
            currency=currency,
            name=name,
            asset_type=asset_type,
            sector=sector
        ), True