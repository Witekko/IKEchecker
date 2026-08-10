import re
import pandas as pd
from django.utils import timezone

class BaseParser:
    """Base class for row parsers."""
    
    def is_match(self, columns):
        """Check if this parser can handle the dataframe based on columns."""
        return False

    def parse_row(self, row):
        """Parse a single row into a standardized dictionary."""
        raise NotImplementedError

    def _parse_amount(self, val):
        try:
            if isinstance(val, str):
                val = val.replace(',', '.').replace(' ', '').replace('\xa0', '')
            return float(val)
        except:
            return 0.0

    def _parse_date(self, val_time):
        try:
            if pd.isna(val_time) or str(val_time).strip() == '': return None
            dt = pd.to_datetime(val_time)
            if pd.isna(dt): return None
            return timezone.make_aware(dt) if dt.tzinfo is None else dt
        except:
            return None

    def _parse_quantity(self, trans_type, comment):
        if trans_type in ['BUY', 'SELL']:
            match = re.search(r'(BUY|SELL)\s+([0-9./]+)', comment, re.IGNORECASE)
            if match:
                try:
                    val = match.group(2)
                    if '/' in val: val = val.split('/')[0]
                    return float(val)
                except:
                    pass
        return 0.0

    def _parse_price(self, comment):
        if '@' in comment:
            match = re.search(r'@\s*([0-9.,]+)', comment)
            if match:
                try:
                    val = match.group(1).replace(',', '.')
                    return float(val)
                except:
                    pass
        return None


class XtbParser(BaseParser):
    """Unified Parser for XTB (Old & New formats)."""
    
    def is_match(self, columns):
        # Matches if either 'Symbol', 'Instrument', or 'Ticker' is present
        return ('Symbol' in columns or 'Instrument' in columns or 'Ticker' in columns) and 'Type' in columns

    def parse_row(self, row):
        raw_type = str(row.get('Type', '')).strip()
        comment = str(row.get('Comment', ''))
        amount = self._parse_amount(row.get('Amount'))
        
        trans_type = self._map_type(raw_type)
        if trans_type == 'OTHER' and 'transfer' in raw_type.lower():
            trans_type = 'DEPOSIT' if amount > 0 else 'WITHDRAWAL'

        # Extract Position ID
        position_id = None
        if 'Position ID' in row and pd.notna(row['Position ID']):
            position_id = str(int(row['Position ID'])) if isinstance(row['Position ID'], (int, float)) else str(row['Position ID']).strip()

        # Extract Category
        category = None
        if 'Category' in row and pd.notna(row['Category']):
            category = str(row['Category']).strip().upper()

        # Resolve symbol prioritizing Ticker -> Symbol -> Instrument
        symbol = None
        name_hint = None
        
        if 'Ticker' in row and pd.notna(row['Ticker']) and str(row['Ticker']).strip() != '':
            symbol = str(row['Ticker']).strip()
            if 'Instrument' in row and pd.notna(row['Instrument']) and str(row['Instrument']).strip() != '':
                name_hint = str(row['Instrument']).strip()
        elif 'Symbol' in row and pd.notna(row['Symbol']) and str(row['Symbol']).strip() != '':
            symbol = str(row['Symbol']).strip()
            if 'Instrument' in row and pd.notna(row['Instrument']) and str(row['Instrument']).strip() != '':
                name_hint = str(row['Instrument']).strip()
        elif 'Instrument' in row and pd.notna(row['Instrument']) and str(row['Instrument']).strip() != '':
            symbol = str(row['Instrument']).strip()

        return {
            'xtb_id': str(int(row['ID'])) if isinstance(row['ID'], (int, float)) else str(row['ID']),
            'position_id': position_id,
            'category': category,
            'date': self._parse_date(row.get('Time')),
            'type': trans_type,
            'amount': amount,
            'quantity': self._parse_quantity(trans_type, comment),
            'price': self._parse_price(comment),
            'comment': comment,
            'symbol': symbol,
            'name_hint': name_hint
        }

    def _map_type(self, raw):
        raw = raw.lower()
        if 'stock' in raw and 'purchase' in raw: return 'BUY'
        if 'stock' in raw and ('sale' in raw or 'sell' in raw): return 'SELL'
        if 'close' in raw or 'profit' in raw: return 'CLOSE'
        if 'tax' in raw: return 'TAX'
        if 'return' in raw or 'withdrawal' in raw: return 'WITHDRAWAL'
        if 'deposit' in raw: return 'DEPOSIT'
        if 'divident' in raw or 'dividend' in raw: return 'DIVIDEND'
        if 'fee' in raw: return 'FEE'
        if 'interest' in raw: return 'OTHER'
        return 'OTHER'


class OtherBrokerParser(BaseParser):
    """Placeholder for other brokers."""
    
    def is_match(self, columns):
        return False 

    def parse_row(self, row):
        return {}