# core/services/news.py

import feedparser
import urllib.parse
import difflib
from datetime import date
import logging

logger = logging.getLogger('core')

# 1. Źródła płatne/niechciane
BLOCKED_SOURCES = ['puls biznesu', 'pb.pl', 'wyborcza.biz', 'przegląd sportowy', 'sport.pl', 'meczyki']

# 2. Źródła preferowane (darmowe i dobrej jakości)
PREFERRED_SOURCES = ['bankier', 'stockwatch', 'stooq', 'pap', 'biznes.pl', 'parkiet', 'money.pl', 'infostrefa']

# 3. Tickery "Słowa Pospolite" - wymagają specjalnego traktowania
AMBIGUOUS_TICKERS = {
    'PAS', 'DOM', 'TOR', 'KOG', 'LEN', 'AUTO', 'DATA', 'TEST', 'O2O', 'VIGO', 'ABC', 'BBT', 'BETA', 'ACT'
}


def get_asset_news(symbol, name):
    news_list = []

    # Proste czyszczenie nazwy
    clean_name = name.split(' ')[0].strip()
    # Usuwamy ewentualne kropki z nazwy (np. "Passus S.A." -> "Passus")
    clean_name = clean_name.replace(',', '').replace('.', '')

    query = ""
    is_ambiguous = False

    if symbol.endswith('.PL'):
        ticker_clean = symbol.replace('.PL', '')

        # Sprawdzamy, czy ticker jest na czarnej liście
        is_ambiguous = ticker_clean in AMBIGUOUS_TICKERS

        # Czy nazwa jest bezpieczna? (Dłuższa niż 2 znaki i nie jest tożsama z tickerem)
        # Np. Name="Passus", Ticker="PAS" -> SAFE.
        # Np. Name="PAS", Ticker="PAS" -> UNSAFE.
        is_name_safe = (clean_name.upper() != ticker_clean) and (len(clean_name) > 2)

        if is_ambiguous:
            if is_name_safe:
                # STRATEGIA 1: Mamy bezpieczną nazwę (Passus). OLEWAMY ticker "PAS".
                # Szukamy tylko po nazwie, bo słowo "Passus" nie występuje w sporcie.
                query = f'"{clean_name}"'
            else:
                # STRATEGIA 2: Nazwa to też "PAS". Musimy szukać z kontekstem, ale BEZ słów sportowych.
                # Wyrzuciłem "akcje" (akcja w ringu) i "wyniki" (wynik meczu).
                strict_context = '("giełda" OR "notowania" OR "dywidenda" OR "emitent" OR "ESPI" OR "GPW" OR "inwestor")'
                query = f'("{ticker_clean}" AND {strict_context})'
        else:
            # STRATEGIA 3: Normalne spółki (np. CDR, PKO).
            # Tu możemy pozwolić sobie na szerszy kontekst.
            query = f'"{clean_name}" OR "{ticker_clean}"'

        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'pl', 'gl': 'PL', 'ceid': 'PL:pl'}

    else:
        # Zagraniczne
        query = f'"{clean_name}" stock'
        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'}

    encoded_query = urllib.parse.urlencode(params)
    rss_url = f"{base_url}?{encoded_query}"

    try:
        feed = feedparser.parse(rss_url)
        today = date.today()
        candidates = []

        # Pobieramy 40, żeby po ostrym filtrowaniu coś zostało
        for entry in feed.entries[:40]:
            source_name = entry.source.title if hasattr(entry, 'source') else 'Google'
            source_lower = source_name.lower()
            title_lower = entry.title.lower()

            # A. Filtracja Źródeł (Dodatkowo blokujemy sportowe)
            if any(blocked in source_lower for blocked in BLOCKED_SOURCES):
                continue

            # B. Dodatkowe zabezpieczenie treści dla "PAS"
            # Jeśli w tytule jest "mistrzowski", "waga", "gala", "ring" -> odrzucamy
            if is_ambiguous and any(sport_word in title_lower for sport_word in
                                    ['mistrzowski', 'waga', 'gala', 'ring', 'ksw', 'ufc', 'autostrada', 'drogowy']):
                continue

            # C. Priorytetyzacja
            priority_score = 0
            if any(pref in source_lower for pref in PREFERRED_SOURCES):
                priority_score = 10

            # Data
            dt_obj = date(2000, 1, 1)
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

            tags = []
            if 'espi' in title_lower or 'ebi' in title_lower: tags.append('OFFICIAL')
            if 'dywidend' in title_lower: tags.append('MONEY')
            if 'wyniki' in title_lower and 'finans' in title_lower: tags.append('RESULTS')  # Tylko "wyniki finansowe"
            if 'rekomendacj' in title_lower: tags.append('RECO')

            candidates.append({
                'title': entry.title,
                'link': entry.link,
                'source': source_name,
                'date_label': date_label,
                'date_obj': dt_obj,
                'freshness': freshness,
                'tags': tags,
                'priority': priority_score
            })

        # D. Sortowanie i Deduplikacja
        candidates.sort(key=lambda x: x['priority'], reverse=True)
        unique_news = []
        seen_titles = []

        for item in candidates:
            title = item['title']
            is_duplicate = False
            for seen in seen_titles:
                if difflib.SequenceMatcher(None, title, seen).ratio() > 0.85:
                    is_duplicate = True;
                    break
            if not is_duplicate:
                unique_news.append(item)
                seen_titles.append(title)

        unique_news.sort(key=lambda x: x['date_obj'], reverse=True)
        news_list = unique_news[:8]

    except Exception as e:
        logger.error(f"News Error: {e}")

    return news_list