from django.db.models import QuerySet
from ..models import Portfolio, Transaction, Asset

def get_user_portfolios(user) -> QuerySet[Portfolio]:
    """Zwraca wszystkie portfele danego użytkownika."""
    return Portfolio.objects.filter(user=user).order_by('id')

def get_portfolio_by_id(user, portfolio_id) -> Portfolio:
    """Zwraca konkretny portfel lub None."""
    if not portfolio_id:
        return None
    return Portfolio.objects.filter(id=portfolio_id, user=user).first()

def get_transactions(user, portfolio_id=None) -> QuerySet[Transaction]:
    """
    Zwraca transakcje dla konkretnego portfela LUB wszystkich portfeli usera.
    Posortowane chronologicznie.
    """
    if portfolio_id:
        return Transaction.objects.filter(portfolio_id=portfolio_id).order_by('date')
    return Transaction.objects.filter(portfolio__user=user).order_by('date')

def get_asset_by_symbol(symbol: str) -> Asset:
    """Pobiera obiekt Asset po symbolu."""
    try:
        return Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return None