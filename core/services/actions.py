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
    """
    Obsługuje logikę dodawania transakcji:
    1. Mapowanie XTB -> Yahoo (Asset Resolution).
    2. Walidację ceny w Yahoo (ZAWSZE - dla nowych i starych).
    3. Auto-Deposit (jeśli brakuje gotówki).
    4. Zapis do bazy.
    Rzuca wyjątki (ValueError) z komunikatami dla użytkownika.
    """
    t_type = data.get('type')
    date_obj = data.get('date_obj')  # datetime aware
    symbol = data.get('symbol', '').upper().strip()
    qty = float(data.get('quantity', 0.0))
    price = float(data.get('price', 0.0))
    amount = float(data.get('amount', 0.0))  # Total Value
    auto_deposit = data.get('auto_deposit')

    # 1. ASSET RESOLUTION & VALIDATION
    asset_obj = None
    if t_type in ['BUY', 'SELL', 'DIVIDEND'] and symbol:

        # A. Szukamy dokładnie w bazie
        asset_obj = Asset.objects.filter(symbol__iexact=symbol).first()

        # B. Szukamy z domyślnym sufiksem (jeśli user zapomniał .PL)
        if not asset_obj:
            potential = Asset.objects.filter(symbol__startswith=symbol + ".")
            if potential.exists():
                asset_obj = potential.first()

        # Ustal ticker do sprawdzenia w Yahoo
        yahoo_ticker_to_validate = None

        if asset_obj:
            # Jeśli mamy asset, używamy jego zapisanego tickera Yahoo
            yahoo_ticker_to_validate = asset_obj.yahoo_ticker
        else:
            # Jeśli nie mamy, musimy go wyliczyć (Mapowanie)
            base_ticker, ext = os.path.splitext(symbol)
            ext = ext.upper()

            if ext in SUFFIX_MAP:
                mapping = SUFFIX_MAP[ext]
                yahoo_suffix = mapping.get('yahoo_suffix', '')
                if yahoo_suffix is None: yahoo_suffix = ''
                yahoo_ticker_to_validate = base_ticker + yahoo_suffix
            else:
                if not ext:
                    raise ValueError(f"Symbol '{symbol}' jest niejednoznaczny. Dodaj końcówkę kraju, np. .PL, .US")
                # Jeśli jest nieznany sufiks, zakładamy że to ticker Yahoo (fallback)
                yahoo_ticker_to_validate = symbol

        # --- C. WALIDACJA (TERAZ DZIAŁA ZAWSZE) ---
        # Sprawdzamy cenę niezależnie czy asset jest nowy czy stary
        check_price = price if t_type != 'DIVIDEND' else amount

        # Wywołujemy walidator z market.py
        is_valid, error_msg = validate_ticker_and_price(yahoo_ticker_to_validate, date_obj, check_price)

        if not is_valid:
            # Dodajemy kontekst do błędu
            raise ValueError(f"Błąd weryfikacji ceny dla '{symbol}' ({yahoo_ticker_to_validate}): {error_msg}")

        # D. Tworzymy nowy asset TYLKO jeśli go nie było i walidacja przeszła
        if not asset_obj:
            asset_obj = Asset.objects.create(
                symbol=symbol,
                yahoo_ticker=yahoo_ticker_to_validate,
                name=symbol
            )

    # 2. AUTO DEPOSIT LOGIC
    if t_type == 'BUY' and auto_deposit:
        all_trans = Transaction.objects.filter(portfolio=portfolio)
        calc = PortfolioCalculator(all_trans).process()
        current_cash, _ = calc.get_cash_balance()

        cost = abs(amount)
        if current_cash < cost:
            missing = cost - current_cash
            # Depozyt 1 sek wcześniej
            dep_date = date_obj - timedelta(seconds=1)
            dep_id = f"MAN-DEP-{dep_date.strftime('%Y%m%d%H%M%S')}-{random.randint(100, 999)}"

            Transaction.objects.create(
                portfolio=portfolio,
                xtb_id=dep_id,
                date=dep_date,
                type='DEPOSIT',
                amount=missing,
                comment="Auto-Deposit for Manual Transaction"
            )

    # 3. CREATE TRANSACTION
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

    return f"Transaction {t_type} {symbol} added successfully."