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

    # FIX: Przekazujemy cały słownik 'rates', zamiast rozbitych floatów.
    # Wcześniej było: analyze_holdings(transactions, rates.get('EUR'), rates.get('USD')) -> To trafiało do start_date i powodowało błąd.
    stats = analyze_holdings(transactions, rates)

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
            # Zakładamy 19% podatku Belki zaoszczędzonego na polskich dywidendach
            dividend_tax_saved += round(amt * 0.19, 2)

    # Koszt uzyskania przychodu (tylko wpłaty netto)
    cost_basis = max(0.0, total_deposits - total_withdrawals)
    total_gain = current_value - cost_basis

    # Symulacja: Ile bym zapłacił podatku, gdybym wypłacił teraz?
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
    # --- PASS 1: Calculate Raw Income/Loss per Year (FIFO) ---
    years_db = {}
    buy_queue = {}  # {symbol: [{'qty': 10, 'price': 100}, ...]}

    # Sortujemy rosnąco, żeby zachować FIFO
    sorted_trans = sorted(list(transactions), key=lambda x: x.date)

    for t in sorted_trans:
        year = t.date.year
        if year not in years_db:
            years_db[year] = {
                'revenue': 0.0, 'cost': 0.0, 'income': 0.0,
                'div_gross': 0.0, 'div_tax_paid': 0.0,
                'loss_deducted': 0.0
            }

        amt = float(t.amount)
        qty = float(t.quantity)
        sym = t.asset.symbol if t.asset else 'CASH'

        if t.type == 'DIVIDEND':
            years_db[year]['div_gross'] += amt
        elif t.type == 'TAX':
            years_db[year]['div_tax_paid'] += abs(amt)
        elif t.type == 'CLOSE':
            years_db[year]['income'] += amt
        elif t.type == 'BUY':
            if sym not in buy_queue: buy_queue[sym] = []
            price_per_unit = abs(amt) / qty if qty > 0 else 0
            buy_queue[sym].append({'qty': qty, 'price': price_per_unit})
        elif t.type == 'SELL':
            revenue = amt
            cost_of_sold = 0.0
            shares_needed = qty
            if sym in buy_queue:
                while shares_needed > 0 and buy_queue[sym]:
                    batch = buy_queue[sym][0]
                    if batch['qty'] > shares_needed:
                        cost_of_sold += shares_needed * batch['price']
                        batch['qty'] -= shares_needed
                        shares_needed = 0
                    else:
                        cost_of_sold += batch['qty'] * batch['price']
                        shares_needed -= batch['qty']
                        buy_queue[sym].pop(0)

            years_db[year]['revenue'] += revenue
            years_db[year]['cost'] += cost_of_sold
            years_db[year]['income'] += (revenue - cost_of_sold)

    # --- PASS 2: Loss Carryforward Logic (AGRESYWNE ODLICZANIE) ---
    # Zasada: Stratę można odliczyć w ciągu 5 kolejnych lat.
    # Limit roczny: 50% STRATY PIERWOTNEJ (a nie pozostałej).

    sorted_years = sorted(years_db.keys())

    # Słownik dostępnych strat: {year: remaining_amount}
    available_losses = {}
    # Słownik strat pierwotnych (do limitu 50%): {year: original_amount}
    original_losses = {}

    for y in sorted_years:
        raw_income = years_db[y]['income']

        if raw_income < 0:
            # Rejestrujemy nową stratę
            loss_val = abs(raw_income)
            available_losses[y] = loss_val
            original_losses[y] = loss_val

        elif raw_income > 0:
            # Mamy zysk - szukamy strat z 5 poprzednich lat
            deduction_limit = raw_income  # Tyle potrzebujemy odliczyć, żeby wyzerować podatek
            total_deducted_now = 0.0

            # Sprawdzamy lata wstecz (y-5 do y-1)
            for past_year in range(y - 5, y):
                if past_year in available_losses and available_losses[past_year] > 0:

                    # LOGIKA AGRESYWNA:
                    # Limit to 50% straty PIERWOTNEJ
                    max_limit_for_year = original_losses[past_year] * 0.5

                    # Ale nie możemy wziąć więcej, niż fizycznie zostało w worku
                    actual_available = available_losses[past_year]

                    # Ile bierzemy? Minimum z:
                    # 1. Limitu ustawowego (50% pierwotnej)
                    # 2. Tego co zostało (żeby nie zejść poniżej zera)
                    # 3. Tego co potrzebujemy (żeby nie zrobić sztucznej straty w roku bieżącym)
                    to_take = min(max_limit_for_year, actual_available, deduction_limit)

                    if to_take > 0:
                        available_losses[past_year] -= to_take
                        total_deducted_now += to_take
                        deduction_limit -= to_take

                    if deduction_limit <= 0:
                        break

            years_db[y]['loss_deducted'] = total_deducted_now

    # --- PASS 3: Final Report Generation ---
    report_list = []
    for y in sorted(years_db.keys(), reverse=True):
        d = years_db[y]

        tax_base = max(0.0, d['income'] - d['loss_deducted'])

        stock_tax = round(tax_base * 0.19, 2)
        div_tax_total_due = round(d['div_gross'] * 0.19, 2)
        div_tax_surcharge = max(0.0, div_tax_total_due - d['div_tax_paid'])

        report_list.append({
            'year': y,
            'stock_result': fmt_2(d['income']),
            'loss_deducted': fmt_2(d['loss_deducted']),
            'tax_base': fmt_2(tax_base),
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