# core/services/market.py

import math
import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from django.utils import timezone
from ..models import Asset


def get_current_currency_rates():
    """
    Pobiera aktualne kursy: EUR, USD, GBP, JPY, AUD.
    Odporna na błędy 'nan'.
    """
    tickers = ["EURPLN=X", "USDPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]
    rates = {'EUR': 4.30, 'USD': 4.00, 'GBP': 5.20, 'JPY': 2.60, 'AUD': 2.60}

    try:
        data = yf.download(tickers, period="5d", group_by='ticker', progress=False)

        def get_safe_rate(ticker_name):
            try:
                # Sprawdzamy czy ticker jest w kolumnach (MultiIndex)
                if ticker_name not in data.columns.levels[0]: return None

                series = data[ticker_name]['Close']
                val = float(series.iloc[-1])

                if math.isnan(val):
                    val = float(series.iloc[-2])  # Próbujemy wczoraj
                    if math.isnan(val): return None
                return val
            except:
                return None

        # Aktualizacja
        r_eur = get_safe_rate('EURPLN=X');
        if r_eur: rates['EUR'] = r_eur
        r_usd = get_safe_rate('USDPLN=X');
        if r_usd: rates['USD'] = r_usd
        r_gbp = get_safe_rate('GBPPLN=X');
        if r_gbp: rates['GBP'] = r_gbp
        r_aud = get_safe_rate('AUDPLN=X');
        if r_aud: rates['AUD'] = r_aud

        # JPY specyfika
        r_jpy = get_safe_rate('JPYPLN=X');
        if r_jpy: rates['JPY'] = r_jpy * 100

    except Exception as e:
        print(f"Currency Error: {e}")

    return {k: round(v, 2) for k, v in rates.items()}


def get_cached_price(asset: Asset):
    """
    Pobiera cenę jednego aktywa (z cache lub Yahoo).
    """
    now = timezone.now()
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:  # 15 min cache
            return float(asset.last_price), float(asset.previous_close)

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        # 1 miesiąc historii, żeby ominąć dziury
        data = ticker.history(period='1mo')

        if not data.empty:
            valid = data['Close'].dropna()
            if not valid.empty:
                price = float(valid.iloc[-1])

                prev_close = price
                if len(valid) >= 2:
                    prev_close = float(valid.iloc[-2])

                asset.last_price = price
                asset.previous_close = prev_close
                asset.last_updated = now
                asset.save()
                return price, prev_close
    except Exception as e:
        print(f"Market Error ({asset.symbol}): {e}")

    return float(asset.last_price), float(asset.previous_close)


def fetch_historical_data_for_timeline(assets_tickers: list, start_date: date) -> pd.DataFrame:
    """
    Pobiera dane historyczne dla listy tickerów + benchmarków.
    Zabezpiecza przed datami z przyszłości (cofa start o 2 lata).
    """
    end_date = date.today()
    safe_download_start = start_date - timedelta(days=730)

    benchmarks = ['^GSPC', 'USDPLN=X']
    all_tickers = list(set(assets_tickers + benchmarks))

    if not all_tickers:
        return pd.DataFrame()

    try:
        # threads=False dla stabilności
        data = yf.download(
            all_tickers,
            start=safe_download_start,
            end=end_date + timedelta(days=1),
            group_by='ticker',
            progress=False,
            threads=False
        )
        return data
    except Exception as e:
        print(f"Yahoo Timeline Download Error: {e}")
        return pd.DataFrame()