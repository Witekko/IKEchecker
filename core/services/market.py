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


from django.core.cache import cache
from core.config import SUMMARY_INDICES, SUMMARY_CURRENCIES, BENCHMARKS

def get_market_summary():
    """
    Pobiera zbiorcze dane rynkowe (Indeksy + Waluty) z 2 dni.
    Zwraca:
      1. 'rates': Słownik {Kod: Kurs} dla przeliczania walut portfela.
      2. 'summary': Lista słowników do karuzeli [{'symbol', 'display', 'price', 'change_pct'}]
    """
    # Cache na 15 minut, żeby nie katować API przy każdym odświeżeniu
    cached = cache.get('market_summary_v2')
    if cached:
        return cached

    indices = SUMMARY_INDICES
    currencies = SUMMARY_CURRENCIES
    
    tickers = list(indices.keys()) + currencies
    
    summary_list = []
    rates = getattr(settings, 'DEFAULT_CURRENCY_RATES', {}).copy()

    try:
        # Pobieramy 5 dni żeby mieć pewność że mamy "wczoraj" i "dziś" (weekendy)
        # threads=False rozwiązuje problemy z sqlite w dev serverze Django
        data = yf.download(tickers, period="1mo", group_by='ticker', progress=False, threads=False)
        
        # Helper do wyciągania danych
        def process_ticker(ticker_sym, display_name, is_currency=False):
            try:
                if ticker_sym not in data.columns.levels[0]: return None
                series = data[ticker_sym]['Close'].dropna()
                if len(series) < 2: return None
                
                price_now = float(series.iloc[-1])
                price_prev = float(series.iloc[-2])
                
                change_pct = ((price_now - price_prev) / price_prev) * 100
                
                # Jeśli waluta (np. JPY), to czasem trzeba skalować, ale tu trzymamy raw
                if is_currency and "JPY" in ticker_sym: 
                    # JPY w Yahoo to często ~2-3 (za 100 JPY?), ale standardowo dla usera chcemy kurs 1 JPY lub 100 JPY.
                    # Wcześniejszy kod mnożył przez 100. Utrzymajmy spójność.
                    price_now *= 100
                
                return {
                    'symbol': display_name,
                    'price': price_now,
                    'change_pct': change_pct,
                    'is_up': change_pct >= 0
                }
            except Exception as e:
                logger.warning(f"Error processing {ticker_sym}: {e}")
                return None

        # 1. Przetwarzamy Indeksy
        for tick, name in indices.items():
            try:
                res = process_ticker(tick, name)
                
                # Fallback: Jeśli history nie dało danych (np. 1 wiersz), spróbujmy wyciągnąć z .info
                if not res:
                    try:
                        t_obj = yf.Ticker(tick)
                        info = t_obj.info
                        # Szukamy ceny i prev_close
                        price_now = info.get('regularMarketPrice') or info.get('currentPrice')
                        price_prev = info.get('regularMarketPreviousClose')
                        
                        if price_now and price_prev and price_prev > 0:
                            change_pct = ((price_now - price_prev) / price_prev) * 100
                            res = {
                                'symbol': name,
                                'price': price_now,
                                'change_pct': change_pct,
                                'is_up': change_pct >= 0
                            }
                    except Exception as fallback_err:
                         logger.warning(f"Fallback failed for {tick}: {fallback_err}")
                         pass

                if res: summary_list.append(res)
            except Exception as e:
                logger.warning(f"Error processing {tick}: {e}")
                continue
            
        # 2. Przetwarzamy Waluty (do listy i do rates)
        curr_map = {'USDPLN=X': 'USD', 'EURPLN=X': 'EUR', 'GBPPLN=X': 'GBP', 'JPYPLN=X': 'JPY', 'AUDPLN=X': 'AUD'}
        for tick in currencies:
            code = curr_map.get(tick)
            item = process_ticker(tick, code, is_currency=True)
            if item:
                summary_list.append(item)
                rates[code] = round(item['price'], 4 if code == 'JPY' else 4) # Precyzja

    except Exception as e:
        logger.error(f"Market Summary Error: {e}")

    result = {'rates': rates, 'summary': summary_list}
    cache.set('market_summary_v2', result, 900) # 15 min
    return result

def get_current_currency_rates():
    """ Wrapper zachowujący kompatybilność wsteczną """
    data = get_market_summary()
    return data['rates']


