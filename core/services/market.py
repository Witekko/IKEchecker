# core/services/market.py

import math
import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from django.utils import timezone
from django.conf import settings
import logging
from ..models import Asset

logger = logging.getLogger('core')

def get_current_currency_rates():
    """
    Pobiera aktualne kursy: EUR, USD, GBP, JPY, AUD.
    Odporna na błędy 'nan'.
    """
    tickers = ["EURPLN=X", "USDPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]
    # Load defaults from settings
    rates = settings.DEFAULT_CURRENCY_RATES.copy()

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
        logger.error(f"Currency Error: {e}")

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
        logger.error(f"Market Error ({asset.symbol}): {e}")

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
        logger.error(f"Yahoo Timeline Download Error: {e}")
        return pd.DataFrame()


# core/services/market.py

def validate_ticker_and_price(symbol, date_obj, price_pln):
    """
    Sprawdza czy ticker istnieje w Yahoo i czy podana cena jest wiarygodna.
    Zwraca: (True, None) lub (False, "Treść błędu").
    """
    import yfinance as yf
    from datetime import timedelta

    # 1. Walidacja Tickera
    # Pobieramy 5 dni wokół daty, żeby mieć pewność że trafimy w dni sesyjne
    start_d = date_obj.date() - timedelta(days=2)
    end_d = date_obj.date() + timedelta(days=3)

    try:
        df = yf.download(symbol, start=start_d, end=end_d, progress=False)
        if df.empty:
            # Próba z sufiksem .PL lub .US jeśli użytkownik nie podał
            return False, f"Nie znaleziono danych dla symbolu '{symbol}'. Sprawdź na Yahoo Finance (np. czy nie brakuje końcówki .PL lub .US)."
    except Exception as e:
        return False, f"Błąd połączenia z Yahoo Finance: {e}"

    # 2. Walidacja Ceny (tylko jeśli to nie jest dzisiaj - bo dzisiaj cena jest płynna)
    # Jeśli transakcja jest starsza niż 24h, sprawdzamy widełki.
    if date_obj.date() < date.today():
        # Znajdź najbliższy dzień sesyjny w pobranych danych
        # index w df to daty (DatetimeIndex)
        try:
            # Szukamy wiersza dla konkretnej daty (lub najbliższej)
            # Upraszczamy: bierzemy średnią z pobranego zakresu jako punkt odniesienia
            # (Dokładne sprawdzanie dnia jest trudne przez strefy czasowe, to ma być sanity check)

            high = float(df['High'].max())
            low = float(df['Low'].min())

            # Margines 30% (bezpieczny dla zmiennych spółek)
            safe_high = high * 1.30
            safe_low = low * 0.70

            if not (safe_low <= price_pln <= safe_high):
                return False, f"Podejrzana cena! W tym okresie notowania {symbol} były między {low:.2f} a {high:.2f}. Wpisałeś {price_pln:.2f}. Sprawdź czy to cena za sztukę."

        except Exception as e:
            # Jeśli nie uda się sprawdzić ceny, puszczamy (lepjej przepuścić błąd niż zablokować poprawne)
            pass

    return True, None