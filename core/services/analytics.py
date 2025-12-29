# core/services/analytics.py

import math
import pandas as pd
from datetime import date, timedelta
from .calculator import PortfolioCalculator
from .market import get_cached_price, fetch_historical_data_for_timeline
from django.core.cache import cache
import logging

logger = logging.getLogger('core')


def analyze_holdings(transactions, eur_rate, usd_rate, start_date=None):
    """
    Analizuje stan posiadania.
    Zwraca SUROWE DANE LICZBOWE (float). Formatowanie odbywa się w portfolio.py.
    """
    # 1. Obliczenia standardowe (STAN NA DZIŚ)
    calc = PortfolioCalculator(transactions).process()
    holdings_data = calc.get_holdings()
    cash, total_invested = calc.get_cash_balance()

    # 2. Logika Historyczna (Pandas)
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

            # Stan na start
            df_start = df[df['date'] < start_date]
            df_start.loc[df_start['type'] == 'SELL', 'quantity'] *= -1
            qty_at_start = df_start.groupby('asset__symbol')['quantity'].sum()

            # Cashflow w okresie
            df_period = df[(df['date'] >= start_date) & (df['date'] <= date.today())]
            flows_in_period = df_period.groupby('asset__symbol')['amount'].sum()

            # Cena na start
            # --- FIX: Dodano .dropna() aby usunąć None (z wpłat/wypłat) ---
            tickers = df['asset__yahoo_ticker'].dropna().unique().tolist()

            # Pobieramy ceny (z marginesem błędu 5 dni wstecz)
            hist_prices = fetch_historical_data_for_timeline(tickers, start_date - timedelta(days=5))

            def get_start_price(ticker_sym):
                if hist_prices.empty: return 0.0
                try:
                    target = pd.Timestamp(start_date)
                    if isinstance(hist_prices.columns, pd.MultiIndex):
                        if ticker_sym in hist_prices.columns.levels[0]:
                            return float(hist_prices[ticker_sym]['Close'].asof(target))
                    else:
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

    gainers = 0
    losers = 0

    for sym, data in holdings_data.items():
        qty = data['qty']
        asset = data['asset']

        # --- POZYCJE ZAMKNIĘTE ---
        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                is_foreign = asset.currency != 'PLN'
                processed_assets.append({
                    'is_closed': True,
                    'symbol': sym,
                    'name': asset.name,
                    'currency': asset.currency,
                    'is_foreign': is_foreign,

                    # Surowe liczby
                    'realized_pln': float(data['realized']),
                    'gain_pln': float(data['realized']),

                    # Bezpieczniki (zera w float)
                    'value_pln': 0.0,
                    'gain_percent': 0.0,
                    'day_change_pct': 0.0,
                    'cost_pln': 0.0,
                    'avg_price': 0.0,
                    'cur_price': 0.0,
                    'quantity': 0.0
                })
            continue

        # --- POZYCJE OTWARTE ---
        cost = data['cost']
        cur_price, prev_close = get_cached_price(asset)

        is_fallback_price = False
        if cur_price <= 0:
            cur_price = (cost / qty) if qty > 0 else 0
            prev_close = cur_price
            is_fallback_price = True

        multiplier = 1.0
        is_foreign = False
        if asset.currency == 'EUR':
            multiplier = eur_rate;
            is_foreign = True
        elif asset.currency == 'USD':
            multiplier = usd_rate;
            is_foreign = True
        elif asset.currency == 'GBP':
            multiplier = 5.20;
            is_foreign = True

        if math.isnan(multiplier): multiplier = 1.0
        if is_fallback_price: multiplier = 1.0

        value_pln = (qty * cur_price) * multiplier

        # Logika Zysku
        display_profit_pln = 0.0
        display_return_pct = 0.0

        if use_period_logic:
            p_stat = period_stats.get(sym, {'qty_start': 0, 'price_start': 0, 'flow': 0})
            val_start = (p_stat['qty_start'] * p_stat['price_start']) * multiplier
            period_profit = value_pln - val_start + p_stat['flow']
            display_profit_pln = period_profit

            invested_base = val_start
            if p_stat['flow'] < 0: invested_base += abs(p_stat['flow'])

            if invested_base > 1.0:
                display_return_pct = (period_profit / invested_base) * 100
        else:
            current_position_gain = value_pln - cost
            display_profit_pln = current_position_gain + data['realized']
            if cost > 0:
                display_return_pct = (display_profit_pln / cost) * 100

        total_unrealized_pln += (value_pln - cost)

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

        # Wszystko jako FLOAT
        processed_assets.append({
            'is_closed': False,
            'symbol': sym,
            'name': asset.name,
            'quantity': float(qty),
            'avg_price': float(avg_price),
            'cur_price': float(cur_price),
            'value_pln': float(value_pln),
            'cost_pln': float(cost),
            'gain_pln': float(display_profit_pln),  # Total Gain (Okres/Lifetime)
            'gain_percent': float(display_return_pct),
            'realized_pln': float(data['realized']),
            'day_change_pct': float(day_change_pct),
            'currency': asset.currency,
            'is_foreign': is_foreign,
            'price_date': asset.last_updated,
            'trades': data['trades']
        })

    total_value = portfolio_value_stock + cash
    total_profit = total_value - total_invested

    # Share % obliczamy tutaj jako float
    for item in processed_assets:
        if item.get('is_closed'):
            item['share_pct'] = 0.0
        else:
            base = portfolio_value_stock if portfolio_value_stock > 0 else 1.0
            item['share_pct'] = (item['value_pln'] / base) * 100

    return {
        'total_value': total_value, 'invested': total_invested, 'cash': cash,
        'total_profit': total_profit, 'unrealized_profit': total_unrealized_pln,
        'day_change_pln': total_day_change_pln,
        'assets': processed_assets,  # Lista słowników z floatami
        'gainers': gainers, 'losers': losers, 'first_date': calc.first_date
    }


