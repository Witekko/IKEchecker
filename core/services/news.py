# core/services/news.py

import feedparser
import urllib.parse
import difflib
from datetime import date, datetime
import logging

logger = logging.getLogger('core')

# Konfiguracja źródeł
BLOCKED_SOURCES = ['puls biznesu', 'pb.pl', 'wyborcza.biz']
PREFERRED_SOURCES = ['bankier', 'stockwatch', 'stooq', 'pap', 'biznes.pl', 'parkiet']


def get_asset_news(symbol, name):
    news_list = []
    clean_name = name.split(' ')[0]

    # Budowanie zapytania (bez zmian)
    if symbol.endswith('.PL'):
        ticker_clean = symbol.replace('.PL', '')
        query = f'"{clean_name}" OR "{ticker_clean}"'
        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'pl', 'gl': 'PL', 'ceid': 'PL:pl'}
    else:
        query = f'"{clean_name}" stock'
        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'}

    encoded_query = urllib.parse.urlencode(params)
    rss_url = f"{base_url}?{encoded_query}"

    try:
        feed = feedparser.parse(rss_url)
        today = date.today()

        # 1. Faza wstępna: Pobierz i przetwórz więcej kandydatów (30)
        candidates = []

        for entry in feed.entries[:30]:
            source_name = entry.source.title if hasattr(entry, 'source') else 'Google'
            source_lower = source_name.lower()

            # A. Filtracja Paywalla (Wyrzucamy Puls Biznesu)
            if any(blocked in source_lower for blocked in BLOCKED_SOURCES):
                continue

            # B. Ocena źródła (Bonus dla Bankiera/StockWatch)
            priority_score = 0
            if any(pref in source_lower for pref in PREFERRED_SOURCES):
                priority_score = 10  # Wysoki priorytet

            # Parsowanie daty
            dt_obj = date(2000, 1, 1)  # Fallback
            date_label = "Recent"
            freshness = 2

            if hasattr(entry, 'published_parsed'):
                try:
                    dt_obj = date(entry.published_parsed.tm_year, entry.published_parsed.tm_mon,
                                  entry.published_parsed.tm_mday)
                    delta = (today - dt_obj).days
                    if delta <= 1:
                        date_label = "TODAY 🔥" if delta == 0 else "YESTERDAY";
                        freshness = 0
                    elif delta <= 7:
                        date_label = dt_obj.strftime("%Y-%m-%d");
                        freshness = 1
                    else:
                        date_label = dt_obj.strftime("%Y-%m-%d");
                        freshness = 2
                except:
                    pass

            # Tagi
            tags = []
            title_lower = entry.title.lower()
            if 'espi' in title_lower or 'ebi' in title_lower or 'raport' in title_lower: tags.append('OFFICIAL')
            if 'dywidend' in title_lower or 'dividend' in title_lower: tags.append('MONEY')
            if 'wyniki' in title_lower or 'results' in title_lower: tags.append('RESULTS')
            if 'rekomendacj' in title_lower or 'recommendation' in title_lower: tags.append('RECO')

            candidates.append({
                'title': entry.title,
                'link': entry.link,
                'source': source_name,
                'date_label': date_label,
                'date_obj': dt_obj,
                'freshness': freshness,
                'tags': tags,
                'priority': priority_score  # Klucz do sortowania przed deduplikacją
            })

        # 2. Sortowanie po Priorytecie (Najpierw "Dobre Źródła", potem reszta)
        # Dzięki temu przy usuwaniu duplikatów, zachowamy wersję z lepszego źródła
        candidates.sort(key=lambda x: x['priority'], reverse=True)

        # 3. Deduplikacja (Zachowujemy pierwszy napotkany - czyli ten o wyższym priorytecie)
        unique_news = []
        seen_titles = []

        for item in candidates:
            title = item['title']
            is_duplicate = False
            for seen in seen_titles:
                # Jeśli podobieństwo > 60%, traktujemy jako duplikat
                if difflib.SequenceMatcher(None, title, seen).ratio() > 0.60:
                    is_duplicate = True
                    break

            if not is_duplicate:
                unique_news.append(item)
                seen_titles.append(title)

        # 4. Sortowanie końcowe po dacie (Najnowsze na górze)
        unique_news.sort(key=lambda x: x['date_obj'], reverse=True)

        # 5. Przycięcie do 6 sztuk
        news_list = unique_news[:6]

    except Exception as e:
        logger.error(f"News Error: {e}")

    return news_list