def update_prices_bulk(assets_list):
    """
    Sprawdza, które aktywa są 'przestarzałe' (>15 min) i pobiera ich ceny W JEDNYM zapytaniu.
    Optymalizacja N+1 zapytań HTTP.
    """
    now = timezone.now()
    stale_assets = []
    
    # 1. Filtrujemy tylko te, które wymagają aktualizacji
    for asset in assets_list:
        if not asset.yahoo_ticker: continue
        needs_update = False
        if not asset.last_updated:
            needs_update = True
        else:
            diff = now - asset.last_updated
            if diff.total_seconds() > 900: # 15 min
                needs_update = True
        
        if needs_update:
            stale_assets.append(asset)
            
    if not stale_assets:
        return 0 # Nic do roboty, cache jest świeży
        
    tickers = [a.yahoo_ticker for a in stale_assets]
    logger.info(f"BULK UPDATE: Fetching data for {len(tickers)} assets...")

    try:
        # 2. Jedno duże zapytanie
        data = yf.download(tickers, period="5d", group_by='ticker', progress=False, threads=False)
        
        updated_count = 0
        
        # 3. Parsowanie wyników
        for asset in stale_assets:
            try:
                tk = asset.yahoo_ticker
                
                # Obsługa MultiIndex (jeśli >1 ticker) lub Flat Index (jeśli 1 ticker)
                if len(tickers) == 1:
                     # yfinance zwraca płaski index przy 1 tickerze, wkurzające :)
                     # Ale group_by='ticker' powinien to ogarnąć? Nie zawsze.
                     # Spróbujmy uniwersalnie:
                     if isinstance(data.columns, pd.MultiIndex):
                         # Raczej nie wejdzie tutaj przy 1 elemencie ale na wszelki wypadek
                         if tk in data.columns.levels[0]:
                             df = data[tk]
                         else:
                             continue
                     else:
                         df = data # Cała ramka to ten ticker
                else:
                    if tk not in data.columns.levels[0]:
                        continue
                    df = data[tk]
                
                if 'Close' not in df.columns: continue
                
                valid = df['Close'].dropna()
                if valid.empty: continue
                
                price = float(valid.iloc[-1])
                prev_close = float(valid.iloc[-2]) if len(valid) >= 2 else price
                
                if price > 0:
                    asset.last_price = price
                    asset.previous_close = prev_close
                    asset.last_updated = now
                    asset.save()
                    updated_count += 1
                    
            except Exception as e:
                logger.warning(f"Bulk update error for {asset.symbol}: {e}")
                continue
                
        logger.info(f"BULK UPDATE: Success for {updated_count}/{len(tickers)} assets.")
        return updated_count

    except Exception as e:
        logger.error(f"BULK UPDATE FATAL: {e}")
        return 0


