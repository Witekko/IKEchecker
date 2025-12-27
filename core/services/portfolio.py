import math
import pandas as pd
import yfinance as yf
from datetime import date, timedelta
from django.db.models import QuerySet
from .config import fmt_2, fmt_4
from .market import get_cached_price, get_current_currency_rates
from ..models import Portfolio, Transaction, Asset
from .calculator import PortfolioCalculator


# =========================================================
# 1. GŁÓWNY KONTEKST DASHBOARDU
# =========================================================

def get_dashboard_context(user, portfolio_id=None):
    if portfolio_id:
        transactions = Transaction.objects.filter(portfolio_id=portfolio_id).order_by('date')
    else:
        transactions = Transaction.objects.filter(portfolio__user=user).order_by('date')

    if not transactions.exists():
        return {
            'invested': "0.00", 'cash': "0.00", 'stock_value': "0.00",
            'tile_value_str': "0.00", 'tile_total_profit_str': "0.00",
            'tile_return_pct_str': "0.00", 'tile_day_pct_str': "0.00",
            'tile_day_pln_str': "0.00", 'tile_current_profit_str': "0.00",
            'tile_annual_pct_str': "0.00",
            'tile_gainers': 0, 'tile_losers': 0,
            'rates': get_current_currency_rates()
        }

    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30)
    usd_rate = rates.get('USD', 4.00)

    # 3. Wyliczenia
    context = calculate_current_holdings(transactions, eur_rate, usd_rate)

    # 4. Wykres
    timeline = calculate_historical_timeline(transactions, eur_rate, usd_rate)

    full_context = {
        'rates': rates,
        'timeline_dates': timeline.get('dates', []),
        'timeline_total_value': timeline.get('val_user', []),
        'timeline_invested': timeline.get('val_inv', []),
        'timeline_deposit_points': timeline.get('points', []),
        'timeline_pct_user': timeline.get('pct_user', []),
        'timeline_pct_wig': timeline.get('pct_wig', []),
        'timeline_pct_sp500': timeline.get('pct_sp', []),
        'timeline_pct_inflation': timeline.get('pct_inf', []),
        'last_market_date': timeline.get('last_market_date', 'N/A'),

        'chart_labels': context['charts']['labels'],
        'chart_allocation': context['charts']['allocation'],
        'chart_profit_labels': context['charts']['profit_labels'],
        'chart_profit_values': context['charts']['profit_values'],
        'closed_labels': context['charts']['closed_labels'],
        'closed_values': context['charts']['closed_values'],
    }

    full_context.update(context)
    return full_context


# =========================================================
# 2. OBLICZENIA STANU PORTFELA
# =========================================================

