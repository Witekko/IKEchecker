from django.test import TestCase
from django.utils import timezone
from decimal import Decimal
from django.contrib.auth import get_user_model
from core.models import Portfolio, Asset, Transaction, PortfolioType, TransactionType
from core.services.calculator import PortfolioCalculator
from core.services.importers.parsers import XtbParser
import pandas as pd

User = get_user_model()

class PortfolioCalculatorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="password123")
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name="Test Portfolio",
            portfolio_type=PortfolioType.STANDARD,
            currency="PLN"
        )
        self.asset = Asset.objects.create(
            symbol="TEST.PL",
            name="Test Asset",
            currency="PLN"
        )

    def test_position_id_matching(self):
        # Buy position 1: 3 shares at 100 PLN
        t1 = Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.BUY,
            amount=Decimal('-300.00'),
            quantity=Decimal('3.0000'),
            position_id="POS_123"
        )
        # Buy position 2 (cheaper): 3 shares at 80 PLN
        t2 = Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.BUY,
            amount=Decimal('-240.00'),
            quantity=Decimal('3.0000'),
            position_id="POS_456"
        )
        # Sell position 2: 3 shares at 110 PLN (referencing POS_456)
        t3 = Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.SELL,
            amount=Decimal('330.00'),
            quantity=Decimal('3.0000'),
            position_id="POS_456"
        )

        calc = PortfolioCalculator(Transaction.objects.filter(portfolio=self.portfolio)).process()
        holdings = calc.get_holdings()

        # Realized profit for POS_456 should be: 330 - 240 = 90 PLN.
        # (Standard FIFO would match against t1 first: 330 - 300 = 30 PLN).
        self.assertEqual(holdings["TEST.PL"]["realized"], 90.0)
        # Remaining open position should be t1 (POS_123) with cost of 300 PLN.
        self.assertEqual(holdings["TEST.PL"]["cost"], 300.0)
        self.assertEqual(holdings["TEST.PL"]["qty"], 3.0)

    def test_fifo_fallback(self):
        # Buy 1: no position ID, 2 shares at 100 PLN
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.BUY,
            amount=Decimal('-200.00'),
            quantity=Decimal('2.0000')
        )
        # Sell 1: no position ID, 2 shares at 120 PLN
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.SELL,
            amount=Decimal('240.00'),
            quantity=Decimal('2.0000')
        )

        calc = PortfolioCalculator(Transaction.objects.filter(portfolio=self.portfolio)).process()
        holdings = calc.get_holdings()

        # Should fallback to FIFO and calculate: 240 - 200 = 40 PLN
        self.assertEqual(holdings["TEST.PL"]["realized"], 40.0)
        self.assertEqual(holdings["TEST.PL"]["qty"], 0.0)

    def test_consolidated_currency_calculator(self):
        # Create USD portfolio
        usd_portfolio = Portfolio.objects.create(
            user=self.user,
            name="USD Portfolio",
            portfolio_type=PortfolioType.STANDARD,
            currency="USD"
        )
        # Deposit 100 USD
        Transaction.objects.create(
            portfolio=usd_portfolio,
            date=timezone.now(),
            type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            quantity=Decimal('0')
        )
        # Deposit 100 PLN in PLN portfolio
        Transaction.objects.create(
            portfolio=self.portfolio,
            date=timezone.now(),
            type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            quantity=Decimal('0')
        )
        
        # Test consolidated cash calculation targeting PLN portfolio currency
        rates = {'USD': 4.0}
        all_trans = Transaction.objects.filter(portfolio__in=[self.portfolio, usd_portfolio])
        calc = PortfolioCalculator(all_trans, portfolio_currency="PLN", currency_rates=rates).process()
        
        cash, invested = calc.get_cash_balance()
        # 100 PLN + (100 USD * 4.0) = 500 PLN
        self.assertEqual(cash, 500.0)
        self.assertEqual(invested, 500.0)

    def test_performance_calculator_currency_conversion(self):
        # Create USD portfolio
        usd_portfolio = Portfolio.objects.create(
            user=self.user,
            name="USD Portfolio",
            portfolio_type=PortfolioType.STANDARD,
            currency="USD"
        )
        # Deposit 100 USD
        Transaction.objects.create(
            portfolio=usd_portfolio,
            date=timezone.now(),
            type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            quantity=Decimal('0')
        )
        # Deposit 100 PLN in PLN portfolio
        Transaction.objects.create(
            portfolio=self.portfolio,
            date=timezone.now(),
            type=TransactionType.DEPOSIT,
            amount=Decimal('100.00'),
            quantity=Decimal('0')
        )
        
        rates = {'USD': 4.0}
        all_trans = Transaction.objects.filter(portfolio__in=[self.portfolio, usd_portfolio])
        from core.services.performance import PerformanceCalculator
        perf = PerformanceCalculator(all_trans, portfolio_currency="PLN", currency_rates=rates)
        
        metrics = perf.calculate_metrics(start_date=timezone.now().date(), current_total_value=500.0)
        # profit should be: current_total_value (500) - start_value (0) - net_deposits (100 PLN + 100 USD * 4.0 = 500 PLN) = 0
        self.assertEqual(metrics['profit'], 0.0)


