# core/services/utils.py

from datetime import date, timedelta, datetime


def calculate_range_dates(range_mode):
    """
    Zwraca datę początkową na podstawie wybranego zakresu (1m, 3m, ytd, etc.).
    """
    today = date.today()
    if range_mode == '1m':
        return today - timedelta(days=30)
    elif range_mode == '3m':
        return today - timedelta(days=90)
    elif range_mode == '6m':
        return today - timedelta(days=180)
    elif range_mode == 'ytd':
        return date(today.year, 1, 1)
    elif range_mode == '1y':
        return today - timedelta(days=365)
    return None


def filter_timeline(timeline, start_date):
    """
    Filtruje dane wykresu (timeline) od podanej daty startowej.
    """
    if not start_date:
        return timeline

    dates_str = timeline.get('dates', [])
    if not dates_str:
        return timeline

    start_idx = 0
    for i, d_str in enumerate(dates_str):
        try:
            if datetime.strptime(d_str, "%Y-%m-%d").date() >= start_date:
                start_idx = i
                break
        except:
            pass

    filtered = {}
    for key, val in timeline.items():
        if isinstance(val, list) and len(val) == len(dates_str):
            filtered[key] = val[start_idx:]
        else:
            filtered[key] = val
    return filtered