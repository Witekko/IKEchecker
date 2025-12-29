from datetime import date, timedelta, datetime

try:
    from pyxirr import xirr
except ImportError:
    xirr = None


class PerformanceCalculator:
    def __init__(self, transactions):
        self.transactions = sorted(list(transactions), key=lambda x: x.date)

    # --- ZMIANA: Dodajemy argument timeline_data ---
    def calculate_metrics(self, timeline_data=None, start_date=None, end_date=None, current_total_value=None):
        if not end_date: end_date = date.today()

        # 1. Ustalenie daty startowej
        first_trans_date = self.transactions[0].date.date() if self.transactions else date.today()
        if not start_date: start_date = first_trans_date

        transactions_in_period = [t for t in self.transactions if start_date <= t.date.date() <= end_date]

        # 2. START VALUE (Kluczowa Poprawka)
        # Zamiast brać "Invested" (Księgową), szukamy "Market Value" (Rynkową) w Timeline
        start_val = 0.0

        # Jeśli startujemy przed pierwszą transakcją -> 0
        if start_date <= first_trans_date:
            start_val = 0.0
            effective_start_date = first_trans_date
        else:
            effective_start_date = start_date
            # Szukamy wartości w timeline
            start_val = self._find_market_value_in_timeline(timeline_data, start_date)

            # Fallback: Jeśli timeline nie ma danych (błąd), bierzemy księgową
            if start_val == 0.0:
                start_val = self._get_accounting_value_at(start_date - timedelta(days=1))

        # 3. END VALUE
        if end_date == date.today() and current_total_value is not None:
            end_val = float(current_total_value)
        else:
            # Tu też przydałoby się wziąć z timeline dla dat historycznych,
            # ale dla Dashboardu "Dziś" current_total_value wystarczy.
            end_val = self._get_accounting_value_at(end_date)  # Fallback (mało precyzyjny dla przeszłości)

        # 4. Cash Flow w okresie
        net_deposits = sum(float(t.amount) for t in transactions_in_period if t.type in ['DEPOSIT', 'WITHDRAWAL'])

        # --- A. PROFIT ---
        # Profit = (Wartość Końcowa) - (Wartość Początkowa RYNKOWA) - (Wpłaty w trakcie)
        profit_amount = end_val - start_val - net_deposits

        # --- B. SIMPLE RETURN ---
        invested_base = start_val + max(0, net_deposits)
        simple_return = (profit_amount / invested_base * 100) if invested_base > 1.0 else 0.0

        # --- C. XIRR ---
        xirr_val = 0.0
        if xirr:
            # Do XIRR musimy użyć wartości rynkowej na start jako "Wydatku początkowego"
            raw_xirr = self._calculate_xirr_robust(start_val, end_val, effective_start_date, end_date,
                                                   transactions_in_period)

            days_in_period = (end_date - effective_start_date).days
            if 0 < days_in_period < 365 and raw_xirr != 0.0:
                try:
                    factor = 1 + (raw_xirr / 100.0)
                    if factor > 0:
                        xirr_val = ((factor ** (days_in_period / 365.0)) - 1) * 100
                    else:
                        xirr_val = simple_return
                except:
                    xirr_val = simple_return
            else:
                xirr_val = raw_xirr

        return {
            'profit': profit_amount,
            'simple_return': simple_return,
            'xirr': xirr_val
        }

    def _find_market_value_in_timeline(self, timeline, target_date):
        """Pomocnicza: Szuka wartości portfela w danych wykresu dla konkretnej daty."""
        if not timeline: return 0.0

        dates_str = timeline.get('dates', [])
        vals = timeline.get('val_user', [])

        # Szukamy indeksu, gdzie data <= target_date (najbliższa przeszła)
        # Timeline jest posortowany rosnąco.
        # Idziemy od końca, żeby znaleźć "stan na koniec dnia" danej daty lub najbliższej poprzedniej.
        target_dt = datetime.combine(target_date, datetime.min.time())

        # Szybkie wyszukiwanie (iteracja odwrócona)
        for i in range(len(dates_str) - 1, -1, -1):
            try:
                d_obj = datetime.strptime(dates_str[i], "%Y-%m-%d")
                # Szukamy wartości z dnia START-1 (czyli zamknięcie dnia poprzedniego)
                # Ale start_date w filtrze to "od dzisiaj", więc bierzemy wartość z tego dnia rano?
                # Standard: Start Value to wartość na zamknięcie dnia POPRZEDZAJĄCEGO okres.
                if d_obj.date() < target_date:
                    return vals[i]
            except:
                pass

        return 0.0

    # ... (calculate_twr, _calculate_xirr_robust, _get_accounting_value_at bez zmian) ...
    def calculate_twr(self, timeline_data, start_date_filter=None):
        val_user = timeline_data.get('val_user', [])
        dates_str = timeline_data.get('dates', [])
        if not val_user or len(val_user) < 2: return 0.0

        timeline_dates = []
        for d_str in dates_str:
            try:
                timeline_dates.append(datetime.strptime(d_str, "%Y-%m-%d").date())
            except:
                timeline_dates.append(date.today())

        daily_flows = {}
        for t in self.transactions:
            if t.type in ['DEPOSIT', 'WITHDRAWAL']:
                d_str = t.date.strftime("%Y-%m-%d")
                daily_flows[d_str] = daily_flows.get(d_str, 0.0) + float(t.amount)

        twr_accumulated = 1.0
        start_idx = 0
        if start_date_filter:
            for i, d in enumerate(timeline_dates):
                if d >= start_date_filter:
                    start_idx = i
                    break

        if start_idx >= len(val_user) - 1: return 0.0
        prev_val = val_user[start_idx]

        for i in range(start_idx + 1, len(val_user)):
            curr_val = val_user[i]
            date_str = dates_str[i]
            real_cash_flow = daily_flows.get(date_str, 0.0)
            start_of_day = prev_val + real_cash_flow

            if abs(start_of_day) > 0.01:
                daily_ret = (curr_val - start_of_day) / start_of_day
                twr_accumulated *= (1 + daily_ret)

            prev_val = curr_val

        return (twr_accumulated - 1) * 100

    def _calculate_xirr_robust(self, start_val, end_val, start_date, end_date, transactions):
        flows = {}
        # start_val jest teraz RYNKOWE, więc jest to "koszt alternatywny" (gdybyśmy sprzedali)
        if abs(start_val) > 0.01: flows[start_date] = flows.get(start_date, 0.0) - float(start_val)
        for t in transactions:
            d, amt = t.date.date(), float(t.amount)
            if t.type == 'DEPOSIT':
                flows[d] = flows.get(d, 0.0) - amt
            elif t.type == 'WITHDRAWAL':
                flows[d] = flows.get(d, 0.0) + abs(amt)
        if abs(end_val) > 0.01: flows[end_date] = flows.get(end_date, 0.0) + float(end_val)

        dates, amounts = list(flows.keys()), list(flows.values())
        if not amounts or not (any(a > 0 for a in amounts) and any(a < 0 for a in amounts)): return 0.0
        try:
            res = xirr(dates, amounts)
            return (res * 100) if res else 0.0
        except:
            return 0.0

    def _get_accounting_value_at(self, target_date):
        val = 0.0
        for t in self.transactions:
            if t.date.date() > target_date: break
            val += float(t.amount)
        return max(0.0, val)

    def _empty_result(self, s, e):
        return {'profit': 0.0, 'simple_return': 0.0, 'xirr': 0.0}