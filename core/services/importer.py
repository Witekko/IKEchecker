# core/services/importer.py

import pandas as pd
import re
import yfinance as yf
from datetime import datetime
from django.utils import timezone
from ..models import Transaction, Asset
from .config import SUFFIX_MAP
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger('core')

class BaseImporter(ABC):
    """Abstract base class for transaction importers."""
    
    def __init__(self, file, portfolio):
        self.file = file
        self.portfolio = portfolio
        self.stats = {'added': 0, 'skipped': 0, 'new_assets': 0}
        self.asset_cache = {}

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

        for _, row in df.iterrows():
            try:
                self._process_row(row)
            except Exception as e:
                logger.warning(f"Skipping row due to error: {e}")
                continue
        
        return self.stats

    def _process_row(self, row):
        if pd.isna(row.get('ID')): return

        xtb_id = str(row['ID'])
        if Transaction.objects.filter(xtb_id=xtb_id).exists():
            self.stats['skipped'] += 1
            return

        trans_type = self._parse_transaction_type(str(row.get('Type', '')))
        quantity = self._parse_quantity(trans_type, str(row.get('Comment', '')))
        date_obj = self._parse_date(row.get('Time'))
        
        if not date_obj: return

        amount = self._parse_amount(row.get('Amount'))
        asset_obj = self._resolve_asset(str(row.get('Symbol', '')))

        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=asset_obj,
            xtb_id=xtb_id,
            date=date_obj,
            type=trans_type,
            amount=amount,
            quantity=quantity,
            comment=str(row.get('Comment', ''))
        )
        self.stats['added'] += 1

    def _parse_date(self, val_time):
        try:
            if pd.isna(val_time) or str(val_time).strip() == '': return None
            dt = pd.to_datetime(val_time)
            if pd.isna(dt): return None
            return timezone.make_aware(dt) if dt.tzinfo is None else dt
        except:
            return None

    def _parse_amount(self, val):
        try:
            if isinstance(val, str):
                val = val.replace(',', '.').replace(' ', '')
            return float(val)
        except:
            return 0.0

    def _resolve_asset(self, sym):
        sym = sym.strip()
        if not sym or sym.lower() == 'nan': return None

        if sym in self.asset_cache:
            return self.asset_cache[sym]

        asset_obj, created = self._get_or_create_asset_smart(sym)
        self.asset_cache[sym] = asset_obj
        if created:
            self.stats['new_assets'] += 1
        return asset_obj

    def _get_or_create_asset_smart(self, xtb_symbol):
        existing = Asset.objects.filter(symbol=xtb_symbol).first()
        if existing: return existing, False

        yahoo_ticker = xtb_symbol
        currency = 'PLN'
        name = xtb_symbol

        found_rule = False
        for suffix, rule in SUFFIX_MAP.items():
            if xtb_symbol.endswith(suffix):
                base = xtb_symbol.replace(suffix, '')
                yahoo_suf = rule['yahoo_suffix'] if rule['yahoo_suffix'] is not None else ''
                yahoo_ticker = f"{base}{yahoo_suf}"
                currency = rule['default_currency']
                found_rule = True
                break

        if found_rule:
            try:
                info = yf.Ticker(yahoo_ticker).info
                if 'currency' in info: currency = info['currency']
                if 'shortName' in info: name = info['shortName']
                elif 'longName' in info: name = info['longName']
            except:
                pass

        return Asset.objects.create(
            symbol=xtb_symbol,
            yahoo_ticker=yahoo_ticker,
            currency=currency,
            name=name
        ), True

    def _parse_transaction_type(self, raw_type):
        raw = raw_type.lower().strip()
        if 'stock' in raw and 'purchase' in raw: return 'BUY'
        if 'stock' in raw and 'sale' in raw: return 'SELL'
        if 'close' in raw or 'profit' in raw: return 'CLOSE'
        if 'deposit' in raw: return 'DEPOSIT'
        if 'withdrawal' in raw: return 'WITHDRAWAL'
        if 'dividend' in raw: return 'DIVIDEND'
        if 'withholding tax' in raw: return 'TAX'
        return 'OTHER'

    def _parse_quantity(self, trans_type, comment):
        if trans_type in ['BUY', 'SELL']:
            match = re.search(r'(BUY|SELL) ([0-9./]+)', comment)
            if match:
                try:
                    val = match.group(2)
                    if '/' in val: val = val.split('/')[0]
                    return float(val)
                except:
                    pass
        return 0.0


