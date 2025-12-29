# core/services/calculator.py

from decimal import Decimal
from collections import defaultdict


class PortfolioCalculator:
    def __init__(self, transactions):
        self.transactions = transactions
        self.holdings = {}
        self.first_date = None
        # To śledzi tylko WPŁATY/WYPŁATY netto od użytkownika (Twój kapitał)
        self.total_invested_net = Decimal('0.00')

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

            amt = Decimal(str(t.amount))
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
                        'asset_obj': t.asset
                    })

        for symbol, trades in asset_groups.items():
            self._process_single_asset(symbol, trades)

        return self

    def _process_single_asset(self, symbol, trades):
        total_qty = Decimal('0.0000')
        total_cost = Decimal('0.00')
        realized_pln = Decimal('0.00')
        buy_queue = []

        trades.sort(key=lambda x: x['date'])
        asset_obj = trades[0]['asset_obj']

        for t in trades:
            amt = t['amount']
            qty = t['qty']

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
                buy_queue.append([price_per_unit, qty])

            elif t['type'] == 'SELL':
                total_qty -= qty
                revenue = amt
                cost_basis_for_sale = Decimal('0.00')
                shares_to_sell = qty

                while shares_to_sell > 0 and buy_queue:
                    batch = buy_queue[0]
                    batch_price = batch[0]
                    batch_qty = batch[1]

                    if batch_qty <= shares_to_sell:
                        cost_basis_for_sale += batch_qty * batch_price
                        shares_to_sell -= batch_qty
                        buy_queue.pop(0)
                    else:
                        cost_basis_for_sale += shares_to_sell * batch_price
                        batch[1] -= shares_to_sell
                        shares_to_sell = 0

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
            total_cash += Decimal(str(t.amount))

        # Zwracamy: (Faktyczna Gotówka na koncie, Zainwestowane "Netto" z podłogą zero)
        return float(total_cash), float(self.total_invested_net)