def calculate_current_holdings(transactions: QuerySet, eur_rate: float, usd_rate: float):
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    cash, total_invested = calc.get_cash_balance()

    all_assets_temp = []
    closed_holdings = []
    charts = {'labels': [], 'allocation': [], 'profit_labels': [], 'profit_values': [], 'closed_labels': [],
              'closed_values': []}

    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0
    unrealized_profit = 0.0
    gainers_count = 0
    losers_count = 0

    for sym, data in holdings_data.items():
        qty = data['qty']
        asset = data['asset']

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

        cost = data['cost']

        # Pobieramy cenę (funkcja w market.py jest już bezpieczna na NaN)
        cur_price, prev_close = get_cached_price(asset)

        # OSTATECZNE ZABEZPIECZENIE PRZED NAN W PORTFOLIO
        # Jeśli mimo wszystko przyjdzie 0 lub NaN, system nie może paść.
        if cur_price is None or math.isnan(cur_price) or cur_price <= 0:
            # Jeśli nie ma ceny, bierzemy koszt zakupu jako fallback,
            # ALE w nowym market.py get_cached_price szuka 30 dni wstecz, więc to się nie powinno zdarzyć.
            cur_price = (cost / qty) if qty > 0 else 0
            prev_close = cur_price

        multiplier = 1.0
        currency_sym = 'PLN'
        is_foreign = False

        if asset.currency == 'EUR':
            multiplier = eur_rate;
            currency_sym = '€';
            is_foreign = True
        elif asset.currency == 'USD':
            multiplier = usd_rate;
            currency_sym = '$';
            is_foreign = True
        elif asset.currency == 'GBP':
            multiplier = 5.20;
            currency_sym = '£';
            is_foreign = True

        # Zabezpieczenie kursu walut przed NaN
        if math.isnan(multiplier): multiplier = 1.0

        value_pln = (qty * cur_price) * multiplier
        current_position_gain = value_pln - cost
        total_gain = current_position_gain + data['realized']

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

        days_held = 0
        if data['trades']:
            sorted_trades = sorted(data['trades'], key=lambda x: x['date'])
            days_held = (date.today() - sorted_trades[0]['date'].date()).days

        avg_price = (cost / qty) if qty > 0 else 0

        all_assets_temp.append({
            'symbol': sym, 'name': asset.name, 'quantity': fmt_4(qty),
            'avg_price_pln': fmt_2(avg_price), 'current_price_orig': fmt_2(cur_price),
            'current_price_fmt': f"{cur_price:.2f} {currency_sym}", 'price_date': asset.last_updated,
            'value_pln': fmt_2(value_pln), 'value_pln_raw': value_pln,
            'gain_pln': fmt_2(total_gain), 'gain_pln_raw': total_gain,
            'gain_percent': fmt_2(gain_percent), 'gain_percent_raw': gain_percent,
            'day_change_pct': fmt_2(day_change_pct), 'day_change_pct_raw': day_change_pct,
            'days_held': days_held, 'is_foreign': is_foreign, 'cost_raw': cost,
        })

        charts['labels'].append(sym)
        charts['allocation'].append(value_pln)
        charts['profit_labels'].append(sym)
        charts['profit_values'].append(total_gain)

    total_portfolio_value = portfolio_value_stock + cash
    total_profit = total_portfolio_value - total_invested
    total_return_pct = (total_profit / total_invested * 100) if total_invested > 0 else 0.0

    value_yesterday = total_portfolio_value - total_day_change_pln
    portfolio_day_change_pct = (total_day_change_pln / value_yesterday * 100) if value_yesterday > 0 else 0.0

    pln_group = {'items': [], 'total_val': 0.0, 'total_gain': 0.0, 'total_cost': 0.0}
    foreign_group = {'items': [], 'total_val': 0.0, 'total_gain': 0.0, 'total_cost': 0.0}

    for item in all_assets_temp:
        share_pct = (item['value_pln_raw'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0.0
        item['share_pct'] = fmt_2(share_pct);
        item['share_pct_raw'] = share_pct
        if item['is_foreign']:
            foreign_group['items'].append(item);
            foreign_group['total_val'] += item['value_pln_raw']
            foreign_group['total_gain'] += item['gain_pln_raw'];
            foreign_group['total_cost'] += item['cost_raw']
        else:
            pln_group['items'].append(item);
            pln_group['total_val'] += item['value_pln_raw']
            pln_group['total_gain'] += item['gain_pln_raw'];
            pln_group['total_cost'] += item['cost_raw']

    pln_group['items'].sort(key=lambda x: x['share_pct_raw'], reverse=True)
    foreign_group['items'].sort(key=lambda x: x['share_pct_raw'], reverse=True)

    pln_stats = {
        'value': fmt_2(pln_group['total_val']), 'gain': fmt_2(pln_group['total_gain']),
        'gain_raw': pln_group['total_gain'],
        'return_pct': fmt_2(
            (pln_group['total_gain'] / pln_group['total_cost'] * 100) if pln_group['total_cost'] > 0 else 0),
        'share_total': fmt_2((pln_group['total_val'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0)
    }
    foreign_stats = {
        'value': fmt_2(foreign_group['total_val']), 'gain': fmt_2(foreign_group['total_gain']),
        'gain_raw': foreign_group['total_gain'],
        'return_pct': fmt_2((foreign_group['total_gain'] / foreign_group['total_cost'] * 100) if foreign_group[
                                                                                                     'total_cost'] > 0 else 0),
        'share_total': fmt_2(
            (foreign_group['total_val'] / total_portfolio_value * 100) if total_portfolio_value > 0 else 0)
    }

    annual_return_pct = 0.0
    if calc.first_date and total_invested > 0:
        days = (date.today() - calc.first_date).days
        if days > 365:
            annual_return_pct = total_return_pct / (days / 365.25)
        else:
            annual_return_pct = total_return_pct

    if cash > 1:
        charts['labels'].append("CASH");
        charts['allocation'].append(cash)

    return {
        'total_value': fmt_2(total_portfolio_value), 'total_profit': fmt_2(total_profit),
        'total_profit_raw': total_profit,
        'total_return_pct': fmt_2(total_return_pct), 'total_return_pct_raw': total_return_pct,
        'day_change_pct': fmt_2(portfolio_day_change_pct), 'day_change_pct_raw': portfolio_day_change_pct,
        'cash': fmt_2(cash), 'invested': fmt_2(total_invested),
        'pln_items': pln_group['items'], 'pln_stats': pln_stats,
        'foreign_items': foreign_group['items'], 'foreign_stats': foreign_stats,
        'closed_holdings': closed_holdings,
        'tile_value_str': fmt_2(total_portfolio_value), 'tile_total_profit_str': fmt_2(total_profit),
        'tile_return_pct_str': fmt_2(total_return_pct), 'tile_day_pct_str': fmt_2(portfolio_day_change_pct),
        'tile_day_pln_str': fmt_2(total_day_change_pln), 'tile_current_profit_str': fmt_2(unrealized_profit),
        'tile_annual_pct_str': fmt_2(annual_return_pct), 'tile_gainers': gainers_count, 'tile_losers': losers_count,
        'tile_value_raw': total_portfolio_value, 'tile_total_profit_raw': total_profit,
        'tile_return_pct_raw': total_return_pct, 'tile_day_pct_raw': portfolio_day_change_pct,
        'tile_day_pln_raw': total_day_change_pln, 'tile_current_profit_raw': unrealized_profit,
        'tile_annual_pct_raw': annual_return_pct,
        'charts': charts
    }


# =========================================================
# 3. WYKRES TIMELINE (BEZ WIG, BEZPIECZNA HISTORIA)
# =========================================================

def calculate_historical_timeline(transactions: QuerySet, eur_rate, usd_rate):
    if not transactions.exists(): return {}

    # Sortowanie transakcji
    sorted_trans = transactions.order_by('date')
    start_date = sorted_trans.first().date.date()
    end_date = date.today()

    # --- FIX NA PRZYSZŁOŚĆ ---
    # Cofamy datę startu pobierania danych na 2 lata wstecz,
    # żeby na pewno złapać "koniec danych" w Yahoo (który jest w 2024/2025).
    safe_download_start = start_date - timedelta(days=730)

    user_tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))
    # USUNIĘTO ^WIG z listy benchmarków, bo robi problemy
    benchmarks = ['^GSPC', 'USDPLN=X']
    all_tickers = list(set(user_tickers + benchmarks))

    hist_data = pd.DataFrame()
    last_market_date_str = "Waiting for data..."  # Domyślny tekst

    try:
        # threads=False dla stabilności
        hist_data = yf.download(
            all_tickers,
            start=safe_download_start,
            end=end_date + timedelta(days=1),
            group_by='ticker',
            progress=False,
            threads=False
        )
        if not hist_data.empty:
            # Pobieramy ostatni indeks (Timestamp)
            last_idx = hist_data.index[-1]
            # Formatujemy na czytelny string: np. "27 Dec 2024"
            last_market_date_str = last_idx.strftime('%d %b %Y')
    except:
        hist_data = pd.DataFrame()

    # Helper: Pobiera cenę z danego dnia. Jeśli brak -> bierze ostatnią dostępną (ffill)
    # TO JEST KLUCZOWE: .asof() szuka w tył!
    def get_price_ffill(ticker, query_date):
        if hist_data.empty: return 0.0
        try:
            if isinstance(hist_data.columns, pd.MultiIndex):
                if ticker not in hist_data.columns.levels[0]: return 0.0
                series = hist_data[ticker]['Close']
            else:
                if ticker != all_tickers[0]: return 0.0
                series = hist_data['Close']

            # .asof() zwróci ostatnią znaną cenę przed query_date.
            # Jeśli query_date to 2025, a dane kończą się w 2024, zwróci cenę z 2024.
            val = series.asof(str(query_date))
            return float(val) if not pd.isna(val) else 0.0
        except:
            return 0.0

    sim = {'cash': 0.0, 'invested': 0.0, 'holdings': {}, 'sp500_units': 0.0, 'inflation_capital': 0.0}
    timeline = {'dates': [], 'points': [], 'val_user': [], 'val_inv': [], 'val_sp': [], 'val_inf': [], 'pct_user': [],
                'pct_sp': [], 'pct_inf': [], 'last_market_date': last_market_date_str}

    trans_list = list(sorted_trans)
    trans_idx = 0
    total_trans = len(trans_list)
    current_day = start_date

    while current_day <= end_date:
        is_deposit_day = False
        while trans_idx < total_trans and trans_list[trans_idx].date.date() <= current_day:
            t = trans_list[trans_idx];
            amt = float(t.amount);
            qty = float(t.quantity)

            if t.type == 'DEPOSIT':
                sim['cash'] += amt;
                sim['invested'] += amt;
                sim['inflation_capital'] += amt;
                is_deposit_day = True
                p_usd = get_price_ffill('USDPLN=X', current_day);
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

        user_val = sim['cash']
        for tk, q in sim['holdings'].items():
            if q <= 0.0001: continue

            # Pobieramy cenę historyczną (ostatnią dostępną)
            price = get_price_ffill(tk, current_day)

            if price > 0:
                val = price * q
                if '.DE' in tk:
                    # Zabezpieczenie eur_rate przed nan
                    if math.isnan(eur_rate):
                        val *= 4.30
                    else:
                        val *= eur_rate
                elif '.US' in tk or '.UK' in tk:
                    hist_usd = get_price_ffill('USDPLN=X', current_day)
                    # Zabezpieczenie usd_rate
                    fallback_usd = usd_rate if not math.isnan(usd_rate) else 4.00
                    val *= hist_usd if hist_usd > 0 else fallback_usd
                user_val += val

        sp_val = 0.0
        p_sp = get_price_ffill('^GSPC', current_day);
        p_usd = get_price_ffill('USDPLN=X', current_day)
        if p_sp > 0 and p_usd > 0: sp_val = sim['sp500_units'] * p_sp * p_usd

        sim['inflation_capital'] *= 1.06 ** (1 / 365)

        timeline['dates'].append(current_day.strftime("%Y-%m-%d"))
        timeline['points'].append(6 if is_deposit_day else 0)
        timeline['val_user'].append(round(user_val, 2))
        timeline['val_inv'].append(round(sim['invested'], 2))
        timeline['val_sp'].append(round(sp_val, 2) if sp_val > 0 else round(sim['invested'], 2))
        timeline['val_inf'].append(round(sim['inflation_capital'], 2))

        base = sim['invested'] if sim['invested'] > 0 else 1.0
        timeline['pct_user'].append(round((user_val - base) / base * 100, 2))
        timeline['pct_sp'].append(round((sp_val - base) / base * 100 if sp_val > 0 else 0, 2))
        timeline['pct_inf'].append(round((sim['inflation_capital'] - base) / base * 100, 2))

        current_day += timedelta(days=1)

    return timeline


# =========================================================
# 4. SZCZEGÓŁY AKTYWA (ATH/ATL, Wykres)
# =========================================================

def get_asset_details_context(user, symbol, portfolio_id=None):
    if portfolio_id:
        portfolio = Portfolio.objects.filter(id=portfolio_id, user=user).first()
    else:
        portfolio = Portfolio.objects.filter(user=user).first()

    if not portfolio: return {'symbol': symbol, 'error': 'No portfolio found.'}
    try:
        asset = Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return {'symbol': symbol, 'error': f'Asset not found: {symbol}'}

    transactions = Transaction.objects.filter(portfolio=portfolio, asset=asset).order_by('date')
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    asset_data = holdings_data.get(symbol, {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'trades': []})

    first_trade_date_str = transactions.first().date.strftime('%Y-%m-%d') if transactions.exists() else None
    rates = get_current_currency_rates()
    eur_rate = rates.get('EUR', 4.30);
    usd_rate = rates.get('USD', 4.00);
    gbp_rate = rates.get('GBP', 5.20);
    jpy_rate = rates.get('JPY', 1.0) / 100.0

    multiplier = 1.0
    currency_sym = 'PLN'
    if asset.currency == 'EUR':
        multiplier = eur_rate; currency_sym = '€'
    elif asset.currency == 'USD':
        multiplier = usd_rate; currency_sym = '$'
    elif asset.currency == 'GBP':
        multiplier = gbp_rate; currency_sym = '£'
    elif asset.currency == 'JPY':
        multiplier = jpy_rate
    if math.isnan(multiplier): multiplier = 1.0

    # 1. Historia i Cena
    current_price_orig = 0.0
    prev_close = 0.0
    ath = 0.0;
    atl = 0.0;
    hist = pd.DataFrame()

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        hist = ticker.history(period="2y")
        if not hist.empty:
            current_price_orig = float(hist['Close'].iloc[-1])
            # Do obliczenia 1D change
            if len(hist) >= 2:
                prev_close = float(hist['Close'].iloc[-2])
            else:
                prev_close = current_price_orig

            hist.index = hist.index.strftime('%Y-%m-%d')
            ath = float(hist['Close'].max()) * multiplier
            atl = float(hist['Close'].min()) * multiplier
    except Exception as e:
        print(f"Error fetching details ({symbol}): {e}")
        # Fallback do cache
        current_price_orig, prev_close = get_cached_price(asset)

    qty = asset_data['qty'];
    cost = asset_data['cost']

    # Fallback ceny
    if current_price_orig <= 0 or math.isnan(current_price_orig):
        current_price_orig = (cost / qty) if qty > 0 else 0
        prev_close = current_price_orig

    # 2. Obliczenia Finansowe
    current_value_pln = qty * current_price_orig * multiplier
    avg_price_pln = (cost / qty) if qty > 0 else 0.0
    total_gain_pln = (current_value_pln - cost) + asset_data['realized']
    profit_percent = (total_gain_pln / cost * 100) if cost > 0.01 else 0

    # --- NOWOŚĆ: Obliczanie 1D Change ---
    day_change_pct = 0.0
    day_change_pln = 0.0
    if prev_close > 0:
        day_change_pct = ((current_price_orig - prev_close) / prev_close) * 100
        # Zmiana wartości w PLN
        day_change_pln = (qty * (current_price_orig - prev_close)) * multiplier

    # Tabela historii
    history_table = []
    trade_events = {}
    for t in asset_data['trades']:
        price_val = t.get('price', 0.0)
        history_table.append({
            'date': t['date'].strftime('%Y-%m-%d'), 'type': t['type'], 'quantity': fmt_4(t['qty']),
            'price_original': f"{price_val:.2f}", 'currency': 'PLN', 'value_pln': fmt_2(abs(t['amount']))
        })
        d_str = t['date'].strftime("%Y-%m-%d")
        if t['type'] in ['OPEN BUY', 'BUY']:
            trade_events[d_str] = 'BUY'
        elif t['type'] in ['CLOSE SELL', 'SELL']:
            trade_events[d_str] = 'SELL'

    # Wykres
    chart_dates = [];
    chart_prices = [];
    chart_point_colors = [];
    chart_point_radius = []
    if not hist.empty:
        all_dates = hist.index.tolist();
        all_prices = [float(p) * multiplier for p in hist['Close'].tolist()]
        for d, p in zip(all_dates, all_prices):
            chart_dates.append(d);
            chart_prices.append(p)
            if d in trade_events:
                color = '#00ff7f' if trade_events[d] == 'BUY' else '#ff4d4d'
                chart_point_colors.append(color);
                chart_point_radius.append(6)
            else:
                chart_point_colors.append('rgba(0,0,0,0)');
                chart_point_radius.append(0)
    else:
        chart_dates = [t['date'] for t in history_table]
        chart_prices = [current_price_orig * multiplier] * len(chart_dates)
        chart_point_colors = ['#00ff7f'] * len(chart_dates);
        chart_point_radius = [6] * len(chart_dates)

    return {
        'symbol': symbol, 'asset_name': asset.name,
        'current_value_pln': fmt_2(current_value_pln),
        'avg_price': fmt_2(avg_price_pln),
        'quantity': fmt_4(qty),
        'gain_percent': fmt_2(profit_percent), 'gain_percent_raw': profit_percent,
        'total_gain_pln': fmt_2(total_gain_pln), 'total_gain_pln_raw': total_gain_pln,

        # --- NOWE POLA ---
        'current_price': fmt_2(current_price_orig * multiplier),  # Cena w PLN
        'currency_sym': 'PLN',  # Ponieważ wszystko przeliczamy na PLN w detalach
        'day_change_pct': fmt_2(day_change_pct), 'day_change_pct_raw': day_change_pct,
        'day_change_pln': fmt_2(day_change_pln), 'day_change_pln_raw': day_change_pln,
        # -----------------

        'transactions': reversed(history_table), 'chart_dates': chart_dates, 'chart_prices': chart_prices,
        'chart_point_colors': chart_point_colors, 'chart_point_radius': chart_point_radius,
        'first_trade_date': first_trade_date_str, 'ath': ath, 'atl': atl, 'rates': rates
    }