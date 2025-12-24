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
    """
    Fasada: Agreguje dane z modułów market, portfolio i timeline.
    """
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {'error': 'No portfolio found.'}

    eur_rate, usd_rate = get_current_currency_rates()
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('date')

    current_state = calculate_current_holdings(transactions, eur_rate, usd_rate)
    timeline_data = calculate_historical_timeline(transactions, eur_rate, usd_rate)

    context = current_state.copy()
    context.update({
        'eur_rate': fmt_2(eur_rate),
        'usd_rate': fmt_2(usd_rate),
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
        'chart_labels': current_state['charts']['labels'],
        'chart_allocation': current_state['charts']['allocation'],
        'chart_profit_labels': current_state['charts']['profit_labels'],
        'chart_profit_values': current_state['charts']['profit_values'],
        'closed_labels': current_state['charts']['closed_labels'],
        'closed_values': current_state['charts']['closed_values'],

        # Nowe sumy tabel
        'totals_pln': current_state.get('totals_pln'),
        'totals_foreign': current_state.get('totals_foreign'),
    })

    return context