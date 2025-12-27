from decimal import Decimal
from collections import defaultdict

class PortfolioCalculator:
    def __init__(self, transactions):
        self.transactions = transactions
        self.holdings = {}
        self.first_date = None
        # Używamy Decimal dla precyzji finansowej
        self.total_cash_operations = Decimal('0.00')

    def process(self):
        # Grupowanie transakcji po symbolu aktywa
        asset_groups = defaultdict(list)

        for t in self.transactions:
            if not self.first_date:
                self.first_date = t.date.date()

            # Konwersja na Decimal (bezpieczna matematyka)
            amt = Decimal(str(t.amount))
            qty = Decimal(str(t.quantity))

            if t.type in ['DEPOSIT', 'WITHDRAWAL']:
                self.total_cash_operations += amt

            elif t.type in ['BUY', 'SELL']:
                if t.asset:
                    asset_groups[t.asset.symbol].append({
                        'date': t.date,
                        'type': t.type,
                        'amount': amt,
                        'qty': qty,
                        'asset_obj': t.asset
                    })
                else:
                    self.total_cash_operations += amt

            elif t.type in ['DIVIDEND', 'TAX']:
                self.total_cash_operations += amt

        # Przetwarzanie każdego aktywa osobno
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

            # --- FIX: OBLICZANIE CENY JEDNOSTKOWEJ ---
            # Liczymy to tutaj raz, żeby portfolio.py mogło z tego korzystać
            if qty > 0:
                t['price'] = float(abs(amt) / qty)
            else:
                t['price'] = 0.0
            # -----------------------------------------

            # Obsługa korekt zysku (np. domknięcie pozycji)
            if qty == 0:
                realized_pln += amt
                continue

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
        net_deposits = float(self.total_cash_operations)
        trading_cash_flow = Decimal('0.00')
        for t in self.transactions:
            if t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                trading_cash_flow += Decimal(str(t.amount))
        current_cash = float(self.total_cash_operations + trading_cash_flow)
        return current_cash, net_deposits