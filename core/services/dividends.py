# core/services/dividends.py

from ..models import Transaction, Portfolio
from .market import get_current_currency_rates
from .config import fmt_2


def get_dividend_context(user):
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {}
    eur, usd = get_current_currency_rates()
    txs = Transaction.objects.filter(portfolio=portfolio, type__in=['DIVIDEND', 'TAX']).order_by('date')

    total_received_pln = 0.0
    total_tax_pln = 0.0
    yearly_data = {}
    monthly_data = {}
    payers = {}
    available_years = set()

    for t in txs:
        amt = float(t.amount)
        if t.asset:
            if t.asset.currency == 'EUR':
                amt *= eur
            elif t.asset.currency == 'USD':
                amt *= usd

        net_amount = amt
        if t.type == 'DIVIDEND':
            total_received_pln += amt
        elif t.type == 'TAX':
            total_tax_pln += abs(amt)

        year = t.date.year;
        month = t.date.month - 1
        available_years.add(year)
        yearly_data[year] = yearly_data.get(year, 0.0) + net_amount
        if year not in monthly_data: monthly_data[year] = [0.0] * 12
        monthly_data[year][month] += net_amount
        if t.type == 'DIVIDEND' and t.asset:
            sym = t.asset.symbol
            payers[sym] = payers.get(sym, 0.0) + amt

    sorted_years = sorted(list(available_years))
    yearly_values = [round(yearly_data.get(y, 0), 2) for y in sorted_years]
    sorted_payers = sorted(payers.items(), key=lambda item: item[1], reverse=True)
    top_payers_list = [{'symbol': k, 'amount': fmt_2(v)} for k, v in sorted_payers]

    return {
        'total_net': fmt_2(total_received_pln - total_tax_pln),
        'total_gross': fmt_2(total_received_pln),
        'total_tax': fmt_2(total_tax_pln),
        'top_payer': top_payers_list[0] if top_payers_list else None,
        'payers_list': top_payers_list,
        'years_labels': sorted_years,
        'years_data': yearly_values,
        'monthly_data': monthly_data,
    }