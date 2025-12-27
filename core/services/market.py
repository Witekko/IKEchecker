# core/services/market.py

import math  # <--- WAŻNE: Potrzebne do wykrywania nan
import yfinance as yf
from django.utils import timezone
from ..models import Asset


def get_current_currency_rates():
    """
    Pobiera aktualne kursy: EUR, USD, GBP, JPY, AUD.
    Odporna na błędy 'nan' (Not a Number).
    """
    tickers = ["EURPLN=X", "USDPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]

    # Domyślne wartości (fallback)
    rates = {'EUR': 4.30, 'USD': 4.00, 'GBP': 5.20, 'JPY': 2.60, 'AUD': 2.60}

    try:
        # Pobieramy 5 dni, żeby mieć pewność, że trafimy na dzień roboczy
        data = yf.download(tickers, period="5d", group_by='ticker', progress=False)

        def get_safe_rate(ticker_name):
            try:
                # Bierzemy ostatnią dostępną wartość (iloc[-1])
                val = float(data[ticker_name]['Close'].iloc[-1])
                # KLUCZOWA POPRAWKA: Jeśli to NaN, rzucamy błąd, żeby wejść w except
                if math.isnan(val):
                    # Próbujemy wziąć przedostatnią (wczoraj)
                    val = float(data[ticker_name]['Close'].iloc[-2])
                    if math.isnan(val): return None
                return val
            except:
                return None

        # Aktualizacja tylko jeśli pobrano LICZBĘ
        r_eur = get_safe_rate('EURPLN=X');
        if r_eur: rates['EUR'] = r_eur

        r_usd = get_safe_rate('USDPLN=X');
        if r_usd: rates['USD'] = r_usd

        r_gbp = get_safe_rate('GBPPLN=X');
        if r_gbp: rates['GBP'] = r_gbp

        r_jpy = get_safe_rate('JPYPLN=X');
        if r_jpy: rates['JPY'] = r_jpy * 100

        r_aud = get_safe_rate('AUDPLN=X');
        if r_aud: rates['AUD'] = r_aud

    except Exception as e:
        print(f"Currency Error: {e}")

    return {k: round(v, 2) for k, v in rates.items()}


def get_cached_price(asset: Asset):
    now = timezone.now()
    # Cache ważny 15 minut
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:
            return float(asset.last_price), float(asset.previous_close)

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        # Pobieramy miesiąc, żeby ominąć dziury świąteczne
        data = ticker.history(period='1mo')

        if not data.empty:
            # Szukamy ostatniej nie-NaN wartości
            valid_closes = data['Close'].dropna()

            if not valid_closes.empty:
                price = float(valid_closes.iloc[-1])

                # Poprzednie zamknięcie
                prev_close = price
                if len(valid_closes) >= 2:
                    prev_close = float(valid_closes.iloc[-2])

                asset.last_price = price
                asset.previous_close = prev_close
                asset.last_updated = now
                asset.save()
                return price, prev_close
    except Exception as e:
        print(f"Market Error ({asset.symbol}): {e}")

    return float(asset.last_price), float(asset.previous_close)