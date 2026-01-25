# core/management/commands/reset_demo.py

from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from decimal import Decimal
from core.models import Portfolio, Transaction, Asset

class Command(BaseCommand):
    help = 'Laduje dane 1:1 z Twojego JSON (bez NVIDIA)'

    def handle(self, *args, **kwargs):
        # ========================================================
        # 1. FIX: Definicje dla JSON (To naprawia błąd "null")
        # ========================================================
        null = None
        false = False
        true = True

        # 2. User Demo
        username = 'demo_user'
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password('demo123')
            user.save()

        # 3. Wyczyszczenie starego portfela demo
        Portfolio.objects.filter(user=user).delete()

        # 4. Nowy Portfel
        portfolio = Portfolio.objects.create(
            user=user,
            name="IKE Demo (Real Data 1:1)",
            portfolio_type='IKE',
            currency='PLN'
        )

        self.stdout.write("--- IMPORT DANYCH 1:1 (START) ---")

        # =======================================================
        # DANE SUROWE (Twoje dane 1:1)
        # =======================================================
        RAW_DATA = [
            # --- AKTYWA ---
            {"model": "core.asset", "pk": 1, "fields": {"symbol": "CDR.PL", "yahoo_ticker": "CDR.WA", "currency": "PLN", "name": "CD Projekt", "isin": null, "asset_type": "STOCK", "sector": "GAMING"}},
            {"model": "core.asset", "pk": 2, "fields": {"symbol": "PKN.PL", "yahoo_ticker": "PKN.WA", "currency": "PLN", "name": "Orlen", "isin": null, "asset_type": "STOCK", "sector": "ENERGY"}},
            {"model": "core.asset", "pk": 3, "fields": {"symbol": "IS3N.DE", "yahoo_ticker": "IS3N.DE", "currency": "EUR", "name": "iShares MSCI EM", "isin": null, "asset_type": "ETF", "sector": "OTHER"}},
            {"model": "core.asset", "pk": 4, "fields": {"symbol": "PZU.PL", "yahoo_ticker": "PZU.WA", "currency": "PLN", "name": "PZU", "isin": null, "asset_type": "STOCK", "sector": "HEALTHCARE"}},
            {"model": "core.asset", "pk": 5, "fields": {"symbol": "SXRV.DE", "yahoo_ticker": "SXRV.DE", "currency": "EUR", "name": "iShares NASDAQ 100", "isin": null, "asset_type": "ETF", "sector": "OTHER"}},
            {"model": "core.asset", "pk": 6, "fields": {"symbol": "XTB.PL", "yahoo_ticker": "XTB.WA", "currency": "PLN", "name": "XTB", "isin": null, "asset_type": "STOCK", "sector": "FINANCE"}},
            {"model": "core.asset", "pk": 7, "fields": {"symbol": "SNT.PL", "yahoo_ticker": "SNT.WA", "currency": "PLN", "name": "Synektik", "isin": null, "asset_type": "STOCK", "sector": "HEALTHCARE"}},
            {"model": "core.asset", "pk": 8, "fields": {"symbol": "DIG.PL", "yahoo_ticker": "DIG.WA", "currency": "PLN", "name": "Digital Network", "isin": null, "asset_type": "STOCK", "sector": "CONSUMER"}},
            {"model": "core.asset", "pk": 9, "fields": {"symbol": "CBF.PL", "yahoo_ticker": "CBF.WA", "currency": "PLN", "name": "Cyber_Folks", "isin": null, "asset_type": "STOCK", "sector": "TECHNOLOGY"}},
            {"model": "core.asset", "pk": 10, "fields": {"symbol": "6AQQ.DE", "yahoo_ticker": "6AQQ.DE", "currency": "EUR", "name": "AIS-Amundi NASDAQ-100", "isin": null, "asset_type": "ETF", "sector": "OTHER"}},
            {"model": "core.asset", "pk": 11, "fields": {"symbol": "ACWD.UK", "yahoo_ticker": "ACWD.L", "currency": "USD", "name": "SSGA SPDR EUROPE", "isin": null, "asset_type": "ETF", "sector": "OTHER"}},
            {"model": "core.asset", "pk": 12, "fields": {"symbol": "PKN.WA", "yahoo_ticker": "PKN.WA", "currency": "PLN", "name": "Orlen S.A.", "isin": null, "asset_type": "STOCK", "sector": "ENERGY"}},
            {"model": "core.asset", "pk": 13, "fields": {"symbol": "MBR.PL", "yahoo_ticker": "MBR.WA", "currency": "PLN", "name": "MOBRUK", "isin": null, "asset_type": "STOCK", "sector": "ENERGY"}},
            {"model": "core.asset", "pk": 14, "fields": {"symbol": "PAS.PL", "yahoo_ticker": "PAS.WA", "currency": "PLN", "name": "Passus S.A.", "isin": null, "asset_type": "STOCK", "sector": "TECHNOLOGY"}},
            # PK 15 (NVDA) - POMINIĘTE
            {"model": "core.asset", "pk": 16, "fields": {"symbol": "SXR8.DE", "yahoo_ticker": "SXR8.DE", "currency": "EUR", "name": "iShares Core S&P 500", "isin": null, "asset_type": "ETF", "sector": "OTHER"}},
            {"model": "core.asset", "pk": 17, "fields": {"symbol": "PLTR", "yahoo_ticker": "PLTR", "currency": "USD", "name": "Palantir Technologies", "isin": null, "asset_type": "STOCK", "sector": "TECHNOLOGY"}},
            {"model": "core.asset", "pk": 18, "fields": {"symbol": "CASH", "yahoo_ticker": "CASH", "currency": "PLN", "name": "Gotówka", "isin": null, "asset_type": "OTHER", "sector": "OTHER"}},

            # --- TRANSAKCJE ---
            {"model": "core.transaction", "pk": 211, "fields": {"asset": 18, "date": "2025-09-02T22:40:54.484Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 212, "fields": {"asset": 18, "date": "2025-09-02T22:41:03.413Z", "type": "DEPOSIT", "amount": "-500.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 213, "fields": {"asset": 18, "date": "2025-09-10T13:10:02.307Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 214, "fields": {"asset": 10, "date": "2025-09-10T13:14:55.169Z", "type": "BUY", "amount": "-379.93", "quantity": "0.3799", "price": "233.35", "comment": "OPEN BUY 0.3799 @ 233.35"}},
            {"model": "core.transaction", "pk": 215, "fields": {"asset": 11, "date": "2025-09-10T13:16:03.580Z", "type": "BUY", "amount": "-117.57", "quantity": "0.1174", "price": "273.48", "comment": "OPEN BUY 0.1174 @ 273.4800"}},
            {"model": "core.transaction", "pk": 216, "fields": {"asset": 18, "date": "2025-09-24T12:22:48.846Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 217, "fields": {"asset": 18, "date": "2025-09-24T12:23:11.816Z", "type": "DEPOSIT", "amount": "-502.50", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 218, "fields": {"asset": 18, "date": "2025-10-08T13:13:05.838Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 219, "fields": {"asset": 18, "date": "2025-10-08T13:13:53.706Z", "type": "DEPOSIT", "amount": "-500.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 220, "fields": {"asset": 10, "date": "2025-10-08T13:38:19.639Z", "type": "CLOSE", "amount": "12.16", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 221, "fields": {"asset": 10, "date": "2025-10-08T13:38:19.639Z", "type": "SELL", "amount": "367.73", "quantity": "0.3677", "price": "244.35", "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 222, "fields": {"asset": 18, "date": "2025-10-08T13:41:20.292Z", "type": "DEPOSIT", "amount": "-379.89", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 223, "fields": {"asset": 11, "date": "2025-10-09T09:01:26.065Z", "type": "CLOSE", "amount": "3.48", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 224, "fields": {"asset": 11, "date": "2025-10-09T09:01:26.065Z", "type": "SELL", "amount": "117.57", "quantity": "0.1174", "price": "282.82", "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 225, "fields": {"asset": 10, "date": "2025-10-09T09:04:22.500Z", "type": "CLOSE", "amount": "0.58", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 226, "fields": {"asset": 10, "date": "2025-10-09T09:04:22.500Z", "type": "SELL", "amount": "12.20", "quantity": "0.0122", "price": "247.35", "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 227, "fields": {"asset": 18, "date": "2025-10-09T09:04:45.164Z", "type": "DEPOSIT", "amount": "-133.83", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 228, "fields": {"asset": 18, "date": "2025-11-07T15:31:29.507Z", "type": "DEPOSIT", "amount": "350.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 229, "fields": {"asset": 18, "date": "2025-11-07T15:32:15.743Z", "type": "DEPOSIT", "amount": "-350.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 230, "fields": {"asset": 18, "date": "2025-11-10T12:23:35.135Z", "type": "DEPOSIT", "amount": "-150.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 231, "fields": {"asset": 18, "date": "2025-11-10T12:23:09.674Z", "type": "DEPOSIT", "amount": "150.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 232, "fields": {"asset": 18, "date": "2025-12-09T14:35:45.438Z", "type": "DEPOSIT", "amount": "-500.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 233, "fields": {"asset": 18, "date": "2025-12-09T14:34:47.863Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 234, "fields": {"asset": 18, "date": "2025-12-11T14:20:14.769Z", "type": "DEPOSIT", "amount": "-415.00", "quantity": "0.0000", "price": null, "comment": "Transfer out"}},
            {"model": "core.transaction", "pk": 235, "fields": {"asset": 18, "date": "2025-12-11T14:20:03.053Z", "type": "DEPOSIT", "amount": "415.00", "quantity": "0.0000", "price": null, "comment": "Adyen BLIK deposit"}},
            {"model": "core.transaction", "pk": 397, "fields": {"asset": 18, "date": "2025-09-02T22:41:03.422Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 398, "fields": {"asset": 1, "date": "2025-09-03T09:00:00.969Z", "type": "BUY", "amount": "-100.43", "quantity": "0.4006", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 399, "fields": {"asset": 2, "date": "2025-09-03T09:00:00.958Z", "type": "BUY", "amount": "-19.14", "quantity": "0.2454", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 400, "fields": {"asset": 3, "date": "2025-09-03T09:04:20.433Z", "type": "BUY", "amount": "-81.57", "quantity": "0.5475", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 401, "fields": {"asset": 3, "date": "2025-09-03T09:04:22.728Z", "type": "BUY", "amount": "-299.79", "quantity": "2.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 402, "fields": {"asset": 18, "date": "2025-09-24T12:23:11.825Z", "type": "DEPOSIT", "amount": "502.50", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 403, "fields": {"asset": 4, "date": "2025-09-24T12:24:17.126Z", "type": "BUY", "amount": "-39.05", "quantity": "0.6905", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 404, "fields": {"asset": 4, "date": "2025-09-24T12:24:17.169Z", "type": "BUY", "amount": "-452.48", "quantity": "8.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 405, "fields": {"asset": 18, "date": "2025-10-03T14:48:49.806Z", "type": "OTHER", "amount": "0.01", "quantity": "0.0000", "price": null, "comment": "Free-funds Interest"}},
            {"model": "core.transaction", "pk": 406, "fields": {"asset": 18, "date": "2025-10-08T13:13:53.718Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 407, "fields": {"asset": 2, "date": "2025-10-08T13:17:52.978Z", "type": "BUY", "amount": "-49.96", "quantity": "0.5709", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 408, "fields": {"asset": 2, "date": "2025-10-08T13:17:53.020Z", "type": "BUY", "amount": "-350.04", "quantity": "4.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 409, "fields": {"asset": 5, "date": "2025-10-08T13:18:55.783Z", "type": "BUY", "amount": "-107.47", "quantity": "0.0205", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 410, "fields": {"asset": 5, "date": "2025-10-08T13:41:54.179Z", "type": "BUY", "amount": "-374.63", "quantity": "0.0715", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 411, "fields": {"asset": 18, "date": "2025-10-08T13:41:20.326Z", "type": "DEPOSIT", "amount": "379.89", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 412, "fields": {"asset": 18, "date": "2025-10-09T09:04:45.174Z", "type": "DEPOSIT", "amount": "133.83", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 413, "fields": {"asset": 6, "date": "2025-10-09T09:05:38.161Z", "type": "BUY", "amount": "-135.92", "quantity": "2.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 414, "fields": {"asset": 18, "date": "2025-11-06T12:34:50.469Z", "type": "OTHER", "amount": "0.02", "quantity": "0.0000", "price": null, "comment": "Free-funds Interest"}},
            {"model": "core.transaction", "pk": 415, "fields": {"asset": 18, "date": "2025-11-07T15:32:15.752Z", "type": "DEPOSIT", "amount": "350.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 416, "fields": {"asset": 7, "date": "2025-11-07T15:32:40.492Z", "type": "BUY", "amount": "-264.20", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 417, "fields": {"asset": 5, "date": "2025-11-07T15:33:10.898Z", "type": "BUY", "amount": "-89.22", "quantity": "0.0169", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 418, "fields": {"asset": 18, "date": "2025-11-10T12:23:35.144Z", "type": "DEPOSIT", "amount": "150.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 419, "fields": {"asset": 7, "date": "2025-11-10T12:24:25.581Z", "type": "BUY", "amount": "-149.29", "quantity": "0.5621", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 420, "fields": {"asset": 18, "date": "2025-12-04T15:00:17.068Z", "type": "OTHER", "amount": "0.01", "quantity": "0.0000", "price": null, "comment": "Free-funds Interest"}},
            {"model": "core.transaction", "pk": 421, "fields": {"asset": 18, "date": "2025-12-09T14:35:45.446Z", "type": "DEPOSIT", "amount": "500.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 422, "fields": {"asset": 7, "date": "2025-12-09T14:37:36.132Z", "type": "BUY", "amount": "-100.48", "quantity": "0.3659", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 423, "fields": {"asset": 8, "date": "2025-12-09T14:36:36.601Z", "type": "BUY", "amount": "-117.19", "quantity": "0.8288", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 424, "fields": {"asset": 8, "date": "2025-12-09T14:36:36.655Z", "type": "BUY", "amount": "-141.40", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 425, "fields": {"asset": 8, "date": "2025-12-09T14:36:36.660Z", "type": "BUY", "amount": "-141.80", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 426, "fields": {"asset": 18, "date": "2025-12-11T14:20:14.777Z", "type": "DEPOSIT", "amount": "415.00", "quantity": "0.0000", "price": null, "comment": "Transfer in"}},
            {"model": "core.transaction", "pk": 427, "fields": {"asset": 9, "date": "2025-12-11T14:21:21.319Z", "type": "BUY", "amount": "-200.87", "quantity": "0.9751", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 428, "fields": {"asset": 9, "date": "2025-12-11T14:21:21.337Z", "type": "BUY", "amount": "-206.00", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 429, "fields": {"asset": 4, "date": "2025-12-19T09:17:49.770Z", "type": "CLOSE", "amount": "7.28", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 430, "fields": {"asset": 4, "date": "2025-12-19T09:17:49.770Z", "type": "SELL", "amount": "39.05", "quantity": "0.6905", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 431, "fields": {"asset": 4, "date": "2025-12-19T09:17:49.806Z", "type": "CLOSE", "amount": "84.32", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 432, "fields": {"asset": 4, "date": "2025-12-19T09:17:49.806Z", "type": "SELL", "amount": "452.48", "quantity": "8.0000", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 433, "fields": {"asset": 7, "date": "2025-12-19T09:20:47.821Z", "type": "BUY", "amount": "-256.60", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 434, "fields": {"asset": 9, "date": "2025-12-19T09:21:47.828Z", "type": "BUY", "amount": "-117.97", "quantity": "0.6087", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 435, "fields": {"asset": 7, "date": "2025-12-19T09:20:47.804Z", "type": "BUY", "amount": "-18.73", "quantity": "0.0730", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 436, "fields": {"asset": 9, "date": "2025-12-19T09:21:47.862Z", "type": "BUY", "amount": "-193.80", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 437, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.269Z", "type": "CLOSE", "amount": "50.68", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 438, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.269Z", "type": "SELL", "amount": "350.04", "quantity": "4.0000", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 439, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.205Z", "type": "CLOSE", "amount": "5.44", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 440, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.205Z", "type": "SELL", "amount": "19.14", "quantity": "0.2454", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 441, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.206Z", "type": "CLOSE", "amount": "7.23", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 442, "fields": {"asset": 2, "date": "2026-01-05T11:41:01.206Z", "type": "SELL", "amount": "49.96", "quantity": "0.5709", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 443, "fields": {"asset": 3, "date": "2026-01-05T12:08:16.229Z", "type": "BUY", "amount": "-147.83", "quantity": "0.8788", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 444, "fields": {"asset": 13, "date": "2026-01-05T12:07:39.361Z", "type": "BUY", "amount": "-338.00", "quantity": "1.0000", "price": null, "comment": "OPEN BUY"}},
            {"model": "core.transaction", "pk": 445, "fields": {"asset": 18, "date": "2026-01-07T14:08:39.230Z", "type": "OTHER", "amount": "0.01", "quantity": "0.0000", "price": null, "comment": "Free-funds Interest"}},
            {"model": "core.transaction", "pk": 446, "fields": {"asset": 1, "date": "2026-01-13T11:41:41.890Z", "type": "CLOSE", "amount": "0.32", "quantity": "0.0000", "price": null, "comment": "Profit of position"}},
            {"model": "core.transaction", "pk": 447, "fields": {"asset": 1, "date": "2026-01-13T11:41:41.890Z", "type": "SELL", "amount": "100.43", "quantity": "0.4006", "price": null, "comment": "CLOSE BUY"}},
            {"model": "core.transaction", "pk": 448, "fields": {"asset": 14, "date": "2026-01-13T11:57:46.757Z", "type": "BUY", "amount": "-101.70", "quantity": "0.7478", "price": null, "comment": "OPEN BUY"}},
        ]

        # 4. Import Aktywow (Z mapowaniem PK)
        pk_to_real_asset = {}
        for item in RAW_DATA:
            if item['model'] == 'core.asset':
                # Pomin PK 15 (NVDA)
                if item['pk'] == 15:
                    continue

                f = item['fields']
                asset, _ = Asset.objects.get_or_create(
                    symbol=f['symbol'],
                    defaults={
                        'name': f['name'],
                        'currency': f['currency'],
                        'asset_type': f['asset_type'],
                        'sector': f['sector'],
                        'yahoo_ticker': f.get('yahoo_ticker', f['symbol'])
                    }
                )
                pk_to_real_asset[item['pk']] = asset

        # 5. Import Transakcji
        count = 0
        for item in RAW_DATA:
            if item['model'] == 'core.transaction':
                # Pomin transakcje bez assetu (poza CASH) lub te powiazane z NVDA (Asset 15)
                asset_pk = item['fields'].get('asset')

                if asset_pk == 15:
                    continue

                real_asset = pk_to_real_asset.get(asset_pk)

                # Zezwalamy na asset=None tylko jesli to operacja gotowkowa (DEPOSIT/WITHDRAWAL)
                if real_asset is None and item['fields']['type'] not in ['DEPOSIT', 'WITHDRAWAL', 'OTHER']:
                    continue

                f = item['fields']
                Transaction.objects.create(
                    portfolio=portfolio,
                    asset=real_asset,
                    date=f['date'],
                    type=f['type'],
                    amount=Decimal(f['amount']),
                    quantity=Decimal(f['quantity']),
                    price=Decimal(f['price']) if f['price'] else None,
                    comment=f.get('comment', '')
                )
                count += 1

        self.stdout.write(self.style.SUCCESS(f'SUKCES! Wgrano {count} transakcji do Demo.'))