# analyze_history zostawiamy bez zmian (już działa z Cachem i ma dropna())
def analyze_history(transactions, eur_rate, usd_rate):
    """
    Generuje dane do wykresu historycznego (Optimized with Pandas + Cache).
    """
    if not transactions.exists():
        return {'dates': [], 'val_user': [], 'val_inv': [], 'last_date': 'N/A'}

    tx_data = list(transactions.values('date', 'type', 'amount', 'quantity', 'asset__yahoo_ticker'))
    if not tx_data: return {'dates': [], 'val_user': [], 'val_inv': [], 'last_date': 'N/A'}

    df_tx = pd.DataFrame(tx_data)
    df_tx['date'] = pd.to_datetime(df_tx['date']).dt.date
    df_tx['amount'] = df_tx['amount'].astype(float)
    df_tx['quantity'] = df_tx['quantity'].astype(float)
    df_tx = df_tx.sort_values(by=['date', 'type'])

    start_date = df_tx['date'].min()
    end_date = date.today()

    last_tx_id = transactions.last().id
    count_tx = transactions.count()
    cache_key = f"history_timeline_v3_{last_tx_id}_{count_tx}_{start_date}_{end_date}"
    cached = cache.get(cache_key)
    if cached: return cached

    tickers = df_tx['asset__yahoo_ticker'].dropna().unique().tolist()
    hist_data = fetch_historical_data_for_timeline(tickers, start_date)

    last_market_date_str = "N/A"
    if not hist_data.empty: last_market_date_str = hist_data.index[-1].strftime('%d %b %Y')

    full_dates = pd.date_range(start=start_date, end=end_date, freq='D').date
    timeline_df = pd.DataFrame(index=full_dates)
    timeline_df.index.name = 'date'

    daily_cash = df_tx.groupby('date')['amount'].sum()
    timeline_df['cash_flow'] = daily_cash
    timeline_df['cash_flow'] = timeline_df['cash_flow'].fillna(0)
    timeline_df['cash_balance'] = timeline_df['cash_flow'].cumsum()

    mask_inv = df_tx['type'].isin(['DEPOSIT', 'WITHDRAWAL'])
    daily_inv_change = df_tx[mask_inv].groupby('date')['amount'].sum()
    invested_series = []
    curr_invested = 0.0
    daily_inv_aligned = daily_inv_change.reindex(full_dates, fill_value=0.0)
    for chg in daily_inv_aligned:
        if chg > 0:
            curr_invested += chg
            if curr_invested < 0: curr_invested = 0.0
        elif chg < 0:
            curr_invested -= abs(chg)
            if curr_invested < 0: curr_invested = 0.0
        invested_series.append(curr_invested)
    timeline_df['invested'] = invested_series

    mask_holdings = df_tx['type'].isin(['BUY', 'SELL']) & df_tx['asset__yahoo_ticker'].notnull()
    if mask_holdings.any():
        df_h_changes = df_tx[mask_holdings].copy()
        df_h_changes.loc[df_h_changes['type'] == 'SELL', 'quantity'] *= -1
        daily_qty = df_h_changes.groupby(['date', 'asset__yahoo_ticker'])['quantity'].sum().unstack(fill_value=0)
        daily_qty = daily_qty.reindex(full_dates, fill_value=0).cumsum()
    else:
        daily_qty = pd.DataFrame(index=full_dates)

    if not hist_data.empty: hist_data.index = hist_data.index.date
    price_df = pd.DataFrame(index=full_dates)

    def get_series(tk):
        if hist_data.empty: return pd.Series(dtype=float)
        if isinstance(hist_data.columns, pd.MultiIndex):
            if tk in hist_data.columns.levels[0]: return hist_data[tk]['Close']
        elif tk in hist_data.columns:
            return hist_data[tk]
        return pd.Series(dtype=float)

    usd_series = get_series('USDPLN=X').reindex(full_dates).ffill().fillna(0)
    sp500_series = get_series('^GSPC').reindex(full_dates).ffill().fillna(0)

    for col in daily_qty.columns:
        s = get_series(col)
        if not s.empty:
            price_df[col] = s.reindex(full_dates).ffill().fillna(0)
        else:
            price_df[col] = 0.0

    mult_df = pd.DataFrame(1.0, index=price_df.index, columns=price_df.columns)
    for col in mult_df.columns:
        if str(col).endswith('.DE'):
            mult_df[col] = 4.30 if math.isnan(eur_rate) else eur_rate
        elif str(col).endswith('.US') or str(col).endswith('.UK'):
            mult_df[col] = usd_series
            fallback = usd_rate if not math.isnan(usd_rate) else 4.00
            mult_df[col] = mult_df[col].replace(0.0, fallback)

    common_cols = daily_qty.columns.intersection(price_df.columns)
    stock_val_df = daily_qty[common_cols] * price_df[common_cols] * mult_df[common_cols]
    total_stock_val = stock_val_df.sum(axis=1)

    timeline_df['user_value'] = timeline_df['cash_balance'] + total_stock_val
    timeline_df['user_value'] = timeline_df['user_value'].clip(lower=0.0)

    daily_deposits = df_tx[df_tx['type'] == 'DEPOSIT'].groupby('date')['amount'].sum().reindex(full_dates, fill_value=0)
    denom = usd_series * sp500_series
    daily_units = daily_deposits / denom
    daily_units = daily_units.fillna(0.0)
    daily_units[denom <= 0] = 0.0
    cum_units = daily_units.cumsum()
    sp500_val = cum_units * denom
    timeline_df['sp500_val'] = sp500_val
    mask_sp_zero = timeline_df['sp500_val'] <= 0.001
    timeline_df.loc[mask_sp_zero, 'sp500_val'] = timeline_df.loc[mask_sp_zero, 'invested']

    inf_cap = 0.0;
    inf_series = []
    daily_rate = 1.06 ** (1 / 365)
    for amt in daily_inv_aligned:
        if amt > 0:
            inf_cap += amt;
        elif amt < 0:
            inf_cap -= abs(amt);
        if inf_cap < 0: inf_cap = 0.0
        inf_cap *= daily_rate
        inf_series.append(inf_cap)
    timeline_df['inf_val'] = inf_series

    def calc_pct(val_col, base_col):
        base = timeline_df[base_col]
        val = timeline_df[val_col]
        res = (val - base) / base * 100
        res[base <= 0] = 0.0
        return res.round(2)

    timeline_df['pct_user'] = calc_pct('user_value', 'invested')
    timeline_df['pct_sp'] = calc_pct('sp500_val', 'invested')
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
        'pct_inf': timeline_df['pct_inf'].tolist(),
        'last_market_date': last_market_date_str
    }
    cache.set(cache_key, res, 900)
    return res