# core/services/taxes.py

from .selectors import get_transactions
from .analytics import analyze_holdings
from .market import get_current_currency_rates
from .config import fmt_2


def get_taxes_context(user, portfolio_id=None):
    transactions = get_transactions(user, portfolio_id)
    if not transactions.exists():
        return {'error': 'No transactions found.'}

    portfolio = transactions.first().portfolio
    portfolio_type = portfolio.portfolio_type

    rates = get_current_currency_rates()
    # Nowy analytics zwraca floaty w total_value, więc to jest bezpieczne
    stats = analyze_holdings(transactions, rates.get('EUR', 4.30), rates.get('USD', 4.00))
    current_value = stats['total_value']

    if portfolio_type in ['IKE', 'IKZE']:
        return _calculate_ike_tax_shield(transactions, current_value)
    else:
        return _calculate_standard_tax_report(transactions)


def _calculate_ike_tax_shield(transactions, current_value):
    total_deposits = 0.0
    total_withdrawals = 0.0
    dividend_tax_saved = 0.0

    for t in transactions:
        amt = float(t.amount)
        if t.type == 'DEPOSIT':
            total_deposits += amt
        elif t.type == 'WITHDRAWAL':
            total_withdrawals += abs(amt)
        elif t.type == 'DIVIDEND' and t.asset and t.asset.currency == 'PLN':
            # Symulacja: w IKE nie płacisz Belki od polskich dywidend
            dividend_tax_saved += round(amt * 0.19, 2)

    cost_basis = max(0.0, total_deposits - total_withdrawals)
    total_gain = current_value - cost_basis

    # --- SYMULACJA ZWROTU (Gdybyśmy zamknęli IKE dzisiaj) ---
    exit_tax = 0.0
    if total_gain > 0:
        exit_tax = round(total_gain * 0.19, 2)

    net_after_exit = current_value - exit_tax
    deferred_tax_value = max(0.0, round(total_gain * 0.19, 2))

    return {
        'is_ike': True,
        'portfolio_type': 'IKE/IKZE',

        'current_value': fmt_2(current_value),
        'total_deposits': fmt_2(cost_basis),
        'total_gain': fmt_2(total_gain),
        'total_gain_raw': total_gain,

        'exit_tax_amount': fmt_2(exit_tax),
        'net_after_exit': fmt_2(net_after_exit),

        'tax_saved_dividends': fmt_2(dividend_tax_saved),
        'deferred_tax': fmt_2(deferred_tax_value),

        'js_current_value': round(current_value, 2),
        'js_cost_basis': round(cost_basis, 2)
    }


def _calculate_standard_tax_report(transactions):
    years_db = {}
    buy_queue = {}  # FIFO Queue: {symbol: [{'qty': 10, 'price': 100}, ...]}

    for t in transactions:
        year = t.date.year
        if year not in years_db:
            years_db[year] = {
                'revenue': 0.0,
                'cost': 0.0,
                'income': 0.0,
                'div_gross': 0.0,
                'div_tax_paid': 0.0
            }

        amt = float(t.amount)
        qty = float(t.quantity)
        sym = t.asset.symbol if t.asset else 'CASH'

        # --- 1. DYWIDENDY I PODATKI (WTH) ---
        if t.type == 'DIVIDEND':
            years_db[year]['div_gross'] += amt
        elif t.type == 'TAX':
            years_db[year]['div_tax_paid'] += abs(amt)

        # --- 2. ZAMKNIĘCIE BEZ SPRZEDAŻY (np. SWAP, Cash adjustment) ---
        # TO NAPRAWIA TWOJE 16 ZŁ ZYSKU
        elif t.type == 'CLOSE':
            # Amount w CLOSE to zazwyczaj czysty zysk/strata
            years_db[year]['income'] += amt
            # Jeśli amt > 0 to zysk, zwiększa podstawę opodatkowania.

        # --- 3. KUPNO (Dodaj do kolejki) ---
        elif t.type == 'BUY':
            if sym not in buy_queue: buy_queue[sym] = []
            price_per_unit = abs(amt) / qty if qty > 0 else 0
            buy_queue[sym].append({'qty': qty, 'price': price_per_unit})

        # --- 4. SPRZEDAŻ (Zdejmij z kolejki FIFO) ---
        elif t.type == 'SELL':
            revenue = amt
            cost_of_sold = 0.0
            shares_needed = qty

            if sym in buy_queue:
                while shares_needed > 0 and buy_queue[sym]:
                    batch = buy_queue[sym][0]

                    if batch['qty'] > shares_needed:
                        # Zużywamy część partii
                        cost_of_sold += shares_needed * batch['price']
                        batch['qty'] -= shares_needed
                        shares_needed = 0
                    else:
                        # Zużywamy całą partię
                        cost_of_sold += batch['qty'] * batch['price']
                        shares_needed -= batch['qty']
                        buy_queue[sym].pop(0)

            # Jeśli brakło w kolejce (błąd danych?), koszt jest 0 dla reszty

            years_db[year]['revenue'] += revenue
            years_db[year]['cost'] += cost_of_sold
            years_db[year]['income'] += (revenue - cost_of_sold)

    report_list = []
    for y in sorted(years_db.keys(), reverse=True):
        d = years_db[y]

        # Podatek od akcji (19% od dochodu, nie może być ujemny)
        # Zaokrąglamy zgodnie z zasadami podatkowymi (do pełnych groszy matematycznie)
        stock_tax_base = max(0.0, d['income'])
        stock_tax = round(stock_tax_base * 0.19, 2)

        # Podatek od dywidend (19% ryczałt - zapłacony podatek u źródła)
        # Polska: 19% od brutto minus to co pobrał broker zagraniczny
        div_tax_total_due = round(d['div_gross'] * 0.19, 2)
        div_tax_surcharge = max(0.0, div_tax_total_due - d['div_tax_paid'])

        report_list.append({
            'year': y,
            'stock_result': fmt_2(d['income']),
            'stock_tax': fmt_2(stock_tax),
            'div_gross': fmt_2(d['div_gross']),
            'div_tax_paid': fmt_2(d['div_tax_paid']),
            'div_tax_topup': fmt_2(div_tax_surcharge),
            'total_tax_due': fmt_2(stock_tax + div_tax_surcharge)
        })

    return {
        'is_ike': False,
        'portfolio_type': 'STANDARD',
        'report': report_list
    }