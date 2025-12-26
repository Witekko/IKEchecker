# core/services/dividends.py

from ..models import Transaction, Portfolio
from .market import get_current_currency_rates
from .config import fmt_2


def get_dividend_context(user):
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {}

    # 1. Pobieramy słownik kursów {'EUR': 4.30, 'USD': 4.00, ...}
    rates = get_current_currency_rates()

    txs = Transaction.objects.filter(portfolio=portfolio, type__in=['DIVIDEND', 'TAX']).order_by('date')

    total_received_pln = 0.0
    total_tax_pln = 0.0
    yearly_data = {}
    monthly_data = {}
    payers = {}
    available_years = set()

    for t in txs:
        amt = float(t.amount)

        # 2. Inteligentne przeliczanie walut
        multiplier = 1.0
        if t.asset and t.asset.currency != 'PLN':
            # Pobierz kurs ze słownika, jeśli brak to 1.0
            # Uwaga: Dla JPY w market.py mamy cenę za 100 sztuk, tutaj zakładamy standardowe przeliczanie
            # Jeśli market.py zwraca JPY=2.60 (za 100), to musimy to podzielić.
            curr = t.asset.currency
            if curr == 'JPY':
                multiplier = rates.get('JPY', 1.0) / 100
            else:
                multiplier = rates.get(curr, 1.0)

            amt *= multiplier

        net_amount = amt
        if t.type == 'DIVIDEND':
            total_received_pln += amt
        elif t.type == 'TAX':
            total_tax_pln += abs(amt)

        year = t.date.year
        month = t.date.month - 1  # 0-11 dla JS

        available_years.add(year)
        yearly_data[year] = yearly_data.get(year, 0.0) + net_amount

        if year not in monthly_data:
            monthly_data[year] = [0.0] * 12
        monthly_data[year][month] += net_amount

        if t.type == 'DIVIDEND' and t.asset:
            sym = t.asset.symbol
            payers[sym] = payers.get(sym, 0.0) + amt

    sorted_years = sorted(list(available_years))
    yearly_values = [round(yearly_data.get(y, 0), 2) for y in sorted_years]

    # Sortowanie płatników
    sorted_payers = sorted(payers.items(), key=lambda item: item[1], reverse=True)
    top_payers_list = [{'symbol': k, 'amount': fmt_2(v)} for k, v in sorted_payers]

    # Przygotowanie danych miesięcznych dla wykresu (ostatni dostępny rok jako domyślny)
    current_year_monthly = monthly_data.get(sorted_years[-1], [0] * 12) if sorted_years else [0] * 12

    return {
        'total_net': fmt_2(total_received_pln - total_tax_pln),
        'total_gross': fmt_2(total_received_pln),
        'total_tax': fmt_2(total_tax_pln),
        'top_payer': top_payers_list[0] if top_payers_list else None,
        'payers_list': top_payers_list,

        # Dane do wykresów
        'years_labels': sorted_years,
        'years_data': yearly_values,
        'monthly_data': current_year_monthly,  # Domyślnie ostatni rok
        'all_monthly_data': monthly_data,  # Pełne dane do przełączania w JS (opcjonalnie)
    }