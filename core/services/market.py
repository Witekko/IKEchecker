# core/services/market.py

import math
import yfinance as yf
import pandas as pd
from datetime import date, timedelta
from django.utils import timezone
from django.conf import settings
import logging
from ..models import Asset, AssetType, AssetSector

logger = logging.getLogger('core')


def get_current_currency_rates():
    """
    Pobiera aktualne kursy: EUR, USD, GBP, JPY, AUD.
    Odporna na błędy 'nan'.
    """
    tickers = ["EURPLN=X", "USDPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]
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

        # JPY specyfika (dzielimy, bo często podawany jest za 100 JPY lub odwrotnie, tu zakładamy standard)
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
    Pobiera dane historyczne w trybie bezpiecznym (osobne zapytania dla benchmarków).
    Gwarantuje, że błąd jednego tickera nie wysadzi całego wykresu.
    """
    end_date = date.today()
    safe_download_start = start_date - timedelta(days=730)

    # 1. Lista Benchmarków (Kluczowe dla wykresu)
    benchmarks = ['^GSPC', 'USDPLN=X', 'WIG.WA']

    # 2. Lista Aktywów Użytkownika (Unikalne)
    user_tickers = list(set(assets_tickers))

    # Wynikowy DataFrame
    combined_df = pd.DataFrame()

    # --- KROK A: Pobieramy Benchmarki (PRIORYTET) ---
    # Pobieramy je razem, bo to standardowe tickery Yahoo i rzadko robią problemy
    try:
        bench_data = yf.download(
            benchmarks,
            start=safe_download_start,
            end=end_date + timedelta(days=1),
            group_by='ticker',
            progress=False,
            threads=False
        )
        if not bench_data.empty:
            combined_df = pd.concat([combined_df, bench_data], axis=1)
    except Exception as e:
        logger.error(f"Benchmarks Download Error: {e}")

    # --- KROK B: Pobieramy Aktywa Użytkownika ---
    if user_tickers:
        try:
            # Tu może wystąpić błąd, jeśli user ma dziwny ticker
            user_data = yf.download(
                user_tickers,
                start=safe_download_start,
                end=end_date + timedelta(days=1),
                group_by='ticker',
                progress=False,
                threads=False
            )
            if not user_data.empty:
                # Łączymy kolumny (axis=1), ignorując duplikaty
                combined_df = pd.concat([combined_df, user_data], axis=1)
        except Exception as e:
            logger.error(f"User Assets Download Error: {e}")
            # Nawet jak to padnie, benchmarki z Kroku A zostają!

    return combined_df


def validate_ticker_and_price(symbol, date_obj, price_pln):
    """
    Sprawdza ticker w kolejności: Symbol -> Symbol.WA (Polska) -> Symbol.US.
    Zwraca (True, TICKER_KTÓRY_ZADZIAŁAŁ) tylko jeśli znajdzie PRAWIDŁOWE CENY.
    """
    import yfinance as yf
    from datetime import timedelta

    check_date_start = date_obj.date() - timedelta(days=5)
    check_date_end = date_obj.date() + timedelta(days=1)

    # --- POPRAWKA LISTY KANDYDATÓW ---
    # Yahoo Finance używa '.WA' dla GPW (Warsaw), a nie '.PL'!
    candidates = []
    if "." in symbol:
        candidates = [symbol]
    else:
        # Priorytet: Czysty symbol (np. BTC-USD), Polska (.WA), USA (.US)
        candidates = [symbol, symbol + ".WA", symbol + ".US"]

    best_df = None
    found_ticker = None

    # KROK 1: Szukanie danych
    for ticker in candidates:
        try:
            df = yf.download(ticker, start=check_date_start, end=check_date_end, progress=False)

            if df.empty:
                continue

                # Sprawdzamy czy są jakiekolwiek liczby
            if isinstance(df.columns, pd.MultiIndex):
                if df.isna().all().all():
                    continue
            else:
                if df['Close'].isna().all():
                    continue

            best_df = df
            found_ticker = ticker
            break

        except Exception:
            continue

    if not found_ticker or best_df is None:
        return False, f"Nie znaleziono notowań dla '{symbol}'. Sprawdzono warianty: {', '.join(candidates)}."

    # KROK 2: Walidacja Ceny
    try:
        if isinstance(best_df.columns, pd.MultiIndex):
            if found_ticker in best_df.columns.levels[0]:
                high_s = best_df[found_ticker]['High']
                low_s = best_df[found_ticker]['Low']
            else:
                # Fallback dla innej struktury
                high_s = best_df['High'][found_ticker]
                low_s = best_df['Low'][found_ticker]
        else:
            high_s = best_df['High']
            low_s = best_df['Low']

        max_price = float(high_s.max())
        min_price = float(low_s.min())

        if math.isnan(max_price) or math.isnan(min_price):
            return True, found_ticker

            # Widełki 50%
        safe_high = max_price * 1.50
        safe_low = min_price * 0.50
        price_val = float(price_pln)

        if not (safe_low <= price_val <= safe_high):
            return False, f"Cena podejrzana! Dla {found_ticker} zakres to {min_price:.2f}-{max_price:.2f}. Ty wpisałeś {price_val:.2f}."

        return True, found_ticker

    except Exception as e:
        logger.error(f"Validation Math Error: {e}")
        return True, found_ticker


def fetch_asset_metadata(yahoo_ticker):
    """
    Pobiera metadane z Yahoo Finance.
    """
    try:
        ticker = yf.Ticker(yahoo_ticker)
        info = ticker.info

        q_type = info.get('quoteType', '').upper()
        asset_type = AssetType.OTHER

        if q_type == 'EQUITY':
            asset_type = AssetType.STOCK
        elif q_type == 'ETF':
            asset_type = AssetType.ETF
        elif q_type == 'CRYPTOCURRENCY':
            asset_type = AssetType.CRYPTO
        elif q_type == 'CURRENCY':
            asset_type = AssetType.CURRENCY

        y_sector = info.get('sector', '').lower()
        asset_sector = AssetSector.OTHER

        if 'technology' in y_sector:
            asset_sector = AssetSector.TECHNOLOGY
        elif 'financial' in y_sector:
            asset_sector = AssetSector.FINANCE
        elif 'energy' in y_sector or 'oil' in y_sector:
            asset_sector = AssetSector.ENERGY
        elif 'healthcare' in y_sector or 'pharmaceutical' in y_sector:
            asset_sector = AssetSector.HEALTHCARE
        elif 'consumer' in y_sector:
            asset_sector = AssetSector.CONSUMER
        elif 'industrial' in y_sector:
            asset_sector = AssetSector.INDUSTRIAL
        elif 'real estate' in y_sector:
            asset_sector = AssetSector.REAL_ESTATE
        elif 'basic materials' in y_sector:
            asset_sector = AssetSector.MATERIALS
        elif 'communication' in y_sector or 'telecom' in y_sector:
            asset_sector = AssetSector.TELECOM

        y_industry = info.get('industry', '').lower()
        if 'games' in y_industry or 'gaming' in y_industry:
            asset_sector = AssetSector.GAMING

        return {
            'name': info.get('longName') or info.get('shortName'),
            'asset_type': asset_type,
            'sector': asset_sector,
            'success': True
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}