# core/services/portfolio.py

import math
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from django.utils import timezone
from django.db.models import QuerySet
from .config import fmt_2, fmt_4
from .market import get_cached_price, get_current_currency_rates
from .news import get_asset_news
from ..models import Asset, Portfolio, Transaction

def calculate_current_holdings(transactions: QuerySet, eur_rate: float, usd_rate: float):
    assets_summary = {}
    total_invested = 0.0
    cash = 0.0
    first_transaction_date = timezone.now().date()
    has_transactions = False

    # 1. Agregacja
    for t in transactions:
        has_transactions = True
        if t.date.date() < first_transaction_date:
            first_transaction_date = t.date.date()

        amt = float(t.amount)
        qty = float(t.quantity)

        if t.type == 'DEPOSIT':
            total_invested += amt;
            cash += amt
        elif t.type == 'WITHDRAWAL':
            total_invested -= abs(amt);
            cash -= abs(amt)
        elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
            cash += amt

        if t.asset:
            s = t.asset.symbol
            if s not in assets_summary:
                assets_summary[s] = {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'obj': t.asset}

            if t.type == 'BUY':
                assets_summary[s]['qty'] += qty
                assets_summary[s]['cost'] += abs(amt)
            elif t.type == 'SELL':
                cur_qty = assets_summary[s]['qty']
                if cur_qty > 0:
                    ratio = qty / cur_qty
                    if ratio > 1: ratio = 1
                    cost_removed = assets_summary[s]['cost'] * ratio
                    assets_summary[s]['realized'] += (amt - cost_removed)
                    assets_summary[s]['qty'] -= qty
                    assets_summary[s]['cost'] -= cost_removed

    pln_holdings = []
    foreign_holdings = []
    closed_holdings = []
    charts = {'labels': [], 'allocation': [], 'profit_labels': [], 'profit_values': [], 'closed_labels': [],
              'closed_values': []}

    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0
    unrealized_profit = 0.0
    gainers_count = 0
    losers_count = 0

    # 2. Wyliczanie
    for s, data in assets_summary.items():
        qty = data['qty']
        asset = data['obj']

        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                closed_holdings.append({'symbol': s, 'gain_pln': fmt_2(data['realized'])})
                charts['closed_labels'].append(s)
                charts['closed_values'].append(round(data['realized'], 2))
            continue

        cost = data['cost']
        avg_price = cost / qty if qty > 0 else 0
        cur_price, prev_close = get_cached_price(asset)

        multiplier = 1.0
        currency_code = 'PLN'
        target_list = pln_holdings

        if asset.currency == 'EUR':
            multiplier = eur_rate
            currency_code = 'EUR'
            target_list = foreign_holdings
        elif asset.currency == 'USD':
            multiplier = usd_rate
            currency_code = 'USD'
            target_list = foreign_holdings

        value_pln = (qty * cur_price) * multiplier
        current_position_gain = value_pln - cost
        unrealized_profit += current_position_gain
        total_gain = current_position_gain + data['realized']
        gain_percent = (total_gain / cost * 100) if cost > 0 else 0

        day_change_pct = ((cur_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        day_change_val = (qty * (cur_price - prev_close)) * multiplier
        total_day_change_pln += day_change_val

        if day_change_pct > 0:
            gainers_count += 1
        elif day_change_pct < 0:
            losers_count += 1

        target_list.append({
            'symbol': s,
            'name': asset.name,
            'quantity': fmt_4(qty),
            'avg_price_pln': fmt_2(avg_price),
            'current_price_orig': fmt_2(cur_price),
            'currency': currency_code,
            'value_pln': fmt_2(value_pln),
            'value_pln_raw': value_pln,
            'gain_pln': fmt_2(total_gain),
            'gain_pln_raw': total_gain,
            'gain_percent': fmt_2(gain_percent),
            'day_change_pct': fmt_2(day_change_pct),
            'day_change_pct_raw': day_change_pct
        })

        portfolio_value_stock += value_pln
        charts['labels'].append(s)
        charts['allocation'].append(value_pln)
        charts['profit_labels'].append(s)
        charts['profit_values'].append(total_gain)

    # 3. Sumy dla tabel
    totals_pln = {
        'value': sum(x['value_pln_raw'] for x in pln_holdings),
        'gain': sum(x['gain_pln_raw'] for x in pln_holdings)
    }
    totals_foreign = {
        'value': sum(x['value_pln_raw'] for x in foreign_holdings),
        'gain': sum(x['gain_pln_raw'] for x in foreign_holdings)
    }

    totals_pln_fmt = {
        'value': fmt_2(totals_pln['value']),
        'gain': fmt_2(totals_pln['gain']),
        'gain_raw': totals_pln['gain']
    }
    totals_foreign_fmt = {
        'value': fmt_2(totals_foreign['value']),
        'gain': fmt_2(totals_foreign['gain']),
        'gain_raw': totals_foreign['gain']
    }

    if cash > 1:
        charts['labels'].append("CASH")
        charts['allocation'].append(cash)

    total_portfolio_value = portfolio_value_stock + cash
    total_profit = total_portfolio_value - total_invested

    value_yesterday = total_portfolio_value - total_day_change_pln
    portfolio_day_change_pct = (total_day_change_pln / value_yesterday * 100) if value_yesterday > 0 else 0.0
    total_return_pct = (total_profit / total_invested * 100) if total_invested > 0 else 0.0

    annual_return_pct = 0.0
    if has_transactions and total_invested > 0:
        days_investing = (date.today() - first_transaction_date).days
        if days_investing > 0:
            years = days_investing / 365.25
            if years < 1:
                annual_return_pct = total_return_pct
            else:
                annual_return_pct = total_return_pct / years

    return {
        'cash': fmt_2(cash),
        'invested': fmt_2(total_invested),
        'stock_value': fmt_2(portfolio_value_stock),

        'tile_value_raw': total_portfolio_value,
        'tile_day_pct_raw': portfolio_day_change_pct,
        'tile_total_profit_raw': total_profit,
        'tile_return_pct_raw': total_return_pct,
        'tile_day_pln_raw': total_day_change_pln,
        'tile_current_profit_raw': unrealized_profit,
        'tile_annual_pct_raw': annual_return_pct,

        'tile_value_str': fmt_2(total_portfolio_value),
        'tile_day_pct_str': fmt_2(portfolio_day_change_pct),
        'tile_total_profit_str': fmt_2(total_profit),
        'tile_return_pct_str': fmt_2(total_return_pct),
        'tile_day_pln_str': fmt_2(total_day_change_pln),
        'tile_current_profit_str': fmt_2(unrealized_profit),
        'tile_annual_pct_str': fmt_2(annual_return_pct),

        'tile_gainers': gainers_count,
        'tile_losers': losers_count,

        'pln_holdings': pln_holdings,
        'foreign_holdings': foreign_holdings,
        'closed_holdings': closed_holdings,
        'totals_pln': totals_pln_fmt,
        'totals_foreign': totals_foreign_fmt,

        'charts': charts
    }


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
                    if not math.isnan(hist_usd):
                        val *= hist_usd
                    else:
                        val *= usd_rate
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

def get_asset_details_context(user, symbol):
    """
    Przygotowuje pełne dane dla widoku szczegółów aktywa:
    historia transakcji, wykresy, newsy i zyski.
    """
    portfolio = Portfolio.objects.filter(user=user).first()
    try:
        asset = Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return {'error': f'Nie znaleziono aktywa: {symbol}'}

    transactions = Transaction.objects.filter(portfolio=portfolio, asset=asset).order_by('date')

    total_qty = 0.0
    total_cost_pln = 0.0
    history_table = []
    trade_events = {}

    for t in transactions:
        qty = float(t.quantity)
        amt = float(t.amount)

        if t.type == 'BUY':
            total_qty += qty
            total_cost_pln += abs(amt)
            trade_events[t.date.date().strftime("%Y-%m-%d")] = 'BUY'
        elif t.type == 'SELL':
            if total_qty > 0:
                ratio = qty / total_qty
                if ratio > 1: ratio = 1
                total_cost_pln -= (total_cost_pln * ratio)
                total_qty -= qty
            trade_events[t.date.date().strftime("%Y-%m-%d")] = 'SELL'

        history_table.append({
            'date': t.date, 'type': t.get_type_display(), 'quantity': fmt_4(qty),
            'amount': fmt_2(amt), 'comment': t.comment
        })

    # Pobieranie ceny i historii (Yahoo)
    current_price = 0.0
    hist = pd.DataFrame()
    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        start_date = transactions.first().date.date() if transactions.exists() else None
        if start_date:
            hist = ticker.history(start=start_date)
        else:
            hist = ticker.history(period="1mo")

        if not hist.empty:
            hist.index = hist.index.tz_localize(None)
            current_price = float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"Error fetching details ({symbol}): {e}")

    # Waluty (Teraz używamy naszego serwisu market!)
    eur_rate, usd_rate = get_current_currency_rates()
    multiplier = 1.0
    if asset.currency == 'EUR': multiplier = eur_rate
    elif asset.currency == 'USD': multiplier = usd_rate

    # Obliczenia
    avg_price = (total_cost_pln / total_qty) if total_qty > 0 else 0
    current_value_pln = (total_qty * current_price) * multiplier
    profit_pln = current_value_pln - total_cost_pln
    profit_percent = (profit_pln / total_cost_pln * 100) if total_cost_pln > 0.01 else 0

    # Wykres
    chart_dates = []
    chart_prices = []
    chart_colors = []
    chart_radius = []

    if not hist.empty:
        for date_idx, row in hist.iterrows():
            d_str = date_idx.strftime("%Y-%m-%d")
            chart_dates.append(d_str)
            chart_prices.append(float(row['Close']))

            if d_str in trade_events:
                chart_colors.append('#00ff7f' if trade_events[d_str] == 'BUY' else '#ff4d4d')
                chart_radius.append(6)
            else:
                chart_colors.append('rgba(0,0,0,0)')
                chart_radius.append(0)

    # Newsy (Używamy serwisu news!)
    news_data = get_asset_news(asset.symbol, asset.name)

    return {
        'asset': asset,
        'current_price': fmt_2(current_price),
        'qty': fmt_4(total_qty),
        'avg_price': fmt_2(avg_price),
        'value_pln': fmt_2(current_value_pln),
        'profit_pln': fmt_2(profit_pln),
        'profit_percent': fmt_2(profit_percent),
        'history': reversed(history_table),
        'currency_rate': fmt_2(multiplier) if multiplier != 1.0 else None,
        'chart_dates': chart_dates,
        'chart_prices': chart_prices,
        'chart_colors': chart_colors,
        'chart_radius': chart_radius,
        'news_list': news_data
    }