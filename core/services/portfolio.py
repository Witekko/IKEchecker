from datetime import date
from decimal import Decimal
import colorsys
import math
from .config import fmt_2, fmt_4
from .market import get_current_currency_rates, fetch_historical_data_for_timeline, get_cached_price
from .calculator import PortfolioCalculator
from .selectors import get_transactions, get_asset_by_symbol, get_portfolio_by_id
from .analytics import analyze_holdings, analyze_history

# =========================================================
# KONFIGURACJA KOLORÓW (SOFT UI PALETTE)
# =========================================================

TYPE_COLORS = {
    'STOCK': '#4DB6AC', 'ETF': '#7986CB', 'CASH': '#B0BEC5',
    'CRYPTO': '#FFB74D', 'CURRENCY': '#A1887F', 'COMMODITY': '#FFD54F', 'OTHER': '#E0E0E0'
}

SECTOR_COLORS = {
    'Technology': '#42A5F5', 'Financial': '#66BB6A', 'Financial Services': '#66BB6A',
    'Healthcare': '#EC407A', 'Consumer Cyclical': '#26C6DA', 'Consumer Defensive': '#26A69A',
    'Communication Services': '#AB47BC', 'Energy': '#FFA726', 'Industrials': '#8D6E63',
    'Utilities': '#FDD835', 'Real Estate': '#D4E157', 'Basic Materials': '#78909C',
    'Cash': '#B0BEC5', 'Other': '#BDBDBD'
}

DEFAULT_COLOR = '#CFD8DC'


def _adjust_color_lightness(hex_color, factor):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(*rgb)
        new_l = max(0.2, min(0.85, l * factor))
        r, g, b = colorsys.hls_to_rgb(h, new_l, s)
        return '#%02x%02x%02x' % (int(r * 255), int(g * 255), int(b * 255))
    except:
        return hex_color


def _generate_sector_shades(base_color, count):
    if count <= 1: return [base_color]
    shades = []
    for i in range(count):
        factor = 0.9 + (i * (0.5 / count))
        shades.append(_adjust_color_lightness(base_color, factor))
    return shades


# =========================================================
# GŁÓWNY KONTEKST DASHBOARDU
# =========================================================