class XtbParserTests(TestCase):
    def test_transfer_mapping(self):
        parser = XtbParser()
        # Transfer out (Negative amount)
        row_out = {
            'ID': 12345,
            'Type': 'Transfer',
            'Time': '2026-08-01 10:00:00',
            'Amount': '-100.00',
            'Comment': 'Withdrawal'
        }
        res_out = parser.parse_row(row_out)
        self.assertEqual(res_out['type'], 'WITHDRAWAL')

        # Transfer in (Positive amount)
        row_in = {
            'ID': 12346,
            'Type': 'Transfer',
            'Time': '2026-08-01 10:05:00',
            'Amount': '150.00',
            'Comment': 'Deposit'
        }
        res_in = parser.parse_row(row_in)
        self.assertEqual(res_in['type'], 'DEPOSIT')

    def test_quantity_parsing_old_and_new_formats(self):
        parser = XtbParser()
        
        # 1. Old XTB format: OPEN BUY <qty> @ <price>
        row_old = {
            'ID': 1001,
            'Type': 'Stock purchase',
            'Ticker': 'MBR.PL',
            'Time': '2026-05-15 14:34:01',
            'Amount': '-360.50',
            'Comment': 'OPEN BUY 1 @ 360.50'
        }
        res_old = parser.parse_row(row_old)
        self.assertEqual(res_old['quantity'], 1.0)
        self.assertEqual(res_old['price'], 360.50)

        # 2. Old fractional format: OPEN BUY <qty>/<total> @ <price>
        row_old_frac = {
            'ID': 1002,
            'Type': 'Stock purchase',
            'Ticker': 'CBF.PL',
            'Time': '2026-04-07 12:39:33',
            'Amount': '-4.53',
            'Comment': 'OPEN BUY 0.026/2.026 @ 174.10'
        }
        res_old_frac = parser.parse_row(row_old_frac)
        self.assertEqual(res_old_frac['quantity'], 0.026)
        self.assertEqual(res_old_frac['price'], 174.10)

        # 3. New XTB format (Oct 2026+): OPEN BUY <TICKER> <qty>/<total> @ <price>
        row_new_frac = {
            'ID': 1003,
            'Type': 'Stock purchase',
            'Ticker': 'CBF.PL',
            'Time': '2026-10-26 08:00:17',
            'Amount': '-61.75',
            'Comment': 'OPEN BUY CBF.PL 0.3183/1.3183 @ 194.00'
        }
        res_new_frac = parser.parse_row(row_new_frac)
        self.assertEqual(res_new_frac['quantity'], 0.3183)
        self.assertEqual(res_new_frac['price'], 194.00)

        # 4. New XTB format sell: CLOSE BUY <TICKER> <qty> @ <price>
        row_new_sell = {
            'ID': 1004,
            'Type': 'Stock sell',
            'Ticker': 'NVD.DE',
            'Time': '2026-10-08 07:00:10',
            'Amount': '78.93',
            'Comment': 'CLOSE BUY NVD.DE 0.3362 @ 210.85'
        }
        res_new_sell = parser.parse_row(row_new_sell)
        self.assertEqual(res_new_sell['quantity'], 0.3362)
        self.assertEqual(res_new_sell['price'], 210.85)

    def test_parse_row_nan_id_handling(self):
        import numpy as np
        parser = XtbParser()
        row_nan = {
            'ID': np.nan,
            'Type': 'Total',
            'Time': '2026-11-02 00:00:00',
            'Amount': '1000.00'
        }
        res = parser.parse_row(row_nan)
        self.assertIsNone(res['xtb_id'])


