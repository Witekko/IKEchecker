from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Asset(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    yahoo_ticker = models.CharField(max_length=20)
    currency = models.CharField(max_length=10, default='PLN')
    name = models.CharField(max_length=100, blank=True)

    # Cache
    last_price = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    previous_close = models.DecimalField(max_digits=10, decimal_places=4, default=0.0)
    last_updated = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.symbol


class Portfolio(models.Model):
    """
    User portfolio with support for multiple types (IKE vs Standard).
    """
    PORTFOLIO_TYPES = [
        ('IKE', 'IKE (Tax-Free)'),
        ('IKZE', 'IKZE (Tax-Free)'),
        ('STANDARD', 'Standard (Taxable)'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=50, default="My IKE")

    # To jest kluczowe nowe pole:
    portfolio_type = models.CharField(max_length=10, choices=PORTFOLIO_TYPES, default='IKE')

    currency = models.CharField(max_length=3, default='PLN')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_portfolio_type_display()})"


class Transaction(models.Model):
    """
    Single row from the Excel file.
    """
    TRANSACTION_TYPES = [
        ('BUY', 'Buy'),
        ('SELL', 'Sell'),
        ('DEPOSIT', 'Deposit'),
        ('WITHDRAWAL', 'Withdrawal'),
        ('DIVIDEND', 'Dividend'),
        ('TAX', 'Tax'),
        ('OTHER', 'Other'),
    ]

    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='transactions')
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True)

    # Unique ID from XTB prevents duplicates
    xtb_id = models.CharField(max_length=50, unique=True, help_text="Unique operation ID from XTB")

    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TRANSACTION_TYPES)

    # Financials: max_digits=15, decimal_places=2
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Transaction amount in account currency")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=0, help_text="Number of shares")

    comment = models.TextField(blank=True, help_text="Original comment from XTB")

    def __str__(self):
        return f"{self.date.date()} - {self.type} - {self.asset.symbol if self.asset else 'CASH'}"


class PriceHistory(models.Model):
    """
    Price cache from Yahoo.
    """
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='prices')
    date = models.DateField()
    close_price = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        unique_together = ('asset', 'date')
        ordering = ['-date']