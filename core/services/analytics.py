# core/services/analytics.py

import math
import pandas as pd
from datetime import date, timedelta
from .calculator import PortfolioCalculator
from .market import get_cached_price, fetch_historical_data_for_timeline
from django.core.cache import cache
import logging

logger = logging.getLogger('core')


def analyze_holdings(transactions, currency_rates, start_date=None):
    """
    Analizuje stan posiadania.
    """
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    cash, total_invested = calc.get_cash_balance()

    period_stats = {}
    use_period_logic = start_date is not None

    if use_period_logic:
        tx_data = list(
            transactions.values('date', 'type', 'amount', 'quantity', 'asset__symbol', 'asset__yahoo_ticker'))
        if tx_data:
            df = pd.DataFrame(tx_data)
            df['date'] = pd.to_datetime(df['date']).dt.date
            df['amount'] = df['amount'].astype(float)
            df['quantity'] = df['quantity'].astype(float)

            df_start = df[df['date'] < start_date]
            df_start.loc[df_start['type'] == 'SELL', 'quantity'] *= -1
            qty_at_start = df_start.groupby('asset__symbol')['quantity'].sum()

            df_period = df[(df['date'] >= start_date) & (df['date'] <= date.today())]
            flows_in_period = df_period.groupby('asset__symbol')['amount'].sum()

            tickers = df['asset__yahoo_ticker'].dropna().unique().tolist()
            hist_prices = fetch_historical_data_for_timeline(tickers, start_date - timedelta(days=5))

            def get_start_price(ticker_sym):
                if hist_prices.empty: return 0.0
                try:
                    # FIX: hist_prices ma indeks date, więc szukamy po date
                    target = start_date
                    if isinstance(target, str): target = pd.to_datetime(target).date()

                    if isinstance(hist_prices.columns, pd.MultiIndex):
                        if ticker_sym in hist_prices.columns.levels[0]:
                            # asof działa lepiej na posortowanym indeksie
                            return float(hist_prices[ticker_sym]['Close'].asof(target))
                    else:
                        # Fallback (nie powinno wystąpić z nowym market.py)
                        return float(hist_prices['Close'].asof(target))
                except:
                    return 0.0
                return 0.0

            sym_to_ticker = {row['asset__symbol']: row['asset__yahoo_ticker'] for row in tx_data if
                             row['asset__symbol']}
            all_syms = set(qty_at_start.index).union(set(flows_in_period.index))
            for s in all_syms:
                period_stats[s] = {
                    'qty_start': qty_at_start.get(s, 0.0),
                    'flow': flows_in_period.get(s, 0.0),
                    'price_start': get_start_price(sym_to_ticker.get(s))
                }

    processed_assets = []
    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0
    total_unrealized_pln = 0.0
    gainers = 0;
    losers = 0

    for sym, data in holdings_data.items():
        qty = data['qty']
        asset = data['asset']

        # FIX: Jeśli ilość jest bliska zeru (pozycje zamknięte)
        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                is_foreign = asset.currency != 'PLN'
                realized_pln = float(data['realized'])

                # Obliczamy ROI dla zamkniętej pozycji
                revenue = 0.0
                for t in data['trades']:
                    if t['type'] in ['SELL', 'CLOSE', 'CLOSE SELL']:
                        revenue += float(t['amount'])

                # Koszt = Przychód - Zysk
                cost_basis = revenue - realized_pln
                roi_pct = (realized_pln / cost_basis * 100) if cost_basis > 0.01 else 0.0

                processed_assets.append({
                    'is_closed': True,
                    'symbol': sym,
                    'name': asset.name,
                    'display_name': asset.display_name,
                    'sector': asset.get_sector_display(),
                    'asset_type': asset.get_asset_type_display(),
                    'currency': asset.currency,
                    'is_foreign': is_foreign,
                    'realized_pln': realized_pln,
                    'gain_pln': realized_pln,
                    'gain_percent': roi_pct,
                    'value_pln': 0.0, 'day_change_pct': 0.0, 'cost_pln': 0.0,
                    'avg_price': 0.0, 'cur_price': 0.0, 'quantity': 0.0
                })
            continue

        # POZYCJE OTWARTE
        cost = data['cost']
        cur_price, prev_close = get_cached_price(asset)

        is_fallback_price = False
        if cur_price <= 0:
            cur_price = (cost / qty) if qty > 0 else 0
            prev_close = cur_price
            is_fallback_price = True

        multiplier = 1.0
        is_foreign = False
        if asset.currency != 'PLN':
            is_foreign = True
            multiplier = currency_rates.get(asset.currency, 1.0)
            if multiplier == 0: multiplier = 1.0
        if is_fallback_price: multiplier = 1.0

        value_pln = (qty * cur_price) * multiplier

        # Zysk Niezrealizowany
        current_position_unrealized = value_pln - cost
        total_unrealized_pln += current_position_unrealized

        # Zysk całkowity (Realized + Unrealized)
        display_profit_pln = current_position_unrealized + data['realized']
        display_return_pct = (display_profit_pln / cost * 100) if cost > 0 else 0.0

        day_change_pct = ((cur_price - prev_close) / prev_close * 100) if prev_close > 0 else 0
        day_change_val = (qty * (cur_price - prev_close)) * multiplier

        if day_change_pct > 0:
            gainers += 1
        elif day_change_pct < 0:
            losers += 1

        portfolio_value_stock += value_pln
        total_day_change_pln += day_change_val

        processed_assets.append({
            'is_closed': False,
            'symbol': sym,
            'name': asset.name,
            'display_name': asset.display_name,
            'sector': asset.get_sector_display(),
            'asset_type': asset.get_asset_type_display(),
            'quantity': float(qty),
            'avg_price': float(cost / qty) if qty else 0,
            'cur_price': float(cur_price),
            'value_pln': float(value_pln),
            'cost_pln': float(cost),
            'gain_pln': float(display_profit_pln),
            'gain_percent': float(display_return_pct),
            'realized_pln': float(data['realized']),
            'day_change_pct': float(day_change_pct),
            'currency': asset.currency,
            'is_foreign': is_foreign,
            'price_date': asset.last_updated,
            'share_pct': 0
        })

    total_value = portfolio_value_stock + cash
    total_profit = total_value - total_invested

    for item in processed_assets:
        if not item.get('is_closed'):
            base = portfolio_value_stock if portfolio_value_stock > 0 else 1.0
            item['share_pct'] = (item['value_pln'] / base) * 100

    return {
        'total_value': total_value, 'invested': total_invested, 'cash': cash,
        'total_profit': total_profit, 'unrealized_profit': total_unrealized_pln,
        'day_change_pln': total_day_change_pln,
        'assets': processed_assets,
        'gainers': gainers, 'losers': losers, 'first_date': calc.first_date
    }


