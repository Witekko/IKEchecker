# core/models.py

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


# --- NOWOŚĆ: SŁOWNIKI WYBORU (TextChoices) ---
# Używamy TextChoices dla lepszej czytelności i obsługi w kodzie,
# ale wartości (np. 'STOCK') pasują do tego co mogło być w bazie.

class AssetType(models.TextChoices):
    STOCK = 'STOCK', 'Stock'
    ETF = 'ETF', 'ETF'
    CRYPTO = 'CRYPTO', 'Cryptocurrency'
    CURRENCY = 'CURRENCY', 'Currency'
    COMMODITY = 'COMMODITY', 'Commodity'
    BOND = 'BOND', 'Bond'
    OTHER = 'OTHER', 'Other'


class AssetSector(models.TextChoices):
    TECHNOLOGY = 'TECHNOLOGY', 'Technology'
    FINANCE = 'FINANCE', 'Financial Services'
    ENERGY = 'ENERGY', 'Energy & Utilities'
    HEALTHCARE = 'HEALTHCARE', 'Healthcare'
    CONSUMER = 'CONSUMER', 'Consumer Goods'
    INDUSTRIAL = 'INDUSTRIAL', 'Industrials'
    REAL_ESTATE = 'REAL_ESTATE', 'Real Estate'
    MATERIALS = 'MATERIALS', 'Basic Materials'
    TELECOM = 'TELECOM', 'Telecommunications'
    GAMING = 'GAMING', 'Gaming & Entertainment'
    OTHER = 'OTHER', 'Other / Unknown'


class PortfolioType(models.TextChoices):
    STANDARD = 'STANDARD', 'Standard (Taxable)'
    IKE = 'IKE', 'IKE (Tax-Free)'
    IKZE = 'IKZE', 'IKZE (Tax-Deductible)'


class TransactionType(models.TextChoices):
    BUY = 'BUY', 'Buy'
    SELL = 'SELL', 'Sell'
    CLOSE = 'CLOSE', 'Close Position'  # <--- ZACHOWANO ZE STAREGO MODELU
    DEPOSIT = 'DEPOSIT', 'Deposit'
    WITHDRAWAL = 'WITHDRAWAL', 'Withdrawal'
    DIVIDEND = 'DIVIDEND', 'Dividend'
    TAX = 'TAX', 'Tax'
    FEE = 'FEE', 'Fee'
    OTHER = 'OTHER', 'Other'


# --- MODELE ---

class Portfolio(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='portfolios')
    name = models.CharField(max_length=50, default="My Portfolio")
    currency = models.CharField(max_length=3, default="PLN")

    # Zmieniono definicję choices na klasę, ale dane tekstowe są kompatybilne
    portfolio_type = models.CharField(
        max_length=10,
        choices=PortfolioType.choices,
        default=PortfolioType.STANDARD
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.get_portfolio_type_display()})"


class Asset(models.Model):
    symbol = models.CharField(max_length=20, unique=True)
    yahoo_ticker = models.CharField(max_length=20, blank=True, null=True)  # Poluzowano ograniczenia (może być puste)
    currency = models.CharField(max_length=10, default='PLN')
    name = models.CharField(max_length=100, blank=True)
    isin = models.CharField(max_length=20, blank=True, null=True)  # Nowe pole, opcjonalne

    # --- NOWE POLA (Z domyślnymi wartościami, żeby migracja przeszła gładko) ---
    asset_type = models.CharField(
        max_length=20,
        choices=AssetType.choices,
        default=AssetType.STOCK
    )
    sector = models.CharField(
        max_length=20,
        choices=AssetSector.choices,
        default=AssetSector.OTHER
    )

    # Cache (ZACHOWANO WSZYSTKIE POLA)
    last_price = models.DecimalField(max_digits=12, decimal_places=4, default=0.0, null=True, blank=True)
    previous_close = models.DecimalField(max_digits=12, decimal_places=4, default=0.0)  # <--- ZACHOWANO
    last_updated = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.symbol

    @property
    def display_name(self):
        """
        Zwraca sformatowaną nazwę: 'Pełna Nazwa (SYMBOL)'
        """
        if not self.name:
            return self.symbol

        clean_name = self.name.replace('_', ' ').strip()
        # Jeśli nazwa jest identyczna jak symbol, nie dublujmy (np. XTB (XTB))
        if clean_name.upper() == self.symbol.upper():
            return self.symbol

        return f"{clean_name} ({self.symbol})"


class Transaction(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name='transactions')

    # Zmieniamy on_delete na CASCADE (lub zostawiamy SET_NULL - tutaj decyzja projektowa)
    # W poprzednim modelu miałeś SET_NULL. Jeśli chcesz zachować historię nawet po usunięciu Assetu,
    # zostaw SET_NULL. Jeśli chcesz porządku - CASCADE.
    # Bezpieczniej dla Ciebie teraz: Zostawiamy SET_NULL jak było.
    asset = models.ForeignKey(Asset, on_delete=models.SET_NULL, null=True, blank=True)

    xtb_id = models.CharField(max_length=100, blank=True, null=True)  # Zwiększono limit znaków dla bezpieczeństwa

    date = models.DateTimeField()
    type = models.CharField(max_length=20, choices=TransactionType.choices)

    # Zachowano max_digits=15
    amount = models.DecimalField(max_digits=15, decimal_places=2, help_text="Cashflow in account currency")
    quantity = models.DecimalField(max_digits=15, decimal_places=4, default=0)

    # Nowe pole, opcjonalne (do ręcznych wpisów)
    price = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)

    comment = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-date']
        # Dodano unikalność, żeby nie dublować przy imporcie (chyba że xtb_id jest puste)
        unique_together = ('portfolio', 'xtb_id')

    def __str__(self):
        asset_sym = self.asset.symbol if self.asset else 'CASH'
        return f"{self.date.date()} - {self.type} - {asset_sym}"


class PriceHistory(models.Model):
    """
    ZACHOWANO: Tabela cache dla wykresów historycznych.
    """
    asset = models.ForeignKey(Asset, on_delete=models.CASCADE, related_name='prices')
    date = models.DateField()
    close_price = models.DecimalField(max_digits=10, decimal_places=4)

    class Meta:
        unique_together = ('asset', 'date')
        ordering = ['-date']