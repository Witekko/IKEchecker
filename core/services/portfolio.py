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
    transactions = get_transactions(user, portfolio_id)
    if not transactions.exists():
        return _get_empty_dashboard_context()

    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30)
    usd_rate = rates.get('USD', 4.00)

    # Analytics zwraca teraz FLOATY + display_name/sector
    stats = analyze_holdings(transactions, eur_rate, usd_rate)
    timeline = analyze_history(transactions, eur_rate, usd_rate)

    # Wykresy (działają na floatach)
    charts = _prepare_dashboard_charts(stats['assets'], stats['cash'])

    annual_ret = _calculate_annual_return(stats['total_profit'], stats['invested'], stats['first_date'])

    last_transactions = transactions.order_by('-date')[:20]

    # --- TRADING PERFORMANCE CALCULATIONS ---
    closed_assets = [a for a in stats['assets'] if a['is_closed']]
    win_count = sum(1 for a in closed_assets if a['gain_pln'] > 0)
    loss_count = sum(1 for a in closed_assets if a['gain_pln'] <= 0)
    total_closed_count = len(closed_assets)

    win_rate = (win_count / total_closed_count * 100) if total_closed_count > 0 else 0
    total_realized_pln = sum(a['gain_pln'] for a in closed_assets)

    best_trade = None
    worst_trade = None

    if closed_assets:
        # ZMIANA: Sortujemy po stopie zwrotu (ROI), a nie kwocie
        sorted_closed = sorted(closed_assets, key=lambda x: x['gain_percent'], reverse=True)
        best_trade = sorted_closed[0]
        worst_trade = sorted_closed[-1]

        # Formatowanie: ROI + Kwota
        if best_trade:
            best_trade['gain_fmt'] = fmt_2(best_trade['gain_pln'])
            best_trade['pct_fmt'] = fmt_2(best_trade['gain_percent'])
        if worst_trade:
            worst_trade['gain_fmt'] = fmt_2(worst_trade['gain_pln'])
            worst_trade['pct_fmt'] = fmt_2(worst_trade['gain_percent'])

    # ------------------------------------------------

    context = {
        'tile_value_str': fmt_2(stats['total_value']),
        'tile_value_raw': stats['total_value'],
        'tile_total_profit_str': fmt_2(stats['total_profit']),
        'tile_total_profit_raw': stats['total_profit'],
        'tile_return_pct_str': fmt_2((stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0),
        'tile_return_pct_raw': (stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0,
        'tile_day_pln_str': fmt_2(stats['day_change_pln']),
        'tile_day_pln_raw': stats['day_change_pln'],
        'tile_day_pct_str': fmt_2(
            (stats['day_change_pln'] / (stats['total_value'] - stats['day_change_pln']) * 100) if (stats[
                                                                                                       'total_value'] -
                                                                                                   stats[
                                                                                                       'day_change_pln']) > 0 else 0),
        'tile_day_pct_raw': (stats['day_change_pln'] / (stats['total_value'] - stats['day_change_pln']) * 100) if (
                                                                                                                              stats[
                                                                                                                                  'total_value'] -
                                                                                                                              stats[
                                                                                                                                  'day_change_pln']) > 0 else 0,
        'tile_current_profit_str': fmt_2(stats['unrealized_profit']),
        'tile_current_profit_raw': stats['unrealized_profit'],
        'tile_gainers': stats['gainers'],
        'tile_losers': stats['losers'],
        'tile_annual_pct_str': fmt_2(annual_ret),
        'tile_annual_pct_raw': annual_ret,

        # Performance KPIs
        'perf_win_rate': round(win_rate, 1),
        'perf_win_count': win_count,
        'perf_loss_count': loss_count,
        'perf_total_realized': fmt_2(total_realized_pln),
        'perf_total_realized_raw': total_realized_pln,
        'perf_best_trade': best_trade,
        'perf_worst_trade': worst_trade,
        'perf_total_closed': total_closed_count,

        # WYKRESY
        'chart_labels': charts['labels'],
        'chart_allocation': charts['allocation'],
        'chart_profit_labels': charts['profit_labels'],
        'chart_profit_values': charts['profit_values'],
        'chart_sector_labels': charts['sector_labels'],
        'chart_sector_values': charts['sector_values'],
        'chart_type_labels': charts['type_labels'],
        'chart_type_values': charts['type_values'],

        'closed_labels': charts['closed_labels'],
        'closed_values': charts['closed_values'],
        'closed_holdings': charts['closed_items_display'],

        'last_transactions': last_transactions,
        'timeline_dates': timeline['dates'],
        'timeline_total_value': timeline['val_user'],
        'timeline_invested': timeline['val_inv'],
        'timeline_deposit_points': timeline['points'],
        'timeline_pct_user': timeline['pct_user'],
        'timeline_pct_wig': timeline.get('pct_wig', []),
        'timeline_pct_sp500': timeline['pct_sp'],
        'timeline_pct_inflation': timeline['pct_inf'],
        'last_market_date': timeline['last_market_date'],
        'rates': rates,
        'invested': fmt_2(stats['invested']),
        'cash': fmt_2(stats['cash']),
    }

    enrich_assets_context(context, stats['assets'], stats['total_value'])

    return context


# =========================================================
# PUBLICZNY HELPER (Dla views.py i assets_list)
# =========================================================

def enrich_assets_context(context, assets, total_portfolio_value):
    """
    Przyjmuje surowe dane (float) z analytics i formatuje je (str) dla HTML.
    """
    pln_items = []
    foreign_items = []
    closed_items = []

    for a in assets:
        # Pozycje Zamknięte
        if a['is_closed']:
            closed_items.append({
                'symbol': a['symbol'],
                'name': a['name'],
                'display_name': a.get('display_name', f"{a['name']} ({a['symbol']})"),
                'gain_pln': fmt_2(a['gain_pln']),
                'gain_pln_raw': a['gain_pln'],
                'asset_type': a.get('asset_type', 'STOCK')
            })
            continue

        # Pozycje Otwarte
        days_held = 0
        if a.get('trades'):
            sorted_trades = sorted(a['trades'], key=lambda x: x['date'])
            first_trade_date = sorted_trades[0]['date'].date()
            days_held = (date.today() - first_trade_date).days

        # Tworzymy obiekt dla widoku (ViewModel)
        item = {
            'symbol': a['symbol'],
            'name': a['name'],
            'display_name': a.get('display_name', f"{a['name']} ({a['symbol']})"),
            'sector': a.get('sector', 'OTHER'),
            'asset_type': a.get('asset_type', 'STOCK'),

            'quantity': fmt_4(a['quantity']),
            'avg_price_pln': fmt_2(a['avg_price']),
            'current_price_fmt': fmt_2(a['cur_price']) + " " + a['currency'],
            'value_pln': fmt_2(a['value_pln']),
            'gain_pln': fmt_2(a['gain_pln']),
            'gain_percent': fmt_2(a['gain_percent']),
            'day_change_pct': fmt_2(a['day_change_pct']),
            'share_pct': fmt_2(a['share_pct']),

            'value_pln_raw': a['value_pln'],
            'gain_pln_raw': a['gain_pln'],
            'gain_percent_raw': a['gain_percent'],
            'day_change_pct_raw': a['day_change_pct'],
            'share_pct_raw': a['share_pct'],
            'cost_pln_raw': a['cost_pln'],

            'days_held': days_held,
            'price_date': a['price_date'],
            'is_foreign': a['is_foreign']
        }

        if a['is_foreign']:
            foreign_items.append(item)
        else:
            pln_items.append(item)

    # Sortowanie (na floatach)
    pln_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)
    foreign_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)
    closed_items.sort(key=lambda x: x['gain_pln_raw'], reverse=True)

    context['pln_items'] = pln_items
    context['foreign_items'] = foreign_items
    context['closed_items'] = closed_items

    # Podsumowania grup
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


