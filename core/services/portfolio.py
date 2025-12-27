# core/services/portfolio.py

from datetime import date
import pandas as pd
from .config import fmt_2, fmt_4
from .market import get_current_currency_rates, get_cached_price, fetch_historical_data_for_timeline
from .calculator import PortfolioCalculator
from .selectors import get_transactions, get_asset_by_symbol, get_portfolio_by_id
from .analytics import analyze_holdings, analyze_history


# =========================================================
# 1. GŁÓWNY KONTEKST DASHBOARDU (Presenter)
# =========================================================

def get_dashboard_context(user, portfolio_id=None):
    """
    Zbiera dane z warstwy Selectors i Analytics, formatuje je dla widoku.
    """
    # 1. Pobieramy dane (Data Layer)
    transactions = get_transactions(user, portfolio_id)

    # Jeśli brak transakcji, szybki powrót
    if not transactions.exists():
        return _get_empty_dashboard_context()

    # 2. Pobieramy dane rynkowe (External API Layer)
    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30)
    usd_rate = rates.get('USD', 4.00)

    # 3. Analityka (Business Logic Layer)
    stats = analyze_holdings(transactions, eur_rate, usd_rate)
    timeline = analyze_history(transactions, eur_rate, usd_rate)

    # 4. Prezentacja (Formatting Layer)
    charts = _prepare_dashboard_charts(stats['assets'], stats['cash'])

    # --- FIX: Obliczamy Annual Return raz, żeby mieć wersję RAW i STR ---
    annual_ret = _calculate_annual_return(stats['total_profit'], stats['invested'], stats['first_date'])
    # -------------------------------------------------------------------

    # 5. Budowanie ostatecznego słownika dla szablonu
    context = {
        # Kafelki główne
        'tile_value_str': fmt_2(stats['total_value']),
        'tile_value_raw': stats['total_value'],

        'tile_total_profit_str': fmt_2(stats['total_profit']),
        'tile_total_profit_raw': stats['total_profit'],

        'tile_return_pct_str': fmt_2((stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0),
        'tile_return_pct_raw': (stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0,

        'tile_day_pln_str': fmt_2(stats['day_change_pln']),
        'tile_day_pln_raw': stats['day_change_pln'],

        'tile_day_pct_str': fmt_2(
            (stats['day_change_pln'] / (stats['total_value'] - stats['day_change_pln']) * 100) if (stats['total_value'] - stats['day_change_pln']) > 0 else 0),
        'tile_day_pct_raw': (stats['day_change_pln'] / (stats['total_value'] - stats['day_change_pln']) * 100) if (stats['total_value'] - stats['day_change_pln']) > 0 else 0,

        'tile_current_profit_str': fmt_2(stats['total_profit']),
        'tile_current_profit_raw': stats['total_profit'],

        'tile_gainers': stats['gainers'],
        'tile_losers': stats['losers'],

        # --- FIX: Przekazujemy RAW do koloru ---
        'tile_annual_pct_str': fmt_2(annual_ret),
        'tile_annual_pct_raw': annual_ret,
        # ---------------------------------------

        # Wykresy i Tabele
        'chart_labels': charts['labels'],
        'chart_allocation': charts['allocation'],
        'chart_profit_labels': charts['profit_labels'],
        'chart_profit_values': charts['profit_values'],
        'closed_labels': charts['closed_labels'],
        'closed_values': charts['closed_values'],
        'closed_holdings': charts['closed_items_display'],

        # Timeline
        'timeline_dates': timeline['dates'],
        'timeline_total_value': timeline['val_user'],
        'timeline_invested': timeline['val_inv'],
        'timeline_deposit_points': timeline['points'],
        'timeline_pct_user': timeline['pct_user'],
        'timeline_pct_wig': [],
        'timeline_pct_sp500': timeline['pct_sp'],
        'timeline_pct_inflation': timeline['pct_inf'],
        'last_market_date': timeline['last_market_date'],

        # Pozostałe
        'rates': rates,
        'invested': fmt_2(stats['invested']),
        'cash': fmt_2(stats['cash']),
        'pln_items': [],
        'foreign_items': []
    }

    _enrich_context_with_groups(context, stats['assets'], stats['total_value'])

    return context


# =========================================================
# 2. SZCZEGÓŁY AKTYWA (Presenter)
# =========================================================

def get_asset_details_context(user, symbol, portfolio_id=None):
    """
    Buduje szczegółowy widok jednego aktywa.
    """
    portfolio = get_portfolio_by_id(user, portfolio_id)
    asset = get_asset_by_symbol(symbol)

    if not portfolio or not asset:
        return {'symbol': symbol, 'error': 'Asset or Portfolio not found.'}

    # Pobieramy transakcje TYLKO dla tego aktywa
    all_trans = get_transactions(user, portfolio.id)
    asset_trans = all_trans.filter(asset=asset).order_by('date')

    # Obliczenia pozycji
    calc = PortfolioCalculator(asset_trans).process()
    holdings = calc.get_holdings()
    asset_data = holdings.get(symbol, {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'trades': []})

    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30);
    usd_rate = rates.get('USD', 4.00);
    gbp_rate = rates.get('GBP', 5.20)

    multiplier = 1.0
    if asset.currency == 'EUR':
        multiplier = eur_rate
    elif asset.currency == 'USD':
        multiplier = usd_rate
    elif asset.currency == 'GBP':
        multiplier = gbp_rate
    elif asset.currency == 'JPY':
        multiplier = rates.get('JPY', 1.0) / 100.0

    # Historia cen (Market Layer)
    first_date = asset_trans.first().date.date() if asset_trans.exists() else date.today()
    hist_df = fetch_historical_data_for_timeline([asset.yahoo_ticker], first_date)

    current_price_orig = 0.0
    prev_close = 0.0
    ath = 0.0
    atl = 0.0
    chart_dates = []
    chart_prices = []

    try:
        if not hist_df.empty:
            series = None
            # Obsługa MultiIndex (YFinance group_by='ticker')
            if isinstance(hist_df.columns, pd.MultiIndex):
                if asset.yahoo_ticker in hist_df.columns.levels[0]:
                    series = hist_df[asset.yahoo_ticker]['Close']
            else:
                series = hist_df['Close']

            if series is not None and not series.empty:
                # --- FIX: DROPNA() JEST KLUCZOWE ---
                # Usuwamy dni, w których giełda nie działała dla tego konkretnego tickera
                # (np. święta w USA, gdy pobraliśmy też benchmarki z USA)
                series = series.dropna()

                if not series.empty:
                    # Ostatnia cena
                    current_price_orig = float(series.iloc[-1])
                    if len(series) >= 2:
                        prev_close = float(series.iloc[-2])
                    else:
                        prev_close = current_price_orig

                    # ATH / ATL
                    ath = float(series.max()) * multiplier
                    atl = float(series.min()) * multiplier

                    # Dane do wykresu (teraz bez NaN)
                    chart_dates = series.index.strftime('%Y-%m-%d').tolist()
                    chart_prices = [float(p) * multiplier for p in series.tolist()]
                else:
                    # Jeśli po dropna() nic nie zostało
                    current_price_orig, prev_close = get_cached_price(asset)
            else:
                current_price_orig, prev_close = get_cached_price(asset)
        else:
            current_price_orig, prev_close = get_cached_price(asset)

    except Exception as e:
        print(f"Details Chart Error: {e}")
        current_price_orig, prev_close = get_cached_price(asset)

    # Fallback ceny, gdyby nadal 0
    qty = asset_data['qty']
    cost = asset_data['cost']
    if current_price_orig <= 0:
        current_price_orig = (cost / qty) if qty > 0 else 0
        prev_close = current_price_orig

    # Wyliczenia końcowe
    current_value_pln = qty * current_price_orig * multiplier
    avg_price_pln = (cost / qty) if qty > 0 else 0.0
    total_gain_pln = (current_value_pln - cost) + asset_data['realized']
    profit_percent = (total_gain_pln / cost * 100) if cost > 0.01 else 0

    day_change_pct = 0.0
    day_change_pln = 0.0
    if prev_close > 0:
        day_change_pct = ((current_price_orig - prev_close) / prev_close) * 100
        day_change_pln = (qty * (current_price_orig - prev_close)) * multiplier

    # Tabela historii
    history_table = []
    trade_events = {}

    for t in asset_data['trades']:
        price_val = t.get('price', 0.0)
        history_table.append({
            'date': t['date'].strftime('%Y-%m-%d'),
            'type': t['type'],
            'quantity': fmt_4(t['qty']),
            'price_original': f"{price_val:.2f}",
            'currency': 'PLN',
            'value_pln': fmt_2(abs(t['amount']))
        })
        d_str = t['date'].strftime("%Y-%m-%d")
        if t['type'] in ['OPEN BUY', 'BUY']:
            trade_events[d_str] = 'BUY'
        elif t['type'] in ['CLOSE SELL', 'SELL']:
            trade_events[d_str] = 'SELL'

    # Kolory punktów na wykresie
    chart_point_colors = []
    chart_point_radius = []
    for d in chart_dates:
        if d in trade_events:
            color = '#00ff7f' if trade_events[d] == 'BUY' else '#ff4d4d'
            chart_point_colors.append(color)
            chart_point_radius.append(6)
        else:
            chart_point_colors.append('rgba(0,0,0,0)')
            chart_point_radius.append(0)

    return {
        'symbol': symbol,
        'asset_name': asset.name,
        'current_value_pln': fmt_2(current_value_pln),
        'avg_price': fmt_2(avg_price_pln),
        'quantity': fmt_4(qty),
        'gain_percent': fmt_2(profit_percent),
        'gain_percent_raw': profit_percent,
        'total_gain_pln': fmt_2(total_gain_pln),
        'total_gain_pln_raw': total_gain_pln,
        'current_price': fmt_2(current_price_orig * multiplier),
        'currency_sym': 'PLN',
        'day_change_pct': fmt_2(day_change_pct), 'day_change_pct_raw': day_change_pct,
        'day_change_pln': fmt_2(day_change_pln), 'day_change_pln_raw': day_change_pln,
        'transactions': reversed(history_table),
        'chart_dates': chart_dates,
        'chart_prices': chart_prices,
        'chart_point_colors': chart_point_colors,
        'chart_point_radius': chart_point_radius,
        'first_trade_date': first_date.strftime('%Y-%m-%d'),
        'ath': ath,
        'atl': atl,
        'rates': rates
    }


# =========================================================
# HELPERY PREZENTACJI (Prywatne)
# =========================================================

def _get_empty_dashboard_context():
    """Zwraca pusty stan dashboardu."""
    return {
        'invested': "0.00", 'cash': "0.00", 'stock_value': "0.00",
        'tile_value_str': "0.00", 'tile_total_profit_str': "0.00",
        'tile_return_pct_str': "0.00", 'tile_day_pct_str': "0.00",
        'tile_day_pln_str': "0.00", 'tile_current_profit_str': "0.00",
        'tile_annual_pct_str': "0.00",
        'tile_gainers': 0, 'tile_losers': 0,
        'rates': get_current_currency_rates()
    }


def _prepare_dashboard_charts(assets, cash):
    """Przerabia surowe dane z analytics na format dla Chart.js."""
    charts = {
        'labels': [], 'allocation': [],
        'profit_labels': [], 'profit_values': [],
        'closed_labels': [], 'closed_values': [], 'closed_items_display': []
    }

    sorted_assets = sorted([a for a in assets if not a['is_closed']], key=lambda x: x['value_pln'], reverse=True)

    for a in sorted_assets:
        charts['labels'].append(a['symbol'])
        charts['allocation'].append(a['value_pln'])
        charts['profit_labels'].append(a['symbol'])
        charts['profit_values'].append(a['total_gain_pln'])

    if cash > 1:
        charts['labels'].append("CASH")
        charts['allocation'].append(cash)

    closed_assets = [a for a in assets if a['is_closed']]
    for a in closed_assets:
        charts['closed_labels'].append(a['symbol'])
        charts['closed_values'].append(round(a['realized_pln'], 2))
        charts['closed_items_display'].append({
            'symbol': a['symbol'],
            'gain_pln': fmt_2(a['realized_pln']),
            'gain_pln_raw': a['realized_pln']
        })

    return charts


def _calculate_annual_return(total_profit, invested, first_date):
    if not first_date or invested <= 0: return 0.0
    days = (date.today() - first_date).days
    total_return_pct = (total_profit / invested * 100)
    if days > 365:
        return total_return_pct / (days / 365.25)
    return total_return_pct


def _enrich_context_with_groups(context, assets, total_portfolio_value):
    """
    Odtwarza grupy PLN/Foreign dla tabeli w dashboardzie.
    """
    pln_items = []
    foreign_items = []

    # Tylko aktywne
    active_assets = [a for a in assets if not a['is_closed']]

    for a in active_assets:
        # --- FIX: OBLICZANIE DNI POSIADANIA ---
        days_held = 0
        if a.get('trades'):
            # Sortujemy transakcje, żeby znaleźć pierwszą
            sorted_trades = sorted(a['trades'], key=lambda x: x['date'])
            first_trade_date = sorted_trades[0]['date'].date()
            days_held = (date.today() - first_trade_date).days
        # --------------------------------------

        # Konwersja na format wyświetlania (stringi)
        item = {
            'symbol': a['symbol'], 'name': a['name'],
            'quantity': fmt_4(a['qty']),
            'avg_price_pln': fmt_2(a['avg_price']),
            'current_price_fmt': f"{a['cur_price']:.2f} {a['currency']}",
            'value_pln': fmt_2(a['value_pln']), 'value_pln_raw': a['value_pln'],
            'gain_pln': fmt_2(a['total_gain_pln']), 'gain_pln_raw': a['total_gain_pln'],
            'gain_percent': fmt_2((a['total_gain_pln'] / a['cost_pln'] * 100) if a['cost_pln'] > 0 else 0),
            'gain_percent_raw': (a['total_gain_pln'] / a['cost_pln'] * 100) if a['cost_pln'] > 0 else 0,
            'day_change_pct': fmt_2(a['day_change_pct']), 'day_change_pct_raw': a['day_change_pct'],
            # --- FIX: Przekazywanie daty i dni ---
            'days_held': days_held,
            'price_date': a['price_date'],
            # -------------------------------------
            'share_pct': fmt_2((a['value_pln'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0),
            'share_pct_raw': (a['value_pln'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0,
            'cost_pln_raw': a['cost_pln'],
            'is_foreign': a['is_foreign']
        }

        if a['is_foreign']:
            foreign_items.append(item)
        else:
            pln_items.append(item)

    # Sortowanie
    pln_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)
    foreign_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)

    # Proste statystyki grup
    context['pln_items'] = pln_items
    context['foreign_items'] = foreign_items

    # Szybka suma dla stats (stopka tabeli)
    def calculate_group_stats(items):
        if not items: return {'value': "0.00", 'gain': "0.00", 'gain_raw': 0, 'return_pct': "0.00",
                              'share_total': "0.00"}
        sum_val = sum(x['value_pln_raw'] for x in items)
        sum_cost = sum(x['cost_pln_raw'] for x in items)
        sum_gain = sum(x['gain_pln_raw'] for x in items)

        grp_return_pct = (sum_gain / sum_cost * 100) if sum_cost > 0 else 0.0
        grp_share = (sum_val / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0

        return {
            'value': fmt_2(sum_val),
            'gain': fmt_2(sum_gain), 'gain_raw': sum_gain,
            'return_pct': fmt_2(grp_return_pct),
            'share_total': fmt_2(grp_share)
        }

    context['pln_stats'] = calculate_group_stats(pln_items)
    context['foreign_stats'] = calculate_group_stats(foreign_items)