# core/services/analytics.py

import math
import pandas as pd
from datetime import date, timedelta
from .calculator import PortfolioCalculator
from .market import get_cached_price, fetch_historical_data_for_timeline


def analyze_holdings(transactions, eur_rate, usd_rate):
    """
    Analizuje stan posiadania na DZISIAJ.
    Łączy dane ilościowe (Calculator) z danymi rynkowymi (Market).
    Zwraca słownik z surowymi danymi liczbowymi.
    """
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    cash, total_invested = calc.get_cash_balance()

    processed_assets = []
    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0

    # Statystyki zysków/strat dziennych
    gainers = 0
    losers = 0

    for sym, data in holdings_data.items():
        qty = data['qty']
        asset = data['asset']

        # Pozycje zamknięte
        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                processed_assets.append({
                    'is_closed': True,
                    'symbol': sym,
                    'realized_pln': data['realized']
                })
            continue

        # Pozycje otwarte
        cost = data['cost']

        # Pobranie ceny rynkowej (z market.py)
        cur_price, prev_close = get_cached_price(asset)

        # Fallback ceny (gdyby market zwrócił 0)
        if cur_price <= 0:
            cur_price = (cost / qty) if qty > 0 else 0
            prev_close = cur_price

        # Wybór waluty
        multiplier = 1.0
        is_foreign = False
        if asset.currency == 'EUR':
            multiplier = eur_rate; is_foreign = True
        elif asset.currency == 'USD':
            multiplier = usd_rate; is_foreign = True
        elif asset.currency == 'GBP':
            multiplier = 5.20; is_foreign = True  # Sztywne 5.20 lub dodać do market.py

        if math.isnan(multiplier): multiplier = 1.0

        # Matematyka wyceny
        value_pln = (qty * cur_price) * multiplier
        current_position_gain = value_pln - cost
        total_gain = current_position_gain + data['realized']

        day_change_pct = 0.0
        if prev_close > 0:
            day_change_pct = ((cur_price - prev_close) / prev_close) * 100

        day_change_val = (qty * (cur_price - prev_close)) * multiplier

        if day_change_pct > 0:
            gainers += 1
        elif day_change_pct < 0:
            losers += 1

        portfolio_value_stock += value_pln
        total_day_change_pln += day_change_val

        avg_price = (cost / qty) if qty > 0 else 0

        processed_assets.append({
            'is_closed': False,
            'symbol': sym,
            'name': asset.name,
            'qty': qty,
            'avg_price': avg_price,
            'cur_price': cur_price,
            'currency': asset.currency,
            'value_pln': value_pln,
            'cost_pln': cost,
            'total_gain_pln': total_gain,
            'realized_pln': data['realized'],
            'day_change_pct': day_change_pct,
            'is_foreign': is_foreign,
            'price_date': asset.last_updated,
            'trades': data['trades']  # Potrzebne do historii assetu
        })

    total_value = portfolio_value_stock + cash
    total_profit = total_value - total_invested

    return {
        'total_value': total_value,
        'invested': total_invested,
        'cash': cash,
        'total_profit': total_profit,
        'day_change_pln': total_day_change_pln,
        'assets': processed_assets,
        'gainers': gainers,
        'losers': losers,
        'first_date': calc.first_date
    }


