# core/services/calculator.py

from decimal import Decimal
from collections import defaultdict


class PortfolioCalculator:
    def __init__(self, transactions, portfolio_currency="PLN", currency_rates=None):
        self.transactions = transactions
        self.portfolio_currency = portfolio_currency
        
        # Lazy import to avoid circular dependencies
        if currency_rates is None:
            try:
                from .market import get_current_currency_rates
                self.currency_rates = get_current_currency_rates()
            except ImportError:
                self.currency_rates = {}
        else:
            self.currency_rates = currency_rates

        # Pre-cache portfolio currencies to avoid N+1 queries during loop
        self.portfolio_currencies = {}
        if hasattr(self.transactions, 'select_related'):
            try:
                for p_id, p_curr in self.transactions.values_list('portfolio_id', 'portfolio__currency').distinct():
                    self.portfolio_currencies[p_id] = p_curr
            except Exception:
                pass

        self.holdings = {}
        self.first_date = None
        # To śledzi tylko WPŁATY/WYPŁATY netto od użytkownika (Twój kapitał)
        self.total_invested_net = Decimal('0.00')

    def _get_converted_amount(self, t):
        amt = Decimal(str(t.amount))
        
        tx_currency = self.portfolio_currencies.get(t.portfolio_id)
        if not tx_currency:
            if hasattr(t, 'portfolio') and t.portfolio and hasattr(t.portfolio, 'currency'):
                tx_currency = t.portfolio.currency
                self.portfolio_currencies[t.portfolio_id] = tx_currency
            else:
                return amt
                
        if tx_currency == self.portfolio_currency:
            return amt
            
        tx_to_pln = 1.0 if tx_currency == 'PLN' else self.currency_rates.get(tx_currency, 1.0)
        port_to_pln = 1.0 if self.portfolio_currency == 'PLN' else self.currency_rates.get(self.portfolio_currency, 1.0)
        
        if tx_currency == 'JPY': tx_to_pln = float(tx_to_pln) / 100.0
        if self.portfolio_currency == 'JPY': port_to_pln = float(port_to_pln) / 100.0
        
        multiplier = Decimal(str(tx_to_pln)) / Decimal(str(port_to_pln)) if port_to_pln else Decimal('1.00')
        return amt * multiplier

    def process(self):
        asset_groups = defaultdict(list)

        # Sortujemy transakcje chronologicznie, żeby "Podłoga Zero" działała poprawnie
        # Jeśli data jest ta sama, DEPOSIT (wpłata) ma pierwszeństwo przed innymi
        sorted_transactions = sorted(
            self.transactions,
            key=lambda x: (x.date, 0 if x.type == 'DEPOSIT' else 1)
        )

        for t in sorted_transactions:
            if not self.first_date:
                self.first_date = t.date.date()

            amt = self._get_converted_amount(t)
            qty = Decimal(str(t.quantity))

            # --- SEKCJA DEPOSIT (WPŁATY I "UJEMNE WPŁATY") ---
            if t.type == 'DEPOSIT':
                self.total_invested_net += amt

                # FIX: Jeśli "ujemna wpłata" (wypłata zysków przez XTB)
                # sprawiła, że kapitał spadł poniżej zera -> resetujemy do 0.
                if self.total_invested_net < 0:
                    self.total_invested_net = Decimal('0.00')

            # --- SEKCJA WITHDRAWAL (STANDARDOWE WYPŁATY) ---
            elif t.type == 'WITHDRAWAL':
                self.total_invested_net += amt

                # Jeśli wypłaciliśmy więcej niż wpłaciliśmy (wypłata zysków),
                # resetujemy zainwestowany kapitał do 0. Nie robimy "ujemnej dziury".
                if self.total_invested_net < 0:
                    self.total_invested_net = Decimal('0.00')

            # --- POZOSTAŁE ---
            elif t.type in ['BUY', 'SELL', 'CLOSE']:
                if t.asset:
                    asset_groups[t.asset.symbol].append({
                        'date': t.date,
                        'type': t.type,
                        'amount': amt,
                        'qty': qty,
                        'asset_obj': t.asset,
                        'position_id': t.position_id
                    })

        for symbol, trades in asset_groups.items():
            self._process_single_asset(symbol, trades)

        return self

    def _process_single_asset(self, symbol, trades):
        total_qty = Decimal('0.0000')
        total_cost = Decimal('0.00')
        realized_pln = Decimal('0.00')
        open_buys = []

        trades.sort(key=lambda x: x['date'])
        asset_obj = trades[0]['asset_obj']

        for t in trades:
            amt = t['amount']
            qty = t['qty']
            pos_id = t.get('position_id')

            # Obsługa typu CLOSE (Zysk bez zmiany ilości akcji)
            if t['type'] == 'CLOSE':
                realized_pln += amt
                continue

            if qty > 0:
                t['price'] = float(abs(amt) / qty)
            else:
                t['price'] = 0.0

            if t['type'] == 'BUY':
                total_qty += qty
                cost_of_trade = abs(amt)
                total_cost += cost_of_trade
                price_per_unit = cost_of_trade / qty
                open_buys.append({
                    'price': price_per_unit,
                    'qty': qty,
                    'position_id': pos_id
                })

            elif t['type'] == 'SELL':
                total_qty -= qty
                revenue = amt
                cost_basis_for_sale = Decimal('0.00')
                shares_to_sell = qty

                # 1. Match by Position ID first (if position_id is present)
                if pos_id:
                    matching_buys = [b for b in open_buys if b['position_id'] == pos_id]
                    for batch in matching_buys:
                        if shares_to_sell <= 0:
                            break
                        take_qty = min(batch['qty'], shares_to_sell)
                        cost_basis_for_sale += take_qty * batch['price']
                        shares_to_sell -= take_qty
                        batch['qty'] -= take_qty

                    # Filter out fully depleted batches
                    open_buys = [b for b in open_buys if b['qty'] > 0]

                # 2. Fallback: match any remaining shares to sell using standard FIFO
                if shares_to_sell > 0:
                    while shares_to_sell > 0 and open_buys:
                        batch = open_buys[0]
                        take_qty = min(batch['qty'], shares_to_sell)
                        cost_basis_for_sale += take_qty * batch['price']
                        shares_to_sell -= take_qty
                        batch['qty'] -= take_qty
                        if batch['qty'] <= 0:
                            open_buys.pop(0)

                total_cost -= cost_basis_for_sale
                trade_profit = revenue - cost_basis_for_sale
                realized_pln += trade_profit

        self.holdings[symbol] = {
            'qty': float(total_qty),
            'cost': float(total_cost),
            'realized': float(realized_pln),
            'asset': asset_obj,
            'trades': trades
        }

    def get_holdings(self):
        return self.holdings

    def get_cash_balance(self):
        # Gotówka to suma wszystkiego (tu ujemne wypłaty są OK, bo gotówki fizycznie ubywa)
        # Niezależnie od tego czy licznik "invested" się wyzerował, gotówka na koncie jest faktem.
        total_cash = Decimal('0.00')
        for t in self.transactions:
            total_cash += self._get_converted_amount(t)

        # Zwracamy: (Faktyczna Gotówka na koncie, Zainwestowane "Netto" z podłogą zero)
        return float(total_cash), float(self.total_invested_net)