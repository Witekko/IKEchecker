from django.db import models
from django.contrib.auth.models import User


class Asset(models.Model):
    """
    Asset catalog. Once added 'PKN.PL' serves all users.
    """
    symbol = models.CharField(max_length=20, unique=True, help_text="XTB Symbol, e.g., PKN.PL")
    yahoo_ticker = models.CharField(max_length=20, help_text="Yahoo Symbol, e.g., PKN.WA")
    currency = models.CharField(max_length=3, default='PLN', help_text="Currency, e.g., PLN, EUR")
    name = models.CharField(max_length=100, blank=True, help_text="Full name, e.g., Orlen S.A.")

    def __str__(self):
        return f"{self.symbol} ({self.yahoo_ticker})"


class Portfolio(models.Model):
    """
    User portfolio.
    """
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=50, default="My IKE")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Portfolio: {self.name} ({self.user.username})"


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