def analyze_history(transactions, eur_rate, usd_rate):
    """
    Generuje dane do wykresu historycznego.
    Używa mechanizmu 'Safe Price' (Forward Fill) z market.py.
    """
    if not transactions.exists():
        return {'dates': [], 'val_user': [], 'val_inv': [], 'last_date': 'N/A'}

    sorted_trans = transactions.order_by('date')
    start_date = sorted_trans.first().date.date()
    end_date = date.today()

    # Pobieramy tickery z transakcji
    user_tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))

    # Pobieramy dane (z market.py)
    hist_data = fetch_historical_data_for_timeline(user_tickers, start_date)

    last_market_date_str = "N/A"
    if not hist_data.empty:
        last_market_date_str = hist_data.index[-1].strftime('%d %b %Y')

    # Helper wewnątrz funkcji (korzysta z hist_data)
    def get_price_ffill(ticker, query_date):
        if hist_data.empty: return 0.0
        try:
            # Obsługa MultiIndex (jeśli pobrano wiele tickerów)
            if isinstance(hist_data.columns, pd.MultiIndex):
                if ticker not in hist_data.columns.levels[0]: return 0.0
                series = hist_data[ticker]['Close']
            else:
                # Obsługa pojedynczego tickera (rzadkie przy all_tickers, ale możliwe)
                # Sprawdzamy czy ticker się zgadza
                # W tym przypadku yfinance zwraca DataFrame bez poziomu tickera
                series = hist_data['Close']

            val = series.asof(str(query_date))
            return float(val) if not pd.isna(val) else 0.0
        except:
            return 0.0

    # Symulacja dzień po dniu
    sim = {'cash': 0.0, 'invested': 0.0, 'holdings': {}, 'sp500_units': 0.0, 'inflation_capital': 0.0}
    timeline = {
        'dates': [], 'points': [],
        'val_user': [], 'val_inv': [], 'val_sp': [], 'val_inf': [],
        'pct_user': [], 'pct_sp': [], 'pct_inf': [],
        'last_market_date': last_market_date_str
    }

    trans_list = list(sorted_trans)
    trans_idx = 0
    total_trans = len(trans_list)
    current_day = start_date

    while current_day <= end_date:
        is_deposit_day = False

        # Przetwarzanie transakcji z danego dnia
        while trans_idx < total_trans and trans_list[trans_idx].date.date() <= current_day:
            t = trans_list[trans_idx];
            amt = float(t.amount);
            qty = float(t.quantity)

            if t.type == 'DEPOSIT':
                sim['cash'] += amt;
                sim['invested'] += amt;
                sim['inflation_capital'] += amt;
                is_deposit_day = True
                # Kupujemy wirtualne SP500
                p_usd = get_price_ffill('USDPLN=X', current_day)
                p_sp = get_price_ffill('^GSPC', current_day)
                if p_usd > 0 and p_sp > 0: sim['sp500_units'] += (amt / p_usd) / p_sp

            elif t.type == 'WITHDRAWAL':
                sim['cash'] -= abs(amt);
                sim['invested'] -= abs(amt);
                sim['inflation_capital'] -= abs(amt)
            elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                sim['cash'] += amt

            if t.asset:
                tk = t.asset.yahoo_ticker
                if t.type == 'BUY':
                    sim['holdings'][tk] = sim['holdings'].get(tk, 0.0) + qty
                elif t.type == 'SELL':
                    sim['holdings'][tk] = sim['holdings'].get(tk, 0.0) - qty

            trans_idx += 1

        # Wycena na koniec dnia
        user_val = sim['cash']
        for tk, q in sim['holdings'].items():
            if q <= 0.0001: continue

            price = get_price_ffill(tk, current_day)

            if price > 0:
                val = price * q
                if '.DE' in tk:
                    # Zabezpieczenie EUR
                    val *= 4.30 if math.isnan(eur_rate) else eur_rate
                elif '.US' in tk or '.UK' in tk:
                    hist_usd = get_price_ffill('USDPLN=X', current_day)
                    usd_val = hist_usd if hist_usd > 0 else (usd_rate if not math.isnan(usd_rate) else 4.00)
                    val *= usd_val
                user_val += val

        # Benchmarki
        sp_val = 0.0
        p_sp = get_price_ffill('^GSPC', current_day)
        p_usd = get_price_ffill('USDPLN=X', current_day)
        if p_sp > 0 and p_usd > 0: sp_val = sim['sp500_units'] * p_sp * p_usd

        # Inflacja (6%)
        sim['inflation_capital'] *= 1.06 ** (1 / 365)

        # Zapis do osi czasu
        timeline['dates'].append(current_day.strftime("%Y-%m-%d"))
        timeline['points'].append(6 if is_deposit_day else 0)
        timeline['val_user'].append(round(user_val, 2))
        timeline['val_inv'].append(round(sim['invested'], 2))
        timeline['val_sp'].append(round(sp_val, 2) if sp_val > 0 else round(sim['invested'], 2))
        timeline['val_inf'].append(round(sim['inflation_capital'], 2))

        # Procenty
        base = sim['invested'] if sim['invested'] > 0 else 1.0
        timeline['pct_user'].append(round((user_val - base) / base * 100, 2))
        timeline['pct_sp'].append(round((sp_val - base) / base * 100 if sp_val > 0 else 0, 2))
        timeline['pct_inf'].append(round((sim['inflation_capital'] - base) / base * 100, 2))

        current_day += timedelta(days=1)

    return timeline