# =========================================================
# POZOSTAŁE FUNKCJE (Chart, Details) - Bez zmian logiki
# =========================================================

def get_asset_details_context(user, symbol, portfolio_id=None):
    portfolio = get_portfolio_by_id(user, portfolio_id)
    asset = get_asset_by_symbol(symbol)
    if not portfolio or not asset: return {'symbol': symbol, 'error': 'Asset not found.'}
    all_trans = get_transactions(user, portfolio.id)
    asset_trans = all_trans.filter(asset=asset).order_by('date')
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
    first_date = asset_trans.first().date.date() if asset_trans.exists() else date.today()
    hist_df = fetch_historical_data_for_timeline([asset.yahoo_ticker], first_date)
    current_price_orig = 0.0;
    prev_close = 0.0;
    ath = 0.0;
    atl = 0.0;
    chart_dates = [];
    chart_prices = []
    try:
        if not hist_df.empty:
            series = hist_df['Close'] if not isinstance(hist_df.columns, pd.MultiIndex) else (
                hist_df[asset.yahoo_ticker]['Close'] if asset.yahoo_ticker in hist_df.columns.levels[0] else None)
            if series is not None and not series.empty:
                series = series.dropna()
                if not series.empty:
                    current_price_orig = float(series.iloc[-1])
                    prev_close = float(series.iloc[-2]) if len(series) >= 2 else current_price_orig
                    ath = float(series.max()) * multiplier
                    atl = float(series.min()) * multiplier
                    chart_dates = series.index.strftime('%Y-%m-%d').tolist()
                    chart_prices = [float(p) * multiplier for p in series.tolist()]
                else:
                    current_price_orig, prev_close = get_cached_price(asset)
            else:
                current_price_orig, prev_close = get_cached_price(asset)
        else:
            current_price_orig, prev_close = get_cached_price(asset)
    except:
        current_price_orig, prev_close = get_cached_price(asset)

    qty = asset_data['qty'];
    cost = asset_data['cost']
    if current_price_orig <= 0: current_price_orig = (cost / qty) if qty > 0 else 0
    current_value_pln = qty * current_price_orig * multiplier
    avg_price_pln = (cost / qty) if qty > 0 else 0.0
    total_gain_pln = (current_value_pln - cost) + asset_data['realized']
    profit_percent = (total_gain_pln / cost * 100) if cost > 0.01 else 0
    day_change_pct = ((current_price_orig - prev_close) / prev_close * 100) if prev_close > 0 else 0
    day_change_pln = (qty * (current_price_orig - prev_close)) * multiplier

    history_table = []
    trade_events = {}
    for t in asset_data['trades']:
        history_table.append({'date': t['date'].strftime('%Y-%m-%d'), 'type': t['type'], 'quantity': fmt_4(t['qty']),
                              'price_original': f"{t.get('price', 0):.2f}", 'currency': 'PLN',
                              'value_pln': fmt_2(abs(t['amount']))})
        if t['type'] in ['OPEN BUY', 'BUY']:
            trade_events[t['date'].strftime("%Y-%m-%d")] = 'BUY'
        elif t['type'] in ['CLOSE SELL', 'SELL', 'CLOSE']:
            trade_events[t['date'].strftime("%Y-%m-%d")] = 'SELL'

    chart_point_colors = ['#00ff7f' if d in trade_events and trade_events[
        d] == 'BUY' else '#ff4d4d' if d in trade_events else 'rgba(0,0,0,0)' for d in chart_dates]
    chart_point_radius = [6 if d in trade_events else 0 for d in chart_dates]

    return {'symbol': symbol, 'asset_name': asset.name, 'current_value_pln': fmt_2(current_value_pln),
            'avg_price': fmt_2(avg_price_pln), 'quantity': fmt_4(qty), 'gain_percent': fmt_2(profit_percent),
            'gain_percent_raw': profit_percent, 'total_gain_pln': fmt_2(total_gain_pln),
            'total_gain_pln_raw': total_gain_pln, 'current_price': fmt_2(current_price_orig * multiplier),
            'currency_sym': 'PLN', 'day_change_pct': fmt_2(day_change_pct), 'day_change_pct_raw': day_change_pct,
            'day_change_pln': fmt_2(day_change_pln), 'day_change_pln_raw': day_change_pln,
            'transactions': reversed(history_table), 'chart_dates': chart_dates, 'chart_prices': chart_prices,
            'chart_point_colors': chart_point_colors, 'chart_point_radius': chart_point_radius,
            'first_trade_date': first_date.strftime('%Y-%m-%d'), 'ath': ath, 'atl': atl, 'rates': rates}


