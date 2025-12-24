# core/services/news.py

import feedparser
import urllib.parse
import difflib
from datetime import date, timedelta


def get_asset_news(symbol, name):
    news_list = []
    clean_name = name.split(' ')[0]

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
        seen_titles = []
        for entry in feed.entries[:15]:
            title = entry.title

            # Usuwanie duplikatów
            is_duplicate = False
            for seen in seen_titles:
                if difflib.SequenceMatcher(None, title, seen).ratio() > 0.60:
                    is_duplicate = True;
                    break
            if is_duplicate: continue
            seen_titles.append(title)

            dt_obj = date(2000, 1, 1)
            date_label = "Recent"
            freshness = 2

            if hasattr(entry, 'published_parsed'):
                try:
                    dt_obj = date(entry.published_parsed.tm_year, entry.published_parsed.tm_mon,
                                  entry.published_parsed.tm_mday)
                    delta = (today - dt_obj).days
                    if delta <= 1:
                        date_label = "TODAY 🔥" if delta == 0 else "YESTERDAY"; freshness = 0
                    elif delta <= 7:
                        date_label = dt_obj.strftime("%Y-%m-%d"); freshness = 1
                    else:
                        date_label = dt_obj.strftime("%Y-%m-%d"); freshness = 2
                except:
                    pass

            tags = []
            title_lower = entry.title.lower()
            if 'espi' in title_lower or 'ebi' in title_lower or 'raport' in title_lower: tags.append('OFFICIAL')
            if 'dywidend' in title_lower or 'dividend' in title_lower: tags.append('MONEY')
            if 'wyniki' in title_lower or 'results' in title_lower: tags.append('RESULTS')

            news_list.append({
                'title': entry.title,
                'link': entry.link,
                'source': entry.source.title if hasattr(entry, 'source') else 'Google',
                'date_label': date_label,
                'date_obj': dt_obj,
                'freshness': freshness,
                'tags': tags
            })

        news_list.sort(key=lambda x: x['date_obj'], reverse=True)
        news_list = news_list[:6]
    except Exception as e:
        print(f"News Error: {e}")

    return news_list