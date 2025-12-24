# core/services/market.py

import yfinance as yf
from django.utils import timezone
from ..models import Asset


def get_current_currency_rates():
    """Pobiera aktualne kursy EUR i USD."""
    try:
        eur = float(yf.Ticker("EURPLN=X").history(period="1d")['Close'].iloc[-1])
        usd = float(yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1])
    except:
        # Fallback w razie awarii Yahoo
        eur, usd = 4.30, 4.00
    return round(eur, 2), round(usd, 2)


def get_cached_price(asset: Asset):
    """
    Pobiera cenę aktywa z cache (baza) lub z Yahoo Finance,
    jeśli cache jest starszy niż 15 minut.
    """
    now = timezone.now()
    # 1. Sprawdź cache (ważny 15 min)
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:
            return float(asset.last_price), float(asset.previous_close)

    # 2. Pobierz z Yahoo
    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        data = ticker.history(period='5d')
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            prev_close = price
            if len(data) >= 2:
                prev_close = float(data['Close'].iloc[-2])

            # 3. Zapisz w bazie
            asset.last_price = price
            asset.previous_close = prev_close
            asset.last_updated = now
            asset.save()
            return price, prev_close
    except Exception as e:
        print(f"Market Error ({asset.symbol}): {e}")

    # Fallback do ostatniej znanej
    return float(asset.last_price), float(asset.previous_close)