class XtbExcelImporter(BaseImporter):
    def load_dataframe(self):
        try:
            xls = pd.ExcelFile(self.file)
        except Exception as e:
            raise ValueError(f"Excel Error: {e}")

        target_sheet = None
        for sheet in xls.sheet_names:
            if "CASH" in sheet.upper():
                target_sheet = sheet
                break
        if not target_sheet: target_sheet = xls.sheet_names[0]

        # Find header
        df_preview = pd.read_excel(self.file, sheet_name=target_sheet, header=None, nrows=40)
        header_idx = self._find_header_row(df_preview)

        if header_idx is None:
            raise ValueError("Nie znaleziono nagłówka (ID, Type, Comment) w pliku Excel.")

        self.file.seek(0)
        return pd.read_excel(self.file, sheet_name=target_sheet, header=header_idx)

    def _find_header_row(self, df):
        for idx, row in df.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            if "ID" in s and "Type" in s and "Comment" in s:
                return idx
        return None


class XtbCsvImporter(BaseImporter):
    def load_dataframe(self):
        attempts = [
            {'encoding': 'utf-16', 'sep': '\t'},
            {'encoding': 'utf-16', 'sep': ';'},
            {'encoding': 'utf-16', 'sep': ','},
            {'encoding': 'utf-8', 'sep': ';'},
            {'encoding': 'utf-8', 'sep': ','},
            {'encoding': 'cp1250', 'sep': ';'}
        ]

        df_raw = None
        for params in attempts:
            try:
                self.file.seek(0)
                temp = pd.read_csv(self.file, encoding=params['encoding'], sep=params['sep'])
                if len(temp.columns) > 1:
                    df_raw = temp
                    break
            except:
                continue

        if df_raw is None:
            raise ValueError("Nie udało się odczytać pliku CSV (błąd kodowania).")

        header_idx = self._find_header_row(df_raw.head(40))

        if header_idx is None:
            s = " ".join([str(c) for c in df_raw.columns])
            if "ID" in s and "Type" in s:
                return df_raw
            else:
                raise ValueError("Nie znaleziono nagłówka w pliku CSV.")
        
        new_header = df_raw.iloc[header_idx]
        df = df_raw[header_idx + 1:].copy()
        df.columns = new_header
        return df

    def _find_header_row(self, df):
        for idx, row in df.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            if "ID" in s and "Type" in s and "Comment" in s:
                return idx
        return None


def process_xtb_file(uploaded_file, portfolio_obj, overwrite_manual=False):
    filename = uploaded_file.name.lower()

    if filename.endswith(('.xlsx', '.xls')):
        importer = XtbExcelImporter(uploaded_file, portfolio_obj)
    elif filename.endswith('.csv'):
        importer = XtbCsvImporter(uploaded_file, portfolio_obj)
    else:
        raise ValueError("Nieobsługiwany format pliku. Użyj .xlsx lub .csv")

    # --- LOGIKA NADPISYWANIA (Checkox) ---
    if overwrite_manual:
        # 1. Wczytaj dane wstępnie, żeby poznać zakres dat
        df = importer.load_dataframe()
        if df is not None and not df.empty:
            # Szukamy kolumny czasu (Time)
            if 'Time' in df.columns:
                try:
                    # Konwersja na daty, ignorując błędy
                    dates = pd.to_datetime(df['Time'], errors='coerce').dropna()
                    if not dates.empty:
                        min_date = dates.min()
                        max_date = dates.max()

                        # Usuwamy transakcje ręczne (MAN-) w tym zakresie dat
                        # Używamy delete() co jest szybkie i skuteczne
                        deleted_count, _ = Transaction.objects.filter(
                            portfolio=portfolio_obj,
                            xtb_id__startswith='MAN-',
                            date__range=(min_date, max_date)
                        ).delete()

                        logger.info(f"Usunięto {deleted_count} ręcznych transakcji kolidujących z importem.")
                except Exception as e:
                    logger.warning(f"Nie udało się określić zakresu dat do czyszczenia manualnego: {e}")

            # Resetujemy wskaźnik pliku, bo load_dataframe go przesunął
            uploaded_file.seek(0)

    return importer.process()