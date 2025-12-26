# core/services/calculator.py

from ..models import Transaction


class PortfolioCalculator:
    """
    Silnik obliczeniowy portfela.
    Przetwarza surowe transakcje i zwraca stan posiadania (ilość, koszt, zysk zrealizowany).
    """

    def __init__(self, transactions):
        self.transactions = transactions
        # Główne kontenery stanu
        self.holdings = {}  # { 'PKN.PL': { 'qty': 10, 'cost': 500, 'realized': 50, 'asset': Obj, 'trades': [] } }
        self.cash = 0.0
        self.total_invested = 0.0
        self.first_date = None

    def process(self):
        """
        Główna pętla przetwarzająca transakcje chronologicznie.
        """
        for t in self.transactions:
            if not self.first_date:
                self.first_date = t.date.date()

            # Konwersja na float dla bezpieczeństwa
            amt = float(t.amount)
            qty = float(t.quantity)

            # 1. Obsługa Gotówki (Cash Flow)
            if t.type == 'DEPOSIT':
                self.total_invested += amt
                self.cash += amt
            elif t.type == 'WITHDRAWAL':
                self.total_invested -= abs(amt)
                self.cash -= abs(amt)
            elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                # BUY ma ujemne amt (wydatek), SELL/DIV dodatnie (przychód)
                self.cash += amt

            # 2. Obsługa Aktywów (Assets Logic)
            if t.asset:
                sym = t.asset.symbol

                # Inicjalizacja wpisu dla aktywa, jeśli nie istnieje
                if sym not in self.holdings:
                    self.holdings[sym] = {
                        'qty': 0.0,
                        'cost': 0.0,  # Średni ważony koszt zakupu całej pozycji
                        'realized': 0.0,  # Zysk/Strata z zamkniętych pozycji
                        'asset': t.asset,  # Obiekt Asset (potrzebny do cen/walut)
                        'trades': []  # Historia transakcji dla tego aktywa (do wykresów/tabel)
                    }

                # Zapisujemy transakcję w historii aktywa (z wyliczoną ceną jednostkową)
                implied_price = (abs(amt) / qty) if qty > 0 else 0.0
                self.holdings[sym]['trades'].append({
                    'date': t.date,
                    'type': t.type,
                    'qty': qty,
                    'amount': amt,
                    'price': implied_price,
                    'currency': 'PLN'  # XTB raportuje amount w PLN
                })

                # Logika kupna/sprzedaży (Average Cost Basis)
                if t.type in ['OPEN BUY', 'BUY']:
                    self.holdings[sym]['qty'] += qty
                    self.holdings[sym]['cost'] += abs(amt)

                elif t.type in ['CLOSE SELL', 'SELL']:
                    current_qty = self.holdings[sym]['qty']
                    if current_qty > 0:
                        # Obliczamy proporcję sprzedanej części
                        ratio = qty / current_qty
                        if ratio > 1: ratio = 1  # Zabezpieczenie

                        # Zdejmujemy koszt proporcjonalnie
                        cost_removed = self.holdings[sym]['cost'] * ratio

                        self.holdings[sym]['cost'] -= cost_removed
                        self.holdings[sym]['qty'] -= qty

                        # Zysk zrealizowany = Przychód ze sprzedaży - Koszt sprzedanej części
                        # amt jest dodatnie przy sprzedaży
                        self.holdings[sym]['realized'] += (amt - cost_removed)

        return self

    # Helpery do pobierania wyników
    def get_holdings(self):
        return self.holdings

    def get_cash_balance(self):
        return self.cash, self.total_invested