from django.urls import reverse

class DashboardApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="apiuser", password="apipassword")
        self.portfolio = Portfolio.objects.create(
            user=self.user,
            name="API Portfolio",
            portfolio_type=PortfolioType.STANDARD,
            currency="PLN"
        )
        self.asset = Asset.objects.create(
            symbol="API.PL",
            name="API Asset",
            currency="PLN"
        )
        # Add a buy transaction to give it some data
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            date=timezone.now(),
            type=TransactionType.BUY,
            amount=Decimal('-100.00'),
            quantity=Decimal('1.0000')
        )

    def test_dashboard_data_api_unauthorized(self):
        url = reverse('dashboard_data_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_dashboard_data_api_authorized(self):
        self.client.login(username="apiuser", password="apipassword")
        url = reverse('dashboard_data_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        
        data = response.json()
        self.assertIn('tile_value_raw', data)
        self.assertIn('tile_total_profit_raw', data)
        self.assertIn('last_transactions', data)
        
        # Verify the transactions serialization
        txs = data['last_transactions']
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]['asset_symbol'], "API.PL")

    def test_force_refresh_api_unauthorized(self):
        url = reverse('dashboard_force_refresh_api')
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302) # Redirect to login

    def test_force_refresh_api_non_staff(self):
        self.client.login(username="apiuser", password="apipassword")
        url = reverse('dashboard_force_refresh_api')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 403) # Unauthorized for non-staff

    def test_force_refresh_api_staff(self):
        # Create a staff user
        staff_user = User.objects.create_user(username="staffuser", password="staffpassword", is_staff=True)
        self.client.login(username="staffuser", password="staffpassword")
        url = reverse('dashboard_force_refresh_api')
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertIn('updated_assets_count', data)


from django.conf import settings

