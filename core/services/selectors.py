# core/selectors.py

from django.db.models import QuerySet
from ..models import Portfolio, Transaction, Asset


def get_active_portfolio(request):
    """
    Pobiera aktywny portfel z sesji lub tworzy domyślny.
    To jest logika biznesowa wyboru portfela, nie powinna być w widoku.
    """
    user = request.user
    user_portfolios = Portfolio.objects.filter(user=user).order_by('id')

    if not user_portfolios.exists():
        new_p = Portfolio.objects.create(user=user, name="My IKE", portfolio_type='IKE')
        request.session['active_portfolio_id'] = new_p.id
        return new_p

    active_id = request.session.get('active_portfolio_id')
    if active_id:
        p = user_portfolios.filter(id=active_id).first()
        if p: return p

    # Fallback: pierwszy dostępny
    first_p = user_portfolios.first()
    request.session['active_portfolio_id'] = first_p.id
    return first_p


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
def get_all_assets():
    """Zwraca wszystkie aktywa posortowane po symbolu."""
    return Asset.objects.all().order_by('symbol')