def analyze_history(transactions, currency_rates):
    """
    Generuje dane do wykresu historycznego.
    """
    if not transactions.exists():
        return {'dates': [], 'val_user': [], 'val_inv': [], 'last_date': 'N/A'}

    tx_data = list(transactions.values('date', 'type', 'amount', 'quantity', 'asset__yahoo_ticker'))
    df_tx = pd.DataFrame(tx_data)
    df_tx['date'] = pd.to_datetime(df_tx['date']).dt.date
    df_tx['amount'] = df_tx['amount'].astype(float)
    df_tx['quantity'] = df_tx['quantity'].astype(float)
    df_tx = df_tx.sort_values(by=['date', 'type'])

    start_date = df_tx['date'].min()
    end_date = date.today()
    if df_tx['date'].max() > end_date: end_date = df_tx['date'].max()

    last_tx_id = transactions.last().id
    count_tx = transactions.count()
    cache_key = f"history_v9_{last_tx_id}_{count_tx}_{start_date}_{end_date}"
    cached = cache.get(cache_key)
    if cached: return cached

    user_tickers = df_tx['asset__yahoo_ticker'].dropna().unique().tolist()

    # Tickery do pobrania
    CURRENCY_MAP = {
        'USD': 'USDPLN=X', 'EUR': 'EURPLN=X', 'GBP': 'GBPPLN=X',
        'CHF': 'CHFPLN=X', 'NOK': 'NOKPLN=X', 'SEK': 'SEKPLN=X',
        'DKK': 'DKKPLN=X', 'CZK': 'CZKPLN=X', 'PLN': None
    }
    needed_currencies = [v for v in CURRENCY_MAP.values() if v]
    benchmarks = ['^GSPC', 'WIG.WA']
    full_ticker_list = list(set(user_tickers + needed_currencies + benchmarks))

    # POBIERANIE (Market zwraca index typu DATE, nie Timestamp!)
    hist_data = fetch_historical_data_for_timeline(full_ticker_list, start_date)

    last_market_date_str = "N/A"
    if not hist_data.empty:
        last_market_date_str = hist_data.index[-1].strftime('%d %b %Y')

    # FIX: full_dates też musi być typu date, żeby pasować do hist_data
    full_dates = pd.date_range(start=start_date, end=end_date, freq='D').date
    timeline_df = pd.DataFrame(index=full_dates)
    timeline_df.index.name = 'date'

    def get_series(tk):
        if hist_data.empty: return pd.Series(dtype=float)
        try:
            # Teraz mamy pewność, że kolumny to MultiIndex (Dzięki nowemu market.py)
            if isinstance(hist_data.columns, pd.MultiIndex):
                if tk in hist_data.columns.levels[0]:
                    return hist_data[tk]['Close']
            # Fallback (gdyby jednak coś poszło nie tak)
            elif tk in hist_data.columns:
                return hist_data[tk]
        except:
            pass
        return pd.Series(dtype=float)

    def smart_fill(series, target_dates):
        if series.empty: return pd.Series(0.0, index=target_dates)
        # series.index to Date, target_dates to Date -> Union zadziała
        combined_idx = series.index.union(target_dates).sort_values()
        extended = series.reindex(combined_idx).ffill()
        return extended.reindex(target_dates).fillna(0)

    # --- CASH & INVESTED ---
    daily_cash = df_tx.groupby('date')['amount'].sum()
    timeline_df['cash_flow'] = daily_cash
    timeline_df['cash_flow'] = timeline_df['cash_flow'].fillna(0)
    timeline_df['cash_balance'] = timeline_df['cash_flow'].cumsum()

    mask_inv = df_tx['type'].isin(['DEPOSIT', 'WITHDRAWAL'])
    daily_inv_change = df_tx[mask_inv].groupby('date')['amount'].sum().reindex(full_dates, fill_value=0.0)
    invested_series = []
    curr_invested = 0.0
    for chg in daily_inv_change:
        if chg > 0:
            curr_invested += chg;
        elif chg < 0:
            curr_invested -= abs(chg);
        if curr_invested < 0: curr_invested = 0.0
        invested_series.append(curr_invested)
    timeline_df['invested'] = invested_series

    # --- QUANTITY ---
    mask_holdings = df_tx['type'].isin(['BUY', 'SELL']) & df_tx['asset__yahoo_ticker'].notnull()
    daily_qty = pd.DataFrame(index=full_dates)
    if mask_holdings.any():
        df_h = df_tx[mask_holdings].copy()
        df_h.loc[df_h['type'] == 'SELL', 'quantity'] *= -1
        grouped = df_h.groupby(['date', 'asset__yahoo_ticker'])['quantity'].sum().unstack(fill_value=0)
        daily_qty = grouped.reindex(full_dates, fill_value=0).cumsum()

    # --- WYCENA ---
    price_df = pd.DataFrame(index=full_dates)
    for col in daily_qty.columns:
        s = get_series(col)
        price_df[col] = smart_fill(s, full_dates)

    from ..models import Asset
    assets_in_chart = Asset.objects.filter(yahoo_ticker__in=daily_qty.columns)
    ticker_currency_map = {a.yahoo_ticker: a.currency for a in assets_in_chart}

    mult_df = pd.DataFrame(1.0, index=full_dates, columns=price_df.columns)
    for t_col in mult_df.columns:
        c_code = ticker_currency_map.get(t_col, 'PLN')
        c_ticker = CURRENCY_MAP.get(c_code)
        if c_ticker:
            s = get_series(c_ticker)
            filled = smart_fill(s, full_dates)
            fallback = currency_rates.get(c_code, 1.0)
            mult_df[t_col] = filled.replace(0.0, fallback)

    common = daily_qty.columns.intersection(price_df.columns)
    stock_val = daily_qty[common] * price_df[common] * mult_df[common]

    timeline_df['user_value'] = timeline_df['cash_balance'] + stock_val.sum(axis=1)
    timeline_df['user_value'] = timeline_df['user_value'].clip(lower=0.0)

    # --- BENCHMARKI (SP500, WIG) ---
    daily_deposits = df_tx[df_tx['type'] == 'DEPOSIT'].groupby('date')['amount'].sum().reindex(full_dates, fill_value=0)

    # SP500
    usd_bm = smart_fill(get_series('USDPLN=X'), full_dates).replace(0.0, currency_rates.get('USD', 4.0))
    sp500_price = smart_fill(get_series('^GSPC'), full_dates)
    denom_sp = usd_bm * sp500_price
    units_sp = daily_deposits / denom_sp
    units_sp = units_sp.fillna(0.0)
    units_sp[denom_sp <= 0.001] = 0.0
    timeline_df['sp500_val'] = units_sp.cumsum() * denom_sp
    timeline_df.loc[timeline_df['sp500_val'] <= 0.01, 'sp500_val'] = timeline_df['invested']

    # WIG
    wig_price = smart_fill(get_series('WIG.WA'), full_dates)
    units_wig = daily_deposits / wig_price
    units_wig = units_wig.fillna(0.0)
    units_wig[wig_price <= 0.001] = 0.0
    timeline_df['wig_val'] = units_wig.cumsum() * wig_price
    timeline_df.loc[timeline_df['wig_val'] <= 0.01, 'wig_val'] = timeline_df['invested']

    # INFLACJA
    inf_series = []
    inf_cap = 0.0
    daily_rate = 1.06 ** (1 / 365)
    for amt in daily_inv_change:
        if amt > 0:
            inf_cap += amt;
        elif amt < 0:
            inf_cap -= abs(amt);
        if inf_cap < 0: inf_cap = 0.0
        inf_cap *= daily_rate
        inf_series.append(inf_cap)
    timeline_df['inf_val'] = inf_series

    # FORMATOWANIE
    def calc_pct(v_col, b_col):
        base = timeline_df[b_col]
        val = timeline_df[v_col]
        res = (val - base) / base * 100
        res[base <= 1.0] = 0.0
        return res.round(2)

    timeline_df['pct_user'] = calc_pct('user_value', 'invested')
    timeline_df['pct_sp'] = calc_pct('sp500_val', 'invested')
    timeline_df['pct_wig'] = calc_pct('wig_val', 'invested')
    timeline_df['pct_inf'] = calc_pct('inf_val', 'invested')

    timeline_df['points'] = 0
    timeline_df.loc[daily_deposits > 0, 'points'] = 6

    res = {
        'dates': timeline_df.index.map(lambda d: d.strftime("%Y-%m-%d")).tolist(),
        'points': timeline_df['points'].tolist(),
        'val_user': timeline_df['user_value'].round(2).tolist(),
        'val_inv': timeline_df['invested'].round(2).tolist(),
        'val_sp': timeline_df['sp500_val'].round(2).tolist(),
        'val_inf': timeline_df['inf_val'].round(2).tolist(),
        'pct_user': timeline_df['pct_user'].tolist(),
        'pct_sp': timeline_df['pct_sp'].tolist(),
        'pct_wig': timeline_df['pct_wig'].tolist(),
        'pct_inf': timeline_df['pct_inf'].tolist(),
        'last_market_date': last_market_date_str
    }

    cache.set(cache_key, res, 900)
    return res