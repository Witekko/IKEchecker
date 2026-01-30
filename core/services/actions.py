# core/services/actions.py

import os
import random
from datetime import timedelta
from django.utils import timezone
from ..models import Asset, Transaction
from core.config import SUFFIX_MAP
from .market import validate_ticker_and_price
from .calculator import PortfolioCalculator
from .market import fetch_asset_metadata

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


def update_assets_bulk(post_data):
    """
    Parsuje surowe dane z formularza (request.POST) i aktualizuje aktywa.
    Oczekuje kluczy: asset_{id}_name, asset_{id}_sector, asset_{id}_type.
    """
    # Pobieramy wszystkie aktywa do mapy, żeby nie robić 100 zapytań SQL
    all_assets = {str(a.id): a for a in Asset.objects.all()}
    updated_count = 0

    for key, value in post_data.items():
        # Szukamy kluczy zmian nazwy, bo one są wyznacznikiem wiersza
        if key.startswith('asset_') and key.endswith('_name'):
            parts = key.split('_')
            if len(parts) == 3:
                asset_id = parts[1]

                if asset_id in all_assets:
                    asset = all_assets[asset_id]

                    # Pobieramy wartości z formularza
                    new_name = value.strip()
                    new_sector = post_data.get(f'asset_{asset_id}_sector')
                    new_type = post_data.get(f'asset_{asset_id}_type')

                    # Sprawdzamy zmiany (Dirty check)
                    changed = False
                    if asset.name != new_name:
                        asset.name = new_name
                        changed = True
                    if asset.sector != new_sector:
                        asset.sector = new_sector
                        changed = True
                    if asset.asset_type != new_type:
                        asset.asset_type = new_type
                        changed = True

                    if changed:
                        asset.save()
                        updated_count += 1

    return updated_count


def sync_all_assets_metadata():
    """
    Iteruje po wszystkich aktywach i aktualizuje dane z Yahoo Finance.
    Zwraca (zaktualizowane, błędy).
    """
    assets = Asset.objects.all()
    updated_count = 0
    errors = 0

    for asset in assets:
        # Pomijamy waluty i PLN, bo Yahoo często nie ma dla nich dobrych metadanych
        if asset.symbol == 'CASH' or ('PLN' in asset.symbol and len(asset.symbol) == 3):
            continue

        ticker = asset.yahoo_ticker if asset.yahoo_ticker else asset.symbol
        data = fetch_asset_metadata(ticker)

        if data['success']:
            changed = False

            # Logika nadpisywania (tylko jeśli w bazie są domyślne/puste)
            if asset.sector == 'OTHER' and data['sector'] != 'OTHER':
                asset.sector = data['sector']
                changed = True

            if asset.asset_type == 'STOCK' and data['asset_type'] != 'STOCK':
                asset.asset_type = data['asset_type']
                changed = True

            # Nazwę aktualizujemy, jeśli obecna jest pusta lub tożsama z symbolem
            if not asset.name or asset.name == asset.symbol:
                if data['name']:
                    asset.name = data['name']
                    changed = True

            if changed:
                asset.save()
                updated_count += 1
        else:
            errors += 1

    return updated_count, errors