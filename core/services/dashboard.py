# core/services/dashboard.py

from ..models import Transaction
from .market import get_current_currency_rates
from .analytics import analyze_history, analyze_holdings
from .performance import PerformanceCalculator
from .config import fmt_2
from .portfolio import get_dashboard_context as get_base_context
# FIX: Import musi pasować do nazwy funkcji w utils.py (filter_timeline)
from .utils import calculate_range_dates, filter_timeline


def get_dashboard_stats_context(active_portfolio, range_mode='all'):
    """
    Fasada obliczająca statystyki MWR/TWR/ROI oraz dane wykresu
    dla wybranego zakresu czasu. Zwraca czysty słownik do contextu.
    """
    start_date = calculate_range_dates(range_mode)
    transactions = Transaction.objects.filter(portfolio=active_portfolio)

    # Jeśli brak transakcji, zwracamy puste dane
    if not transactions.exists():
        return {
            'tile_mwr': "0.00",
            'tile_twr': "0.00",
            'tile_return_pct_str': "0.00",
            'tile_return_pct_raw': 0.0,
            'tile_total_profit_str': "0.00",
            'tile_total_profit_raw': 0.0,
            'timeline_dates': [],
            'timeline_total_value': [],
            'timeline_invested': [],
        }

    # 1. Pobierz kursy i dane analityczne
    rates = get_current_currency_rates()
    full_timeline = analyze_history(transactions, rates)
    stats = analyze_holdings(transactions, rates)  # stats['total_value'] potrzebne do MWR
    current_val = stats['total_value']

    # 2. Oblicz wskaźniki (Performance)
    perf = PerformanceCalculator(transactions)
    metrics = perf.calculate_metrics(
        timeline_data=full_timeline,
        start_date=start_date,
        current_total_value=current_val
    )

    twr_percent = perf.calculate_twr(full_timeline, start_date_filter=start_date)

    # 3. Filtruj wykres pod zakres
    filtered_timeline = filter_timeline(full_timeline, start_date)

    # 4. Spakuj wyniki (Bez try-except w widoku!)
    return {
        'tile_mwr': fmt_2(metrics['xirr']),
        'tile_twr': fmt_2(twr_percent),
        'tile_return_pct_str': fmt_2(metrics['simple_return']),
        'tile_return_pct_raw': float(metrics['simple_return']),
        'tile_total_profit_str': fmt_2(metrics['profit']),
        'tile_total_profit_raw': float(metrics['profit']),

        # Wykres
        'timeline_dates': filtered_timeline.get('dates', []),
        'timeline_total_value': filtered_timeline.get('val_user', []),
        'timeline_invested': filtered_timeline.get('val_inv', []),
        'timeline_deposit_points': filtered_timeline.get('points', []),
        'timeline_pct_user': filtered_timeline.get('pct_user', []),
        'timeline_pct_wig': filtered_timeline.get('pct_wig', []),
        'timeline_pct_sp500': filtered_timeline.get('pct_sp', []),
        'timeline_pct_inflation': filtered_timeline.get('pct_inf', []),
    }


def get_holdings_view_context(user, portfolio, range_mode='all'):
    """
    Przygotowuje pełny kontekst dla widoku Assets List.
    Łączy bazowy kontekst dashboardu + statystyki okresowe.
    """
    start_date = calculate_range_dates(range_mode)

    # 1. Bazowy kontekst (kafelki alokacji, ogólne dane)
    context = get_base_context(user, portfolio_id=portfolio.id)

    # 2. Statystyki wydajności (te same co na dashboardzie - MWR/TWR)
    # Żeby kafelki na górze tabeli też reagowały na filtr czasu
    perf_context = get_dashboard_stats_context(portfolio, range_mode)
    context.update(perf_context)

    # 3. Szczegółowa analiza holdings z uwzględnieniem start_date
    # To nadpisze niektóre pola w assets (np. gain_pln, gain_percent) jeśli start_date jest ustawione
    transactions = Transaction.objects.filter(portfolio=portfolio)
    rates = get_current_currency_rates()

    dynamic_stats = analyze_holdings(transactions, rates, start_date=start_date)

    # 4. Wzbogacenie listy assetów (formatowanie, kolory) - korzystamy z istniejącego helpera
    from .portfolio import enrich_assets_context
    enrich_assets_context(context, dynamic_stats['assets'], dynamic_stats['total_value'])

    return context