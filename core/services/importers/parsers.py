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
        # Matches if either 'Symbol' (Old) or 'Instrument' (New) is present
        return ('Symbol' in columns or 'Instrument' in columns) and 'Type' in columns

    def parse_row(self, row):
        raw_type = str(row.get('Type', '')).strip()
        comment = str(row.get('Comment', ''))
        
        trans_type = self._map_type(raw_type)
        
        # Handle Symbol/Instrument column difference
        symbol = str(row.get('Instrument') if 'Instrument' in row else row.get('Symbol', '')).strip()

        return {
            'xtb_id': str(int(row['ID'])) if isinstance(row['ID'], (int, float)) else str(row['ID']),
            'date': self._parse_date(row.get('Time')),
            'type': trans_type,
            'amount': self._parse_amount(row.get('Amount')),
            'quantity': self._parse_quantity(trans_type, comment),
            'price': self._parse_price(comment),
            'comment': comment,
            'symbol': symbol
        }

    def _map_type(self, raw):
        raw = raw.lower()
        if 'stock' in raw and 'purchase' in raw: return 'BUY'
        if 'stock' in raw and ('sale' in raw or 'sell' in raw): return 'SELL' # Handles both 'sale' and 'sell'
        if 'close' in raw or 'profit' in raw: return 'CLOSE'
        if 'deposit' in raw: return 'DEPOSIT'
        if 'withdrawal' in raw: return 'WITHDRAWAL'
        if 'divident' in raw or 'dividend' in raw: return 'DIVIDEND' # Handles typo 'divident'
        if 'withholding tax' in raw: return 'TAX'
        if 'fee' in raw: return 'FEE'
        if 'interest' in raw: return 'OTHER'
        return 'OTHER'


class OtherBrokerParser(BaseParser):
    """Placeholder for other brokers."""
    
    def is_match(self, columns):
        return False 

    def parse_row(self, row):
        return {}