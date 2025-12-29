from django.test import TestCase
from decimal import Decimal
from datetime import datetime
from django.utils import timezone
from .models import Transaction, Asset, Portfolio
from django.contrib.auth.models import User
from .services.calculator import PortfolioCalculator

class PortfolioCalculatorTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.portfolio = Portfolio.objects.create(user=self.user, name="Test Portfolio", portfolio_type='IKE')
        self.asset = Asset.objects.create(symbol='TEST', yahoo_ticker='TEST', currency='PLN', name='Test Asset')

    def test_fifo_calculation(self):
        # 1. Buy 10 shares at 100 PLN
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            xtb_id='1',
            date=timezone.make_aware(datetime(2023, 1, 1, 10, 0, 0)),
            type='BUY',
            amount=1000.00,
            quantity=10.0
        )

        # 2. Buy 10 shares at 120 PLN
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            xtb_id='2',
            date=timezone.make_aware(datetime(2023, 1, 2, 10, 0, 0)),
            type='BUY',
            amount=1200.00,
            quantity=10.0
        )

        # 3. Sell 15 shares at 150 PLN
        # FIFO Logic:
        # - Sell 10 shares from batch 1 (Cost: 1000, Revenue: 1500, Profit: 500)
        # - Sell 5 shares from batch 2 (Cost: 600, Revenue: 750, Profit: 150)
        # Total Realized Profit: 650
        # Remaining: 5 shares from batch 2 (Cost Basis: 600)
        Transaction.objects.create(
            portfolio=self.portfolio,
            asset=self.asset,
            xtb_id='3',
            date=timezone.make_aware(datetime(2023, 1, 3, 10, 0, 0)),
            type='SELL',
            amount=2250.00, # 15 * 150
            quantity=15.0
        )

        transactions = Transaction.objects.filter(portfolio=self.portfolio)
        calc = PortfolioCalculator(transactions).process()
        holdings = calc.get_holdings()

        self.assertIn('TEST', holdings)
        data = holdings['TEST']

        self.assertEqual(data['qty'], 5.0)
        self.assertEqual(data['cost'], 600.0)
        self.assertEqual(data['realized'], 650.0)

    def test_deposit_withdrawal_logic(self):
        # Deposit 1000
        Transaction.objects.create(
            portfolio=self.portfolio,
            xtb_id='D1',
            date=timezone.make_aware(datetime(2023, 1, 1, 10, 0, 0)),
            type='DEPOSIT',
            amount=1000.00,
            quantity=0
        )
        
        # Withdrawal 200
        Transaction.objects.create(
            portfolio=self.portfolio,
            xtb_id='W1',
            date=timezone.make_aware(datetime(2023, 1, 2, 10, 0, 0)),
            type='WITHDRAWAL',
            amount=-200.00,
            quantity=0
        )

        transactions = Transaction.objects.filter(portfolio=self.portfolio)
        calc = PortfolioCalculator(transactions).process()
        cash, invested_net = calc.get_cash_balance()

        self.assertEqual(cash, 800.0)
        self.assertEqual(invested_net, 800.0)

    def test_negative_deposit_floor(self):
        # Deposit 1000
        Transaction.objects.create(
            portfolio=self.portfolio,
            xtb_id='D1',
            date=timezone.make_aware(datetime(2023, 1, 1, 10, 0, 0)),
            type='DEPOSIT',
            amount=1000.00,
            quantity=0
        )

        # Withdrawal 1500 (Profit withdrawal scenario)
        Transaction.objects.create(
            portfolio=self.portfolio,
            xtb_id='W1',
            date=timezone.make_aware(datetime(2023, 1, 2, 10, 0, 0)),
            type='WITHDRAWAL',
            amount=-1500.00,
            quantity=0
        )

        transactions = Transaction.objects.filter(portfolio=self.portfolio)
        calc = PortfolioCalculator(transactions).process()
        cash, invested_net = calc.get_cash_balance()

        self.assertEqual(cash, -500.0) # Cash balance is just sum of flows
        self.assertEqual(invested_net, 0.0) # Invested capital cannot be negative