class SecuritySettingsTests(TestCase):
    def test_security_settings_active(self):
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')
        self.assertEqual(settings.X_FRAME_OPTIONS, 'DENY')
        self.assertEqual(settings.SECURE_REFERRER_POLICY, 'strict-origin-when-cross-origin')
        self.assertEqual(settings.SECURE_PROXY_SSL_HEADER, ('HTTP_X_FORWARDED_PROTO', 'https'))

    def test_traditional_login_via_allauth_view(self):
        user = User.objects.create_user(username="testloginuser", password="password123", email="testlogin@example.com")
        from allauth.account.models import EmailAddress
        EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
        
        # Test email login (since only email login is enforced now)
        response = self.client.post('/', {'login': 'testlogin@example.com', 'password': 'password123'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.endswith('/dashboard/'))


from core.models import Announcement
from core.context_processors import active_announcement

class AnnouncementTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpassword")

    def test_context_processor_no_announcements(self):
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        
        context = active_announcement(request)
        self.assertEqual(len(context['active_announcements']), 0)

    def test_context_processor_with_active_announcement(self):
        Announcement.objects.create(message="First inactive", is_active=False)
        Announcement.objects.create(message="Latest active", is_active=True)
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        
        context = active_announcement(request)
        self.assertEqual(len(context['active_announcements']), 1)
        self.assertEqual(context['active_announcements'][0].message, "Latest active")

    def test_dismiss_announcement_api(self):
        ann = Announcement.objects.create(message="Critical alert", is_active=True)
        self.client.login(username="testuser", password="testpassword")
        url = reverse('dismiss_announcement', args=[ann.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['success'])
        
        # Verify read state is created in DB
        from core.models import UserAnnouncementRead
        self.assertTrue(UserAnnouncementRead.objects.filter(user=self.user, announcement=ann).exists())

    def test_context_processor_hides_read_announcements(self):
        ann = Announcement.objects.create(message="Verify reset", is_active=True)
        from core.models import UserAnnouncementRead
        UserAnnouncementRead.objects.create(user=self.user, announcement=ann)
        
        from django.test import RequestFactory
        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user
        
        context = active_announcement(request)
        self.assertEqual(len(context['active_announcements']), 0)


from core.services.market import is_cache_stale
from datetime import datetime
import pytz

class MarketCacheAndDailyChangeTests(TestCase):
    def setUp(self):
        self.asset = Asset.objects.create(
            symbol="TEST.PL",
            yahoo_ticker="TEST.WA",
            last_price=100.0,
            previous_close=95.0,
            currency="PLN"
        )

    def test_cache_stale_when_no_price_or_date(self):
        self.asset.last_updated = None
        self.assertTrue(is_cache_stale(self.asset))

    def test_cache_stale_after_15_minutes(self):
        tz = pytz.timezone('Europe/Warsaw')
        t1 = tz.localize(datetime(2026, 11, 2, 10, 0, 0))
        t2 = tz.localize(datetime(2026, 11, 2, 10, 16, 0)) # 16 mins later
        self.asset.last_updated = t1
        self.assertTrue(is_cache_stale(self.asset, now=t2))

    def test_cache_fresh_within_15_minutes(self):
        tz = pytz.timezone('Europe/Warsaw')
        t1 = tz.localize(datetime(2026, 11, 2, 10, 0, 0))
        t2 = tz.localize(datetime(2026, 11, 2, 10, 5, 0)) # 5 mins later
        self.asset.last_updated = t1
        self.assertFalse(is_cache_stale(self.asset, now=t2))

    def test_cache_stale_crossing_warsaw_open(self):
        tz = pytz.timezone('Europe/Warsaw')
        t_pre = tz.localize(datetime(2026, 11, 2, 8, 55, 0)) # pre-open
        t_open = tz.localize(datetime(2026, 11, 2, 9, 2, 0))  # 7 mins later, but crossed 09:00
        self.asset.last_updated = t_pre
        self.assertTrue(is_cache_stale(self.asset, now=t_open))

    def test_cache_stale_crossing_us_open(self):
        tz = pytz.timezone('Europe/Warsaw')
        t_pre = tz.localize(datetime(2026, 11, 2, 15, 25, 0)) # pre-US open
        t_open = tz.localize(datetime(2026, 11, 2, 15, 32, 0)) # 7 mins later, but crossed 15:30
        self.asset.last_updated = t_pre
        self.assertTrue(is_cache_stale(self.asset, now=t_open))

    def test_unopened_market_zero_day_change(self):
        # When an asset has not opened today, last_price == previous_close
        self.asset.last_price = 100.0
        self.asset.previous_close = 100.0
        self.asset.save()
        
        cur_p = float(self.asset.last_price)
        prev_c = float(self.asset.previous_close)
        chg_pct = ((cur_p - prev_c) / prev_c * 100) if prev_c > 0 else 0.0
        chg_val = (10 * (cur_p - prev_c))
        
        self.assertEqual(chg_pct, 0.0)
        self.assertEqual(chg_val, 0.0)
