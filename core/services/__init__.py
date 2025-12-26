# core/services/__init__.py

from .config import TICKER_CONFIG, fmt_2, fmt_4
from .market import get_current_currency_rates, get_cached_price
from .importer import process_xtb_file
from .news import get_asset_news
from .dividends import get_dividend_context
from .portfolio import (
    calculate_current_holdings,
    calculate_historical_timeline,
    get_asset_details_context
)
from ..models import Portfolio, Transaction


def get_dashboard_context(user):
    # 1. Pobieramy słownik wszystkich walut (EUR, USD, GBP, AUD, JPY)
    # Robimy to na początku, żeby mieć dane nawet dla pustego portfela
    rates = get_current_currency_rates()

    # 2. Szukamy portfela użytkownika
    portfolio = Portfolio.objects.filter(user=user).first()

    # --- FIX: OBSŁUGA NOWEGO UŻYTKOWNIKA (EMPTY STATE) ---
    if not portfolio:
        # Zwracamy "sztuczne" zera i słownik walut.
        # Dzięki temu w dashboard.html zadziała warunek {% if invested == "0.00" %}
        # i wyświetli się ekran powitalny (Rakieta), a w nagłówku będą kursy walut.
        return {
            'invested': "0.00",
            'cash': "0.00",
            'rates': rates,
        }

    # 3. Jeśli portfel istnieje, pobieramy transakcje i liczymy resztę
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('date')

    # Wyciągamy kursy dla funkcji obliczeniowych
    # Używamy .get() z wartością domyślną dla bezpieczeństwa
    eur = rates.get('EUR', 4.30)
    usd = rates.get('USD', 4.00)

    # Przekazujemy EUR i USD do obliczeń (zgodnie z obecną strukturą portfolio.py)
    current_state = calculate_current_holdings(transactions, eur, usd)
    timeline_data = calculate_historical_timeline(transactions, eur, usd)

    context = current_state.copy()
    context.update({
        # 4. Przekazujemy pełny słownik walut do szablonu (dla paska w nagłówku)
        'rates': rates,

        'timeline_dates': timeline_data.get('dates', []),
        'timeline_deposit_points': timeline_data.get('points', []),
        'timeline_total_value': timeline_data.get('val_user', []),
        'timeline_invested': timeline_data.get('val_inv', []),
        'timeline_wig': timeline_data.get('val_wig', []),
        'timeline_sp500': timeline_data.get('val_sp', []),
        'timeline_inflation': timeline_data.get('val_inf', []),
        'timeline_pct_user': timeline_data.get('pct_user', []),
        'timeline_pct_wig': timeline_data.get('pct_wig', []),
        'timeline_pct_sp500': timeline_data.get('pct_sp', []),
        'timeline_pct_inflation': timeline_data.get('pct_inf', []),

        # Dane do wykresów kołowych i słupkowych
        'chart_labels': current_state['charts']['labels'],
        'chart_allocation': current_state['charts']['allocation'],
        'chart_profit_labels': current_state['charts']['profit_labels'],
        'chart_profit_values': current_state['charts']['profit_values'],
        'closed_labels': current_state['charts']['closed_labels'],
        'closed_values': current_state['charts']['closed_values'],

        # Podsumowania tabel
        'totals_pln': current_state.get('totals_pln'),
        'totals_foreign': current_state.get('totals_foreign'),
    })

    return context