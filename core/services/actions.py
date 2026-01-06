# core/services/actions.py

import os
import random
from datetime import timedelta
from django.utils import timezone
from ..models import Asset, Transaction
from .config import SUFFIX_MAP
from .market import validate_ticker_and_price
from .calculator import PortfolioCalculator


def add_manual_transaction(portfolio, data):
    t_type = data.get('type')
    date_obj = data.get('date_obj')
    symbol = data.get('symbol', '').upper().strip()
    qty = float(data.get('quantity', 0.0))
    price = float(data.get('price', 0.0))
    amount = float(data.get('amount', 0.0))
    auto_deposit = data.get('auto_deposit')

    # 1. ASSET RESOLUTION & VALIDATION
    asset_obj = None
    if t_type in ['BUY', 'SELL', 'DIVIDEND'] and symbol:

        # A. Szukamy w bazie (PKN)
        asset_obj = Asset.objects.filter(symbol__iexact=symbol).first()

        # B. Fallback: Szukamy po początku (PKN.PL)
        if not asset_obj:
            potential = Asset.objects.filter(symbol__startswith=symbol + ".")
            if potential.exists():
                asset_obj = potential.first()

        # Ustal ticker do sprawdzenia
        yahoo_ticker_to_validate = None

        if asset_obj:
            yahoo_ticker_to_validate = asset_obj.yahoo_ticker
        else:
            # Próba zgadywania sufiksu
            base_ticker, ext = os.path.splitext(symbol)
            ext = ext.upper()
            if ext in SUFFIX_MAP:
                mapping = SUFFIX_MAP[ext]
                yahoo_suffix = mapping.get('yahoo_suffix', '') or ''
                yahoo_ticker_to_validate = base_ticker + yahoo_suffix
            else:
                # Brak rozszerzenia? Zakładamy, że to surowy ticker (np. PKN)
                yahoo_ticker_to_validate = symbol

        # --- C. WALIDACJA ---
        check_price = price if t_type != 'DIVIDEND' else amount

        # Walidacja zwraca (True/False, "POPRAWNY_TICKER" lub "KOMUNIKAT")
        is_valid, result_or_msg = validate_ticker_and_price(yahoo_ticker_to_validate, date_obj, check_price)

        if not is_valid:
            raise ValueError(f"Błąd walidacji: {result_or_msg}")

        # Jeśli walidacja przeszła, result_or_msg to ticker, który ZADZIAŁAŁ (np. "PKN.PL")
        # Aktualizujemy naszą zmienną, żeby zapisać w bazie działający ticker!
        if result_or_msg:
            yahoo_ticker_to_validate = result_or_msg

        # D. Tworzenie lub Aktualizacja Assetu
        if not asset_obj:
            # Tworzymy nowy
            asset_obj = Asset.objects.create(
                symbol=symbol,
                yahoo_ticker=yahoo_ticker_to_validate,  # Zapisujemy ten, który zadziałał (PKN.PL)
                name=symbol
            )
        else:
            # Opcjonalnie: Naprawiamy istniejący, jeśli był zły (np. miał PKN a działa PKN.PL)
            if asset_obj.yahoo_ticker != yahoo_ticker_to_validate:
                asset_obj.yahoo_ticker = yahoo_ticker_to_validate
                asset_obj.save()

    # 2. AUTO DEPOSIT LOGIC
    if t_type == 'BUY' and auto_deposit:
        all_trans = Transaction.objects.filter(portfolio=portfolio)
        calc = PortfolioCalculator(all_trans).process()
        current_cash, _ = calc.get_cash_balance()

        cost = abs(amount)
        if current_cash < cost:
            missing = cost - current_cash
            dep_date = date_obj - timedelta(seconds=1)
            dep_id = f"MAN-DEP-{dep_date.strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"

            Transaction.objects.create(
                portfolio=portfolio,
                xtb_id=dep_id,
                date=dep_date,
                type='DEPOSIT',
                amount=missing,
                comment="Auto-Deposit"
            )

    # 3. SAVE TRANSACTION
    man_id = f"MAN-{date_obj.strftime('%Y%m%d%H%M')}-{t_type}-{random.randint(1000, 9999)}"
    final_amount = abs(amount)
    if t_type in ['BUY', 'WITHDRAWAL', 'TAX']:
        final_amount = -final_amount

    Transaction.objects.create(
        portfolio=portfolio,
        asset=asset_obj,
        xtb_id=man_id,
        date=date_obj,
        type=t_type,
        amount=final_amount,
        quantity=qty,
        comment="Manual Entry"
    )

    return f"Transaction {t_type} {symbol} added."