def get_cached_price(asset: Asset):
    """
    Pobiera cenę jednego aktywa.
    Teraz ta funkcja powinna być wołana PO 'update_prices_bulk', więc trafi w świeże dane w bazie.
    Jeśli nie, zrobi fallback do individual fetch (stara logika).
    """
    now = timezone.now()
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:
            return float(asset.last_price), float(asset.previous_close)

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        price = 0.0
        prev_close = 0.0

        # 1. Próba z historią
        data = ticker.history(period='5d')
        if not data.empty and 'Close' in data.columns:
            valid = data['Close'].dropna()
            if not valid.empty:
                price = float(valid.iloc[-1])
                prev_close = float(valid.iloc[-2]) if len(valid) >= 2 else price

        # 2. Fallback: Jeśli historia pusta, bierzemy aktualną wycenę (Quote)
        if price <= 0:
            info = ticker.info
            # Różne pola, w których Yahoo może ukryć cenę
            price = info.get('currentPrice') or info.get('regularMarketPrice') or info.get('price') or 0.0
            prev_close = info.get('regularMarketPreviousClose') or price

        if price > 0:
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
    Pobiera dane historyczne.
    GWARANCJA: Indeks to zawsze obiekty datetime.date. Kolumny to zawsze MultiIndex (Ticker, Pole).
    """
    end_date = date.today()
    safe_download_start = start_date - timedelta(days=730)

    benchmarks = [BENCHMARKS['SP500'], 'USDPLN=X', 'EURPLN=X', 'GBPPLN=X', BENCHMARKS['WIG'], BENCHMARKS['ACWI']]

    # Unikalne tickery usera bez benchmarków
    user_tickers = list(set(assets_tickers))
    user_tickers = [t for t in user_tickers if t not in benchmarks]

    combined_df = pd.DataFrame()

    def process_download(tickers_list):
        if not tickers_list: return pd.DataFrame()
        try:
            df = yf.download(
                tickers_list,
                start=safe_download_start,
                end=end_date + timedelta(days=1),
                group_by='ticker',
                progress=False,
                threads=False
            )
            if df.empty: return pd.DataFrame()

            # 1. STANDARYZACJA INDEKSU (Na datetime.date)
            # Najpierw konwersja na datetime (usuwa śmieci), potem tz_localize(None), potem date
            df.index = pd.to_datetime(df.index)
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)
            df.index = df.index.date

            # 2. STANDARYZACJA KOLUMN (Zawsze MultiIndex)
            # Jeśli pobraliśmy 1 ticker, yfinance daje Flat Index. Naprawiamy to.
            if len(tickers_list) == 1 and not isinstance(df.columns, pd.MultiIndex):
                df.columns = pd.MultiIndex.from_product([tickers_list, df.columns])

            return df
        except Exception as e:
            logger.error(f"Download Error for {tickers_list}: {e}")
            return pd.DataFrame()

    # A. Benchmarki
    bench_df = process_download(benchmarks)
    if not bench_df.empty:
        combined_df = pd.concat([combined_df, bench_df], axis=1)

    # Retry missing benchmarks
    existing_tickers = []
    if not combined_df.empty and isinstance(combined_df.columns, pd.MultiIndex):
        existing_tickers = combined_df.columns.levels[0].tolist()
    
    for b in benchmarks:
        if b not in existing_tickers:
            try:
                single = yf.download(b, start=safe_download_start, end=end_date + timedelta(days=1), progress=False, threads=False)
                if not single.empty:
                    # Fix single index columns
                    if not isinstance(single.columns, pd.MultiIndex):
                         single.columns = pd.MultiIndex.from_product([[b], single.columns])
                    
                    # Align dates
                    single.index = pd.to_datetime(single.index)
                    if single.index.tz is not None: single.index = single.index.tz_localize(None)
                    single.index = single.index.date
                    
                    combined_df = pd.concat([combined_df, single], axis=1)
            except:
                pass

    # B. User Assets
    if user_tickers:
        user_df = process_download(user_tickers)
        if not user_df.empty:
            combined_df = pd.concat([combined_df, user_df], axis=1)

    # Sprzątanie
    combined_df = combined_df.loc[:, ~combined_df.columns.duplicated()]
    combined_df.sort_index(inplace=True)

    return combined_df


def validate_ticker_and_price(symbol, date_obj, price_pln):
    """
    Sprawdza ticker w kolejności: Symbol -> Symbol.WA -> Symbol.US.
    """
    import yfinance as yf
    from datetime import timedelta

    check_date_start = date_obj.date() - timedelta(days=5)
    check_date_end = date_obj.date() + timedelta(days=1)

    candidates = []
    if "." in symbol:
        candidates = [symbol]
    else:
        candidates = [symbol, symbol + ".WA", symbol + ".US"]

    best_df = None
    found_ticker = None

    # KROK 1: Szukanie danych
    for ticker in candidates:
        try:
            df = yf.download(ticker, start=check_date_start, end=check_date_end, progress=False)

            if df.empty: continue

            # Sprawdzamy czy są liczby (nie same NaN)
            if isinstance(df.columns, pd.MultiIndex):
                if df.isna().all().all(): continue
            else:
                if df['Close'].isna().all(): continue

            best_df = df
            found_ticker = ticker
            break
        except Exception:
            continue

    if not found_ticker or best_df is None:
        return False, f"Nie znaleziono notowań dla '{symbol}'. Sprawdzono: {', '.join(candidates)}."

    # KROK 2: Walidacja Ceny
    try:
        # Wyciągamy High/Low zależnie od struktury (MultiIndex lub nie)
        if isinstance(best_df.columns, pd.MultiIndex):
            if found_ticker in best_df.columns.levels[0]:
                high_s = best_df[found_ticker]['High']
                low_s = best_df[found_ticker]['Low']
            else:
                # Fallback
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

        # Proste mapowanie sektorów
        if 'technology' in y_sector:
            asset_sector = AssetSector.TECHNOLOGY
        elif 'financial' in y_sector:
            asset_sector = AssetSector.FINANCE
        elif 'energy' in y_sector or 'oil' in y_sector:
            asset_sector = AssetSector.ENERGY
        elif 'healthcare' in y_sector:
            asset_sector = AssetSector.HEALTHCARE
        elif 'consumer' in y_sector:
            asset_sector = AssetSector.CONSUMER
        elif 'real estate' in y_sector:
            asset_sector = AssetSector.REAL_ESTATE
        elif 'basic materials' in y_sector:
            asset_sector = AssetSector.MATERIALS
        elif 'communication' in y_sector:
            asset_sector = AssetSector.TELECOM
        elif 'industrial' in y_sector:
            asset_sector = AssetSector.INDUSTRIAL

        return {
            'name': info.get('longName') or info.get('shortName'),
            'asset_type': asset_type,
            'sector': asset_sector,
            'success': True,
            # FIX: Zwracamy walutę dla Importera (np. ISAC.L -> USD)
            'currency': info.get('currency', 'PLN')
        }

    except Exception as e:
        return {'success': False, 'error': str(e)}