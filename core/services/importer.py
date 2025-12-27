# core/services/importer.py

import pandas as pd
import re
import yfinance as yf
from datetime import datetime
from decimal import Decimal
from django.utils import timezone
from ..models import Portfolio, Transaction, Asset
from .config import SUFFIX_MAP


def process_xtb_file(uploaded_file, portfolio_obj):
    filename = uploaded_file.name.lower()
    df = None

    # ==========================================
    # 1. WCZYTYWANIE PLIKU (Excel lub CSV)
    # ==========================================
    if filename.endswith(('.xlsx', '.xls')):
        try:
            xls = pd.ExcelFile(uploaded_file)
        except Exception as e:
            raise ValueError(f"Excel Error: {e}")

        # Szukanie arkusza CASH
        target_sheet = None
        for sheet in xls.sheet_names:
            if "CASH" in sheet.upper():
                target_sheet = sheet
                break
        if not target_sheet: target_sheet = xls.sheet_names[0]

        # Szukanie nagłówka
        df_preview = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=None, nrows=40)
        header_idx = None
        for idx, row in df_preview.iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            if "ID" in s and "Type" in s and "Comment" in s:
                header_idx = idx
                break

        if header_idx is None:
            raise ValueError("Nie znaleziono nagłówka (ID, Type, Comment) w pliku Excel.")

        uploaded_file.seek(0)
        df = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=header_idx)

    elif filename.endswith('.csv'):
        # Próba różnych kodowań dla CSV
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
                uploaded_file.seek(0)
                temp = pd.read_csv(uploaded_file, encoding=params['encoding'], sep=params['sep'])
                if len(temp.columns) > 1:
                    df_raw = temp
                    break
            except:
                continue

        if df_raw is None:
            raise ValueError("Nie udało się odczytać pliku CSV (błąd kodowania).")

        # Szukanie nagłówka w CSV
        header_idx = None
        for idx, row in df_raw.head(40).iterrows():
            s = " ".join([str(v) for v in row.fillna('').values])
            if "ID" in s and "Type" in s and "Comment" in s:
                header_idx = idx
                break

        if header_idx is None:
            # Sprawdzenie czy nagłówek jest już wczytany
            s = " ".join([str(c) for c in df_raw.columns])
            if "ID" in s and "Type" in s:
                df = df_raw
            else:
                raise ValueError("Nie znaleziono nagłówka w pliku CSV.")
        else:
            new_header = df_raw.iloc[header_idx]
            df = df_raw[header_idx + 1:].copy()
            df.columns = new_header

    else:
        raise ValueError("Nieobsługiwany format pliku. Użyj .xlsx lub .csv")

    # ==========================================
    # 2. PRZETWARZANIE DANYCH
    # ==========================================

    df.columns = [str(c).strip() for c in df.columns]

    stats = {'added': 0, 'skipped': 0, 'new_assets': 0}
    asset_cache = {}

    for _, row in df.iterrows():
        # Pomijamy wiersze bez ID
        if pd.isna(row.get('ID')): continue

        xtb_id = str(row['ID'])

        # Pomijamy duplikaty
        if Transaction.objects.filter(xtb_id=xtb_id).exists():
            stats['skipped'] += 1
            continue

        trans_type = _parse_transaction_type(str(row.get('Type', '')))
        quantity = _parse_quantity(trans_type, str(row.get('Comment', '')))

        # --- FIX: BEZPIECZNE PARSOWANIE DATY (NAPRAWA BŁĘDU NaT) ---
        try:
            val_time = row['Time']
            # Jeśli komórka jest pusta lub None -> pomiń wiersz
            if pd.isna(val_time) or str(val_time).strip() == '':
                continue

            dt = pd.to_datetime(val_time)

            # Kluczowe sprawdzenie: Czy wynik to poprawna data, czy błąd NaT?
            if pd.isna(dt):
                continue

            if dt.tzinfo is None:
                date_obj = timezone.make_aware(dt)
            else:
                date_obj = dt
        except Exception:
            # W razie jakiegokolwiek innego błędu daty, pomijamy ten wiersz
            continue
        # -----------------------------------------------------------

        # Kwota
        try:
            val = row['Amount']
            if isinstance(val, str):
                val = val.replace(',', '.').replace(' ', '')
            amount = float(val)
        except:
            amount = 0.0

        # --- SMART ASSET DISCOVERY ---
        asset_obj = None
        sym = str(row.get('Symbol', '')).strip()

        if sym and sym.lower() != 'nan':
            if sym in asset_cache:
                asset_obj = asset_cache[sym]
            else:
                asset_obj, created = _get_or_create_asset_smart(sym)
                asset_cache[sym] = asset_obj
                if created:
                    stats['new_assets'] += 1

        # Zapis (bez pola raw_data, które powodowało błąd)
        Transaction.objects.create(
            portfolio=portfolio_obj,
            asset=asset_obj,
            xtb_id=xtb_id,
            date=date_obj,
            type=trans_type,
            amount=amount,
            quantity=quantity,
            comment=str(row.get('Comment', ''))
        )
        stats['added'] += 1

    return stats


# --- HELPERY ---

def _get_or_create_asset_smart(xtb_symbol):
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
            if 'shortName' in info:
                name = info['shortName']
            elif 'longName' in info:
                name = info['longName']
        except:
            pass

    return Asset.objects.create(
        symbol=xtb_symbol,
        yahoo_ticker=yahoo_ticker,
        currency=currency,
        name=name
    ), True


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
                val = match.group(2)
                if '/' in val: val = val.split('/')[0]
                return float(val)
            except:
                pass
    return 0.0