def get_dashboard_context(user, portfolio_id=None):
    transactions = get_transactions(user, portfolio_id)
    if not transactions.exists():
        return _get_empty_dashboard_context()

    rates = get_current_currency_rates()
    stats = analyze_holdings(transactions, rates)
    timeline = analyze_history(transactions, rates)
    charts = _prepare_dashboard_charts(stats['assets'], stats['cash'])
    annual_ret = _calculate_annual_return(stats['total_profit'], stats['invested'], stats['first_date'])
    last_transactions = transactions.order_by('-date')[:20]

    closed_assets = [a for a in stats['assets'] if a['is_closed']]
    win_count = sum(1 for a in closed_assets if a['gain_pln'] > 0)
    loss_count = sum(1 for a in closed_assets if a['gain_pln'] <= 0)
    total_closed = len(closed_assets)
    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0
    realized_pln = sum(a['gain_pln'] for a in closed_assets)

    best_trade, worst_trade = None, None
    if closed_assets:
        sorted_closed = sorted(closed_assets, key=lambda x: x['gain_percent'], reverse=True)
        b, w = sorted_closed[0], sorted_closed[-1]
        best_trade = {'symbol': b['symbol'], 'gain_fmt': fmt_2(b['gain_pln']), 'pct_fmt': fmt_2(b['gain_percent'])}
        worst_trade = {'symbol': w['symbol'], 'gain_fmt': fmt_2(w['gain_pln']), 'pct_fmt': fmt_2(w['gain_percent'])}

    day_pln = stats['day_change_pln']
    prev_val = stats['total_value'] - day_pln
    day_pct = (day_pln / prev_val * 100) if prev_val > 0.01 else 0.0

    context = {
        'tile_value_str': fmt_2(stats['total_value']),
        'tile_total_profit_str': fmt_2(stats['total_profit']),
        'tile_total_profit_raw': stats['total_profit'],
        'tile_return_pct_str': fmt_2((stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0),
        'tile_return_pct_raw': (stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0,
        'tile_day_pln_str': fmt_2(day_pln), 'tile_day_pln_raw': day_pln,
        'tile_day_pct_str': fmt_2(day_pct), 'tile_day_pct_raw': day_pct,
        'tile_gainers': stats['gainers'], 'tile_losers': stats['losers'],
        'tile_current_profit_str': fmt_2(stats['unrealized_profit']),
        'tile_current_profit_raw': stats['unrealized_profit'],
        'tile_annual_pct_str': fmt_2(annual_ret),
        'perf_win_rate': round(win_rate, 1), 'perf_win_count': win_count, 'perf_loss_count': loss_count,
        'perf_total_realized': fmt_2(realized_pln), 'perf_total_realized_raw': realized_pln,
        'perf_best_trade': best_trade, 'perf_worst_trade': worst_trade, 'perf_total_closed': total_closed,
        'chart_labels': charts['labels'], 'chart_allocation': charts['allocation'], 'chart_colors': charts['colors'],
        'chart_sector_labels': charts['sector_labels'], 'chart_sector_values': charts['sector_values'],
        'chart_sector_colors': charts['sector_colors'],
        'chart_type_labels': charts['type_labels'], 'chart_type_values': charts['type_values'],
        'chart_type_colors': charts['type_colors'],
        'chart_profit_labels': charts['profit_labels'], 'chart_profit_values': charts['profit_values'],
        'last_transactions': last_transactions,
        'timeline_dates': timeline['dates'], 'timeline_total_value': timeline['val_user'],
        'timeline_invested': timeline['val_inv'], 'timeline_deposit_points': timeline['points'],
        'timeline_pct_user': timeline['pct_user'], 'timeline_pct_wig': timeline.get('pct_wig', []),
        'timeline_pct_sp500': timeline['pct_sp'], 'timeline_pct_inflation': timeline['pct_inf'],
        'last_market_date': timeline['last_market_date'], 'rates': rates
    }
    enrich_assets_context(context, stats['assets'], stats['total_value'])
    return context


def _prepare_dashboard_charts(assets, cash):
    charts = {'labels': [], 'allocation': [], 'colors': [], 'sector_labels': [], 'sector_values': [],
              'sector_colors': [],
              'type_labels': [], 'type_values': [], 'type_colors': [], 'profit_labels': [], 'profit_values': []}
    open_assets = [a for a in assets if not a['is_closed']]
    assets_by_sector = {}
    for a in open_assets:
        sec = a.get('sector', 'Other')
        if sec not in SECTOR_COLORS:
            if 'Financial' in sec:
                sec = 'Financial'
            elif 'Consumer' in sec:
                sec = 'Consumer Cyclical' if 'Cyclical' in sec else 'Consumer Defensive'
            elif 'Technology' in sec:
                sec = 'Technology'
            else:
                sec = 'Other'
        if sec not in assets_by_sector: assets_by_sector[sec] = []
        assets_by_sector[sec].append(a)
    if cash > 1: assets_by_sector['Cash'] = [
        {'symbol': 'CASH', 'display_name': 'Cash', 'value_pln': cash, 'gain_pln': 0, 'asset_type': 'CASH',
         'sector': 'Cash'}]

    sector_sums = {k: sum(x['value_pln'] for x in v) for k, v in assets_by_sector.items()}
    sorted_sectors = sorted(sector_sums.items(), key=lambda x: x[1], reverse=True)
    sectors_agg, types_agg = {}, {}

    for sec_name, _ in sorted_sectors:
        group = assets_by_sector[sec_name]
        group.sort(key=lambda x: x['value_pln'], reverse=True)
        base_color = SECTOR_COLORS.get(sec_name, DEFAULT_COLOR)
        shades = _generate_sector_shades(base_color, len(group))
        for i, asset in enumerate(group):
            charts['labels'].append(asset.get('display_name', 'Cash'))
            charts['allocation'].append(asset['value_pln'])
            charts['colors'].append(shades[i])
            if asset['symbol'] != 'CASH':
                charts['profit_labels'].append(asset['symbol'])
                charts['profit_values'].append(asset['gain_pln'])
            sectors_agg[sec_name] = sectors_agg.get(sec_name, 0.0) + asset['value_pln']
            t = asset.get('asset_type', 'OTHER')
            types_agg[t] = types_agg.get(t, 0.0) + asset['value_pln']

    for k, v in sorted(sectors_agg.items(), key=lambda x: x[1], reverse=True):
        charts['sector_labels'].append(k);
        charts['sector_values'].append(v);
        charts['sector_colors'].append(SECTOR_COLORS.get(k, DEFAULT_COLOR))
    for k, v in sorted(types_agg.items(), key=lambda x: x[1], reverse=True):
        charts['type_labels'].append(k);
        charts['type_values'].append(v);
        charts['type_colors'].append(TYPE_COLORS.get(k, DEFAULT_COLOR))
    return charts


def enrich_assets_context(context, assets, total_portfolio_value):
    pln_items, foreign_items, closed_items = [], [], []
    for a in assets:
        if a['is_closed']:
            closed_items.append(
                {'symbol': a['symbol'], 'name': a['name'], 'display_name': a.get('display_name', f"{a['name']}"),
                 'gain_pln': fmt_2(a['gain_pln']), 'gain_pln_raw': a['gain_pln'],
                 'gain_percent': fmt_2(a['gain_percent']),
                 'gain_percent_raw': a['gain_percent'], 'close_date': a['price_date'],
                 'asset_type': a.get('asset_type', 'STOCK')})
            continue
        days_held = 0
        if a.get('trades'): days_held = (
                    date.today() - sorted(a['trades'], key=lambda x: x['date'])[0]['date'].date()).days
        item = {
            'symbol': a['symbol'], 'name': a['name'], 'display_name': a.get('display_name', f"{a['name']}"),
            'sector': a.get('sector', 'OTHER'),
            'asset_type': a.get('asset_type', 'STOCK'), 'quantity': fmt_4(a['quantity']),
            'avg_price_pln': fmt_2(a['avg_price']),
            'current_price_fmt': fmt_2(a['cur_price']) + " " + a['currency'], 'value_pln': fmt_2(a['value_pln']),
            'gain_pln': fmt_2(a['gain_pln']),
            'gain_percent': fmt_2(a['gain_percent']), 'day_change_pct': fmt_2(a['day_change_pct']),
            'day_change_pln': a.get('day_change_pln', 0.0),
            'first_buy_date': (sorted(a['trades'], key=lambda x: x['date'])[0]['date'].date()) if a.get(
                'trades') else None,
            'share_pct': fmt_2(a['share_pct']), 'value_pln_raw': a['value_pln'], 'gain_pln_raw': a['gain_pln'],
            'gain_percent_raw': a['gain_percent'], 'day_change_pct_raw': a['day_change_pct'],
            'share_pct_raw': a['share_pct'],
            'cost_pln_raw': a['cost_pln'], 'days_held': days_held, 'price_date': a['price_date'],
            'is_foreign': a['is_foreign']
        }
        if a['is_foreign']:
            foreign_items.append(item)
        else:
            pln_items.append(item)

    pln_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)
    foreign_items.sort(key=lambda x: x['share_pct_raw'], reverse=True)
    closed_items.sort(key=lambda x: x['gain_pln_raw'], reverse=True)

    def stats(items):
        if not items: return {'value': "0.00", 'share_total': "0.00", 'return_pct': "0.00", 'gain': "0.00",
                              'gain_raw': 0}
        v = sum(x['value_pln_raw'] for x in items);
        c = sum(x['cost_pln_raw'] for x in items);
        g = sum(x['gain_pln_raw'] for x in items)
        return {'value': fmt_2(v), 'gain': fmt_2(g), 'gain_raw': g, 'return_pct': fmt_2((g / c * 100) if c > 0 else 0),
                'share_total': fmt_2((v / total_portfolio_value * 100) if total_portfolio_value > 0 else 0)}

    context['pln_items'] = pln_items
    context['foreign_items'] = foreign_items
    context['closed_items'] = closed_items
    context['pln_stats'] = stats(pln_items)
    context['foreign_stats'] = stats(foreign_items)


def _get_empty_dashboard_context():
    return {'invested': "0.00", 'tile_value_str': "0.00", 'tile_total_profit_str': "0.00",
            'rates': get_current_currency_rates()}


def _calculate_annual_return(total_profit, invested, first_date):
    if not first_date or invested <= 0: return 0.0
    days = (date.today() - first_date).days
    return (total_profit / invested * 100) / (days / 365.25) if days > 365 else (total_profit / invested * 100)


def get_asset_details_context(user, symbol, portfolio_id=None):
    portfolio = get_portfolio_by_id(user, portfolio_id)
    asset = get_asset_by_symbol(symbol)
    if not portfolio or not asset: return {'symbol': symbol, 'error': 'Asset not found.'}
    all_trans = get_transactions(user, portfolio.id)
    asset_trans = all_trans.filter(asset=asset).order_by('date')
    holdings = PortfolioCalculator(asset_trans).process().get_holdings()
    asset_data = holdings.get(symbol, {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'trades': []})
    rates = get_current_currency_rates()
    multiplier = rates.get(asset.currency, 1.0) if asset.currency != 'PLN' else 1.0
    if asset.currency == 'JPY': multiplier /= 100.0
    first_date = asset_trans.first().date.date() if asset_trans.exists() else date.today()

    current_price_orig, prev_close = 0.0, 0.0
    chart_dates, chart_prices = [], []
    try:
        hist_df = fetch_historical_data_for_timeline([asset.yahoo_ticker], first_date)
        if not hist_df.empty and asset.yahoo_ticker in hist_df.columns.levels[0]:
            series = hist_df[asset.yahoo_ticker]['Close'].dropna()
            current_price_orig = float(series.iloc[-1])
            prev_close = float(series.iloc[-2]) if len(series) >= 2 else current_price_orig
            chart_dates = [d.strftime('%Y-%m-%d') for d in series.index]
            chart_prices = [float(p) * multiplier for p in series.tolist()]
        else:
            current_price_orig, prev_close = get_cached_price(asset)
    except:
        current_price_orig, prev_close = get_cached_price(asset)

    qty, cost = asset_data['qty'], asset_data['cost']
    if current_price_orig <= 0: current_price_orig = (cost / qty) if qty > 0 else 0
    cur_val_pln = qty * current_price_orig * multiplier
    total_gain = (cur_val_pln - cost) + asset_data['realized']
    day_change_pln = (qty * (current_price_orig - prev_close)) * multiplier

    history_table = []
    trade_events = {}
    for t in asset_data['trades']:
        history_table.append({'date': t['date'].strftime('%Y-%m-%d'), 'type': t['type'], 'quantity': fmt_4(t['qty']),
                              'price_original': f"{t.get('price', 0):.2f}", 'value_pln': fmt_2(abs(t['amount']))})
        d_str = t['date'].strftime("%Y-%m-%d")
        trade_events[d_str] = 'BUY' if 'BUY' in t['type'] else 'SELL'

    chart_colors, chart_radius = [], []
    for d in chart_dates:
        col = '#00ff7f' if trade_events.get(d) == 'BUY' else (
            '#ff4d4d' if trade_events.get(d) == 'SELL' else 'rgba(0,0,0,0)')
        chart_colors.append(col);
        chart_radius.append(6 if trade_events.get(d) else 0)

    return {
        'symbol': symbol, 'asset_name': asset.name, 'current_value_pln': fmt_2(cur_val_pln),
        'avg_price': fmt_2(cost / qty if qty > 0 else 0), 'quantity': fmt_4(qty),
        'gain_percent': fmt_2((total_gain / cost * 100) if cost > 0 else 0),
        'gain_percent_raw': (total_gain / cost * 100) if cost > 0 else 0,
        'total_gain_pln': fmt_2(total_gain), 'total_gain_pln_raw': total_gain,
        'current_price': fmt_2(current_price_orig * multiplier), 'currency_sym': 'PLN',
        'day_change_pct': fmt_2(((current_price_orig - prev_close) / prev_close * 100) if prev_close > 0 else 0),
        'day_change_pln': fmt_2(day_change_pln), 'transactions': reversed(history_table),
        'chart_dates': chart_dates, 'chart_prices': chart_prices, 'chart_point_colors': chart_colors,
        'chart_point_radius': chart_radius,
        'first_trade_date': first_date.strftime('%Y-%m-%d'),  # <-- NAPRAWIONE: Używamy first_date
        'rates': rates
    }


# =========================================================
# ASSETS LIST VIEW (FUNKCJA ODPOWIEDZIALNA ZA TABELĘ HOLDINGS)
# =========================================================
def get_assets_view_context(user, portfolio_id=None):
    transactions = get_transactions(user, portfolio_id)
    if not transactions.exists(): return {'pln_items': [], 'foreign_items': [], 'closed_items': [],
                                          'tile_value_str': "0.00"}

    rates = get_current_currency_rates()
    stats = analyze_holdings(transactions, rates)
    day_pln = stats['day_change_pln']
    prev_val = stats['total_value'] - day_pln

    context = {
        'tile_value_str': fmt_2(stats['total_value']),
        'tile_total_profit_str': fmt_2(stats['total_profit']), 'tile_total_profit_raw': stats['total_profit'],
        'tile_return_pct_str': fmt_2((stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0),
        'tile_return_pct_raw': (stats['total_profit'] / stats['invested'] * 100) if stats['invested'] > 0 else 0,
        'tile_day_pln_str': fmt_2(day_pln),
        'tile_day_pct_str': fmt_2((day_pln / prev_val * 100) if prev_val > 0.01 else 0),
        'tile_twr': "0.00", 'tile_mwr': "0.00", 'rates': rates
    }
    enrich_assets_context(context, stats['assets'], stats['total_value'])
    return context