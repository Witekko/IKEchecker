# core/services/market.py

import yfinance as yf
from django.utils import timezone
from ..models import Asset


def get_current_currency_rates():
    """
    Pobiera aktualne kursy: EUR, USD, GBP, JPY, AUD.
    """
    # Dodano AUDPLN=X
    tickers = ["EURPLN=X", "USDPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]

    # Domyślne wartości (fallback)
    rates = {'EUR': 4.30, 'USD': 4.00, 'GBP': 5.20, 'JPY': 2.60, 'AUD': 2.60}

    try:
        data = yf.download(tickers, period="1d", group_by='ticker', progress=False)

        # Parsowanie
        try:
            rates['EUR'] = float(data['EURPLN=X']['Close'].iloc[-1])
        except:
            pass

        try:
            rates['USD'] = float(data['USDPLN=X']['Close'].iloc[-1])
        except:
            pass

        try:
            rates['GBP'] = float(data['GBPPLN=X']['Close'].iloc[-1])
        except:
            pass

        try:
            raw_jpy = float(data['JPYPLN=X']['Close'].iloc[-1])
            rates['JPY'] = raw_jpy * 100
        except:
            pass

        # AUD
        try:
            rates['AUD'] = float(data['AUDPLN=X']['Close'].iloc[-1])
        except:
            pass

    except Exception as e:
        print(f"Currency Error: {e}")

    return {k: round(v, 2) for k, v in rates.items()}


# ... funkcja get_cached_price bez zmian ...
def get_cached_price(asset: Asset):
    now = timezone.now()
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:
            return float(asset.last_price), float(asset.previous_close)

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        data = ticker.history(period='5d')
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            prev_close = price
            if len(data) >= 2:
                prev_close = float(data['Close'].iloc[-2])

            asset.last_price = price
            asset.previous_close = prev_close
            asset.last_updated = now
            asset.save()
            return price, prev_close
    except Exception as e:
        print(f"Market Error ({asset.symbol}): {e}")

    return float(asset.last_price), float(asset.previous_close)