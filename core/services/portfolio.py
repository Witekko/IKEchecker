import math
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import QuerySet
from .config import fmt_2, fmt_4
from .market import get_cached_price, get_current_currency_rates
from ..models import Asset, Portfolio, Transaction
from .calculator import PortfolioCalculator


# =========================================================
# 1. LOGIKA DASHBOARDU I LISTY AKTYWÓW
# =========================================================

def calculate_current_holdings(transactions: QuerySet, eur_rate: float, usd_rate: float):
    # 1. Calculator
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    cash, total_invested = calc.get_cash_balance()

    # Kontenery tymczasowe
    all_assets_temp = []

    # Zmienne do globalnych sum
    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0
    unrealized_profit = 0.0
    gainers_count = 0
    losers_count = 0

    # Wykresy
    charts = {'labels': [], 'allocation': [], 'profit_labels': [], 'profit_values': [], 'closed_labels': [],
              'closed_values': []}
    closed_holdings = []

    # 2. Przetwarzanie wszystkich aktywów (Pierwszy przebieg)
    for sym, data in holdings_data.items():
        qty = data['qty']
        asset = data['asset']

        # Pozycje zamknięte
        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                closed_holdings.append({
                    'symbol': sym,
                    'gain_pln': fmt_2(data['realized']),
                    'gain_pln_raw': data['realized']
                })
                charts['closed_labels'].append(sym)
                charts['closed_values'].append(round(data['realized'], 2))
            continue

        # Pozycje otwarte
        cost = data['cost']
        cur_price, prev_close = get_cached_price(asset)

        multiplier = 1.0
        currency_sym = 'PLN'
        is_foreign = False

        if asset.currency == 'EUR':
            multiplier = eur_rate
            currency_sym = '€'
            is_foreign = True
        elif asset.currency == 'USD':
            multiplier = usd_rate
            currency_sym = '$'
            is_foreign = True
        elif asset.currency == 'GBP':
            multiplier = 5.20
            currency_sym = '£'
            is_foreign = True

        value_pln = (qty * cur_price) * multiplier
        current_position_gain = value_pln - cost
        total_gain = current_position_gain + data['realized']

        avg_price = (cost / qty) if qty > 0 else 0
        gain_percent = (total_gain / cost * 100) if cost > 0 else 0.0

        day_change_pct = ((cur_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        day_change_val = (qty * (cur_price - prev_close)) * multiplier

        if day_change_pct > 0:
            gainers_count += 1
        elif day_change_pct < 0:
            losers_count += 1

        portfolio_value_stock += value_pln
        total_day_change_pln += day_change_val
        unrealized_profit += current_position_gain

        # Dni inwestycji
        days_held = 0
        if data['trades']:
            sorted_trades = sorted(data['trades'], key=lambda x: x['date'])
            first_trade = sorted_trades[0]['date'].date()
            days_held = (date.today() - first_trade).days

        # Zapisujemy do tymczasowej listy
        all_assets_temp.append({
            'symbol': sym,
            'name': asset.name,
            'quantity': fmt_4(qty),
            'avg_price_pln': fmt_2(avg_price),
            'current_price_orig': fmt_2(cur_price),
            'current_price_fmt': f"{cur_price:.2f} {currency_sym}",
            'price_date': asset.last_updated,  # Data ceny

            'value_pln': fmt_2(value_pln),
            'value_pln_raw': value_pln,

            'gain_pln': fmt_2(total_gain),
            'gain_pln_raw': total_gain,

            'gain_percent': fmt_2(gain_percent),
            'gain_percent_raw': gain_percent,

            'day_change_pct': fmt_2(day_change_pct),
            'day_change_pct_raw': day_change_pct,

            'days_held': days_held,
            'is_foreign': is_foreign,  # FLAGA DO PODZIAŁU

            # Dane do podsumowań grup
            'cost_raw': cost,
        })

        charts['labels'].append(sym)
        charts['allocation'].append(value_pln)
        charts['profit_labels'].append(sym)
        charts['profit_values'].append(total_gain)

    # 3. Globalne Sumy
    total_portfolio_value = portfolio_value_stock + cash
    total_profit = total_portfolio_value - total_invested
    total_return_pct = (total_profit / total_invested * 100) if total_invested > 0 else 0.0

    value_yesterday = total_portfolio_value - total_day_change_pln
    portfolio_day_change_pct = (total_day_change_pln / value_yesterday * 100) if value_yesterday > 0 else 0.0

    # 4. Rozdzielanie na grupy i liczenie udziału %
    pln_group = {'items': [], 'total_val': 0.0, 'total_gain': 0.0, 'total_cost': 0.0}
    foreign_group = {'items': [], 'total_val': 0.0, 'total_gain': 0.0, 'total_cost': 0.0}

    for item in all_assets_temp:
        # Udział % w CAŁYM portfelu
        share_pct = 0.0
        if total_portfolio_value > 0:
            share_pct = (item['value_pln_raw'] / total_portfolio_value) * 100

        item['share_pct'] = fmt_2(share_pct)
        item['share_pct_raw'] = share_pct

        # Przydział do grupy
        if item['is_foreign']:
            foreign_group['items'].append(item)
            foreign_group['total_val'] += item['value_pln_raw']
            foreign_group['total_gain'] += item['gain_pln_raw']
            foreign_group['total_cost'] += item['cost_raw']
        else:
            pln_group['items'].append(item)
            pln_group['total_val'] += item['value_pln_raw']
            pln_group['total_gain'] += item['gain_pln_raw']
            pln_group['total_cost'] += item['cost_raw']

    # Sortowanie wewnątrz grup (po udziale)
    pln_group['items'].sort(key=lambda x: x['share_pct_raw'], reverse=True)
    foreign_group['items'].sort(key=lambda x: x['share_pct_raw'], reverse=True)

    # 5. Formatowanie sum dla grup
    pln_stats = {
        'value': fmt_2(pln_group['total_val']),
        'gain': fmt_2(pln_group['total_gain']),
        'gain_raw': pln_group['total_gain'],
        'return_pct': fmt_2(
            (pln_group['total_gain'] / pln_group['total_cost'] * 100) if pln_group['total_cost'] > 0 else 0),
        'share_total': fmt_2((pln_group['total_val'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0)
    }

    foreign_stats = {
        'value': fmt_2(foreign_group['total_val']),
        'gain': fmt_2(foreign_group['total_gain']),
        'gain_raw': foreign_group['total_gain'],
        'return_pct': fmt_2((foreign_group['total_gain'] / foreign_group['total_cost'] * 100) if foreign_group[
                                                                                                     'total_cost'] > 0 else 0),
        'share_total': fmt_2(
            (foreign_group['total_val'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0)
    }

    # Annual Return (uproszczony)
    annual_return_pct = 0.0
    if calc.first_date and total_invested > 0:
        days = (date.today() - calc.first_date).days
        if days > 365:
            annual_return_pct = total_return_pct / (days / 365.25)
        else:
            annual_return_pct = total_return_pct

    if cash > 1:
        charts['labels'].append("CASH")
        charts['allocation'].append(cash)

    return {
        # --- GLOBAL SUMMARY ---
        'total_value': fmt_2(total_portfolio_value),
        'total_profit': fmt_2(total_profit),
        'total_profit_raw': total_profit,
        'total_return_pct': fmt_2(total_return_pct),
        'total_return_pct_raw': total_return_pct,
        'day_change_pct': fmt_2(portfolio_day_change_pct),
        'day_change_pct_raw': portfolio_day_change_pct,
        'cash': fmt_2(cash),
        'invested': fmt_2(total_invested),

        # --- GRUPY AKTYWÓW ---
        'pln_items': pln_group['items'],
        'pln_stats': pln_stats,

        'foreign_items': foreign_group['items'],
        'foreign_stats': foreign_stats,

        'closed_holdings': closed_holdings,

        # --- DASHBOARD CHART DATA ---
        'tile_value_str': fmt_2(total_portfolio_value),
        'tile_total_profit_str': fmt_2(total_profit),
        'tile_return_pct_str': fmt_2(total_return_pct),
        'tile_day_pct_str': fmt_2(portfolio_day_change_pct),
        'tile_day_pln_str': fmt_2(total_day_change_pln),
        'tile_current_profit_str': fmt_2(unrealized_profit),
        'tile_annual_pct_str': fmt_2(annual_return_pct),
        'tile_gainers': gainers_count,
        'tile_losers': losers_count,
        'tile_value_raw': total_portfolio_value,
        'tile_total_profit_raw': total_profit,
        'tile_return_pct_raw': total_return_pct,
        'tile_day_pct_raw': portfolio_day_change_pct,
        'tile_day_pln_raw': total_day_change_pln,
        'tile_current_profit_raw': unrealized_profit,
        'tile_annual_pct_raw': annual_return_pct,
        'charts': charts
    }

# =========================================================
# 2. LOGIKA WYKRESU HISTORII (TIMELINE)
# =========================================================

def calculate_historical_timeline(transactions: QuerySet, eur_rate, usd_rate):
    if not transactions.exists(): return {}
    start_date = transactions.first().date.date()
    end_date = date.today()

    user_tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))
    benchmarks = ['^WIG', '^GSPC', 'USDPLN=X']
    all_tickers = list(set(user_tickers + benchmarks))

    try:
        hist_data = yf.download(all_tickers, start=start_date, end=end_date + timedelta(days=1), group_by='ticker',
                                progress=False, threads=True)
    except:
        hist_data = pd.DataFrame()

    sim = {'cash': 0.0, 'invested': 0.0, 'holdings': {}, 'wig_units': 0.0, 'sp500_units': 0.0, 'inflation_capital': 0.0}
    timeline = {'dates': [], 'points': [], 'val_user': [], 'val_inv': [], 'val_wig': [], 'val_sp': [], 'val_inf': [],
                'pct_user': [], 'pct_wig': [], 'pct_sp': [], 'pct_inf': []}

    trans_list = list(transactions)
    trans_idx = 0
    total_trans = len(trans_list)
    current_day = start_date

    while current_day <= end_date:
        is_deposit_day = False
        while trans_idx < total_trans and trans_list[trans_idx].date.date() <= current_day:
            t = trans_list[trans_idx]
            amt = float(t.amount)
            qty = float(t.quantity)
            if t.type == 'DEPOSIT':
                sim['cash'] += amt;
                sim['invested'] += amt;
                sim['inflation_capital'] += amt;
                is_deposit_day = True
                try:
                    p_wig = float(hist_data['^WIG']['Close'].asof(str(current_day)))
                    if p_wig > 0: sim['wig_units'] += amt / p_wig
                except:
                    pass
                try:
                    p_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                    p_sp = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
                    if p_usd > 0 and p_sp > 0: sim['sp500_units'] += (amt / p_usd) / p_sp
                except:
                    pass
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

        user_val = sim['cash']
        for tk, q in sim['holdings'].items():
            if q <= 0.0001: continue
            try:
                price = float(hist_data[tk]['Close'].asof(str(current_day)))
                if math.isnan(price): price = 0.0
                val = price * q
                if '.DE' in tk:
                    val *= eur_rate
                elif '.US' in tk:
                    hist_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                    val *= hist_usd if not math.isnan(hist_usd) else usd_rate
                user_val += val
            except:
                pass

        wig_val = 0.0
        try:
            p = float(hist_data['^WIG']['Close'].asof(str(current_day)))
            if not math.isnan(p): wig_val = sim['wig_units'] * p
        except:
            pass

        sp_val = 0.0
        try:
            p_sp = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
            p_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
            if not math.isnan(p_sp) and not math.isnan(p_usd): sp_val = sim['sp500_units'] * p_sp * p_usd
        except:
            pass

        sim['inflation_capital'] *= 1.06 ** (1 / 365)
        timeline['dates'].append(current_day.strftime("%Y-%m-%d"))
        timeline['points'].append(6 if is_deposit_day else 0)
        timeline['val_user'].append(round(user_val, 2))
        timeline['val_inv'].append(round(sim['invested'], 2))
        timeline['val_wig'].append(round(wig_val, 2) if wig_val > 0 else round(sim['invested'], 2))
        timeline['val_sp'].append(round(sp_val, 2) if sp_val > 0 else round(sim['invested'], 2))
        timeline['val_inf'].append(round(sim['inflation_capital'], 2))

        base = sim['invested'] if sim['invested'] > 0 else 1.0
        timeline['pct_user'].append(round((user_val - base) / base * 100, 2))
        timeline['pct_wig'].append(round((wig_val - base) / base * 100 if wig_val > 0 else 0, 2))
        timeline['pct_sp'].append(round((sp_val - base) / base * 100 if sp_val > 0 else 0, 2))
        timeline['pct_inf'].append(round((sim['inflation_capital'] - base) / base * 100, 2))
        current_day += timedelta(days=1)

    return timeline


# =========================================================
# 3. LOGIKA SZCZEGÓŁÓW AKTYWA (ATH, ATL, KROPKI)
# =========================================================

def get_asset_details_context(user, symbol):
    portfolio = Portfolio.objects.filter(user=user).first()
    try:
        asset = Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return {'symbol': symbol, 'error': f'Asset not found: {symbol}'}

    transactions = Transaction.objects.filter(portfolio=portfolio, asset=asset).order_by('date')

    # 1. Calculator
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    asset_data = holdings_data.get(symbol, {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'trades': []})

    # 2. Data pierwszej transakcji (dla wykresu)
    first_trade_date_str = None
    if transactions.exists():
        first_trade_date_str = transactions.first().date.strftime('%Y-%m-%d')

    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30)
    usd_rate = rates.get('USD', 4.00)
    gbp_rate = rates.get('GBP', 5.20)
    jpy_rate = rates.get('JPY', 1.0) / 100.0

    multiplier = 1.0
    if asset.currency == 'EUR':
        multiplier = eur_rate
    elif asset.currency == 'USD':
        multiplier = usd_rate
    elif asset.currency == 'GBP':
        multiplier = gbp_rate
    elif asset.currency == 'JPY':
        multiplier = jpy_rate

    # 3. Historia MAX i ATH/ATL
    current_price_orig = 0.0
    ath = 0.0
    atl = 0.0
    hist = pd.DataFrame()

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        # Pobieramy MAX, żeby mieć dane do ATH i pełnego wykresu
        hist = ticker.history(period="max")
        if not hist.empty:
            current_price_orig = float(hist['Close'].iloc[-1])
            hist.index = hist.index.strftime('%Y-%m-%d')

            # Obliczanie ATH i ATL (w PLN)
            ath = float(hist['Close'].max()) * multiplier
            atl = float(hist['Close'].min()) * multiplier
    except Exception as e:
        print(f"Error fetching details ({symbol}): {e}")
        current_price_orig, _ = get_cached_price(asset)

    qty = asset_data['qty']
    cost = asset_data['cost']
    current_value_pln = qty * current_price_orig * multiplier
    avg_price_pln = (cost / qty) if qty > 0 else 0.0

    total_gain_pln = (current_value_pln - cost) + asset_data['realized']
    profit_percent = (total_gain_pln / cost * 100) if cost > 0.01 else 0

    history_table = []
    trade_events = {}

    for t in asset_data['trades']:
        history_table.append({
            'date': t['date'].strftime('%Y-%m-%d'),
            'type': t['type'],
            'quantity': fmt_4(t['qty']),
            'price_original': f"{t['price']:.2f}",
            'currency': 'PLN',
            'value_pln': fmt_2(abs(t['amount']))
        })
        d_str = t['date'].strftime("%Y-%m-%d")
        if t['type'] in ['OPEN BUY', 'BUY']:
            trade_events[d_str] = 'BUY'
        elif t['type'] in ['CLOSE SELL', 'SELL']:
            trade_events[d_str] = 'SELL'

    # 4. Wykres
    chart_dates = []
    chart_prices = []
    chart_point_colors = []
    chart_point_radius = []

    if not hist.empty:
        all_dates = hist.index.tolist()
        all_prices = [float(p) * multiplier for p in hist['Close'].tolist()]

        for d, p in zip(all_dates, all_prices):
            chart_dates.append(d)
            chart_prices.append(p)
            if d in trade_events:
                color = '#00ff7f' if trade_events[d] == 'BUY' else '#ff4d4d'
                chart_point_colors.append(color)
                chart_point_radius.append(6)
            else:
                chart_point_colors.append('rgba(0,0,0,0)')
                chart_point_radius.append(0)
    else:
        chart_dates = [t['date'] for t in history_table]
        chart_prices = [current_price_orig * multiplier] * len(chart_dates)
        chart_point_colors = ['#00ff7f'] * len(chart_dates)
        chart_point_radius = [6] * len(chart_dates)

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
        'transactions': reversed(history_table),

        'chart_dates': chart_dates,
        'chart_prices': chart_prices,
        'chart_point_colors': chart_point_colors,
        'chart_point_radius': chart_point_radius,
        'first_trade_date': first_trade_date_str,

        # ATH/ATL
        'ath': ath,
        'atl': atl,

        'rates': rates
    }