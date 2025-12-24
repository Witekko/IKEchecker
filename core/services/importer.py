# core/services/importer.py

import pandas as pd
import re
from ..models import Portfolio, Transaction, Asset
from .config import TICKER_CONFIG


def process_xtb_file(uploaded_file, user):
    try:
        xls = pd.ExcelFile(uploaded_file)
    except Exception as e:
        raise ValueError(f"Excel Error: {e}")

    target_sheet = None
    for sheet in xls.sheet_names:
        if "CASH" in sheet.upper():
            target_sheet = sheet
            break
    if not target_sheet: target_sheet = xls.sheet_names[0]

    # Znajdowanie nagłówka
    df_preview = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=None, nrows=40)
    header_idx = None
    for idx, row in df_preview.iterrows():
        s = " ".join([str(v) for v in row.fillna('').values])
        if "ID" in s and "Type" in s and "Comment" in s:
            header_idx = idx
            break
    if header_idx is None: raise ValueError("Header not found.")

    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=header_idx)
    df.columns = df.columns.str.strip()

    portfolio, _ = Portfolio.objects.get_or_create(user=user, defaults={'name': 'My IKE'})
    stats = {'added': 0, 'skipped': 0}

    for _, row in df.iterrows():
        if pd.isna(row.get('ID')): continue

        xtb_id = str(row['ID'])
        trans_type = _parse_transaction_type(str(row.get('Type', '')))
        quantity = _parse_quantity(trans_type, str(row.get('Comment', '')))

        try:
            date_obj = pd.to_datetime(row['Time'])
        except:
            continue

        amount = float(row['Amount']) if not pd.isna(row['Amount']) else 0.0

        asset_obj = None
        sym = str(row.get('Symbol', ''))

        if sym in TICKER_CONFIG:
            conf = TICKER_CONFIG[sym]
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=sym,
                defaults={'yahoo_ticker': conf['yahoo'], 'currency': conf['currency'], 'name': conf['name']}
            )

        _, created = Transaction.objects.update_or_create(
            xtb_id=xtb_id,
            defaults={
                'portfolio': portfolio, 'asset': asset_obj, 'date': date_obj,
                'type': trans_type, 'amount': amount, 'quantity': quantity,
                'comment': str(row.get('Comment', ''))
            }
        )
        if created:
            stats['added'] += 1
        else:
            stats['skipped'] += 1

    return stats


def _parse_transaction_type(raw_type):
    raw = raw_type.lower().strip()
    if 'stock' in raw and 'purchase' in raw: return 'BUY'
    if 'stock' in raw and 'sale' in raw: return 'SELL'
    if 'close' in raw or 'profit' in raw: return 'SELL'
    if 'deposit' in raw: return 'DEPOSIT'
    if 'withdrawal' in raw: return 'WITHDRAWAL'
    if 'dividend' in raw: return 'DIVIDEND'
    if 'withholding tax' in raw: return 'TAX'
    return 'OTHER'


def _parse_quantity(trans_type, comment):
    if trans_type in ['BUY', 'SELL']:
        match = re.search(r'(BUY|SELL) ([0-9./]+)', comment)
        if match:
            try:
                return float(match.group(2).split('/')[0])
            except:
                pass
    return 0.0