def _get_empty_dashboard_context():
    return {'invested': "0.00", 'cash': "0.00", 'tile_value_str': "0.00", 'tile_total_profit_str': "0.00",
            'tile_return_pct_str': "0.00", 'rates': get_current_currency_rates()}


def _prepare_dashboard_charts(assets, cash):
    charts = {
        'labels': [], 'allocation': [],
        'profit_labels': [], 'profit_values': [],
        'closed_labels': [], 'closed_values': [], 'closed_items_display': [],
        'sector_labels': [], 'sector_values': [],
        'type_labels': [], 'type_values': []
    }

    sorted_assets = sorted([a for a in assets if not a['is_closed']], key=lambda x: x['value_pln'], reverse=True)

    sectors = {}
    types = {}

    for a in sorted_assets:
        charts['labels'].append(a['display_name'])
        charts['allocation'].append(a['value_pln'])
        charts['profit_labels'].append(a['symbol'])
        charts['profit_values'].append(a['gain_pln'])

        sec = a.get('sector', 'Unknown')
        typ = a.get('asset_type', 'Stock')
        val = a['value_pln']

        sectors[sec] = sectors.get(sec, 0.0) + val
        types[typ] = types.get(typ, 0.0) + val

    if cash > 1:
        charts['labels'].append("CASH")
        charts['allocation'].append(cash)
        sectors['Cash'] = sectors.get('Cash', 0.0) + cash
        types['Cash'] = types.get('Cash', 0.0) + cash

    sorted_sectors = sorted(sectors.items(), key=lambda item: item[1], reverse=True)
    for k, v in sorted_sectors:
        charts['sector_labels'].append(k)
        charts['sector_values'].append(v)

    sorted_types = sorted(types.items(), key=lambda item: item[1], reverse=True)
    for k, v in sorted_types:
        charts['type_labels'].append(k)
        charts['type_values'].append(v)

    closed = [a for a in assets if a['is_closed']]
    for a in closed:
        charts['closed_labels'].append(a['symbol'])
        charts['closed_values'].append(round(a['gain_pln'], 2))
        charts['closed_items_display'].append(
            {'symbol': a['symbol'], 'gain_pln': fmt_2(a['gain_pln']), 'gain_pln_raw': a['gain_pln']})

    return charts


def _calculate_annual_return(total_profit, invested, first_date):
    if not first_date or invested <= 0: return 0.0
    days = (date.today() - first_date).days
    total_return_pct = (total_profit / invested * 100)
    return total_return_pct / (days / 365.25) if days > 365 else total_return_pct