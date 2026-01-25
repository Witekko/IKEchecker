# core/views.py

from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.utils import timezone
from django.contrib.auth import login, authenticate
from django.core.management import call_command
from django.contrib.auth.models import User
# --- MODELE I FORMY ---
from .models import Portfolio, Transaction, Asset, AssetSector, AssetType
from .forms import UploadFileForm, CustomUserCreationForm, PortfolioSettingsForm

# --- WARSTWA USŁUG (SERVICES & SELECTORS) ---
from .services.selectors import get_active_portfolio, get_user_portfolios, get_all_assets
from .services import (
    process_xtb_file, get_dashboard_context, get_dividend_context,
    get_asset_details_context, get_taxes_context,
    fetch_asset_metadata, get_asset_news, add_manual_transaction
)
# Importujemy nowe akcje bulkowe
from .services.actions import update_assets_bulk, sync_all_assets_metadata
from .services.dashboard import get_dashboard_stats_context, get_holdings_view_context


# --- WIDOKI ---

@login_required
def dashboard_view(request):
    """Główny widok Dashboardu."""
    active_portfolio = get_active_portfolio(request)
    range_mode = request.GET.get('range', 'all')

    context = get_dashboard_context(request.user, portfolio_id=active_portfolio.id)
    stats_context = get_dashboard_stats_context(active_portfolio, range_mode)
    context.update(stats_context)

    context['all_portfolios'] = get_user_portfolios(request.user)
    context['active_portfolio'] = active_portfolio
    context['current_range'] = range_mode

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})

    return render(request, 'dashboard.html', context)


@login_required
def assets_list_view(request):
    """Widok tabeli aktywów (Holdings)."""
    active_portfolio = get_active_portfolio(request)
    range_mode = request.GET.get('range', 'all')

    context = get_holdings_view_context(request.user, active_portfolio, range_mode)

    context['all_portfolios'] = get_user_portfolios(request.user)
    context['active_portfolio'] = active_portfolio
    context['current_range'] = range_mode

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})

    return render(request, 'assets_list.html', context)


@login_required
def dividends_view(request):
    active_portfolio = get_active_portfolio(request)
    context = get_dividend_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = get_user_portfolios(request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'dividends.html', context)


@login_required
def asset_details_view(request, symbol):
    active_portfolio = get_active_portfolio(request)
    context = get_asset_details_context(request.user, symbol, portfolio_id=active_portfolio.id)

    if 'error' in context:
        return render(request, 'dashboard.html',
                      {'error': context['error'],
                       'all_portfolios': get_user_portfolios(request.user),
                       'active_portfolio': active_portfolio})

    asset_name = context.get('asset_name', '')
    context['news'] = get_asset_news(symbol, asset_name)
    context['all_portfolios'] = get_user_portfolios(request.user)
    context['active_portfolio'] = active_portfolio

    return render(request, 'asset_details.html', context)


@login_required
def upload_view(request):
    active_portfolio = get_active_portfolio(request)
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                overwrite = request.POST.get('overwrite_manual') == 'on'
                stats = process_xtb_file(request.FILES['file'], active_portfolio, overwrite_manual=overwrite)
                msg = f"Success! Added: {stats['added']} transactions."
                if overwrite: msg += " (Cleaned manual entries)."
                messages.success(request, msg)
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"Error: {e}")
    else:
        form = UploadFileForm()

    return render(request, 'upload.html', {
        'form': form,
        'all_portfolios': get_user_portfolios(request.user),
        'active_portfolio': active_portfolio
    })


@login_required
def switch_portfolio_view(request, portfolio_id):
    portfolio = get_object_or_404(Portfolio, id=portfolio_id, user=request.user)
    request.session['active_portfolio_id'] = portfolio.id
    request.session.modified = True
    messages.success(request, f"Switched to: {portfolio.name}")
    return redirect('dashboard')


@login_required
def create_portfolio_view(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        p_type = request.POST.get('type')
        if name and p_type:
            p = Portfolio.objects.create(user=request.user, name=name, portfolio_type=p_type)
            request.session['active_portfolio_id'] = p.id
            request.session.modified = True
            messages.success(request, f"Created portfolio: {name}")
            return redirect('dashboard')
    return redirect('dashboard')


def register_view(request):
    if request.method == 'POST':
        form = CustomUserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            Portfolio.objects.create(user=user, name="My IKE", portfolio_type='IKE')
            login(request, user)
            messages.success(request, "Account created successfully!")
            return redirect('dashboard')
        else:
            messages.error(request, "Registration error.")
    else:
        form = CustomUserCreationForm()
    return render(request, 'register.html', {'form': form})


def taxes_view(request):
    active_portfolio = get_active_portfolio(request)
    context = get_taxes_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = get_user_portfolios(request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'taxes.html', context)


@login_required
def delete_transaction_view(request, transaction_id):
    transaction = get_object_or_404(Transaction, id=transaction_id, portfolio__user=request.user)
    transaction.delete()
    messages.success(request, "Transaction deleted successfully.")
    return redirect('portfolio_settings')


@login_required
def portfolio_settings_view(request):
    active_portfolio = get_active_portfolio(request)

    if request.method == 'POST':
        if 'manual_add' in request.POST:
            try:
                raw_date = request.POST.get('date')
                dt_obj = datetime.strptime(raw_date, "%Y-%m-%dT%H:%M")
                dt_obj = timezone.make_aware(dt_obj)

                data = {
                    'type': request.POST.get('type'),
                    'date_obj': dt_obj,
                    'symbol': request.POST.get('symbol'),
                    'quantity': request.POST.get('quantity'),
                    'price': request.POST.get('price'),
                    'amount': request.POST.get('amount'),
                    'auto_deposit': request.POST.get('auto_deposit') == 'on'
                }
                msg = add_manual_transaction(active_portfolio, data)
                messages.success(request, msg)
                return redirect('portfolio_settings')

            except ValueError as e:
                messages.error(request, str(e))
                return redirect('portfolio_settings')
            except Exception as e:
                messages.error(request, f"System error: {e}")
                return redirect('portfolio_settings')

        elif 'save_settings' in request.POST:
            form = PortfolioSettingsForm(request.POST, instance=active_portfolio)
            if form.is_valid():
                form.save()
                messages.success(request, "Portfolio settings updated successfully.")
                return redirect('portfolio_settings')

        elif 'clear_transactions' in request.POST:
            count, _ = Transaction.objects.filter(portfolio=active_portfolio).delete()
            messages.warning(request, f"Cleared {count} transactions.")
            return redirect('dashboard')
        elif 'delete_portfolio' in request.POST:
            active_portfolio.delete()
            if 'active_portfolio_id' in request.session: del request.session['active_portfolio_id']
            messages.error(request, "Portfolio deleted.")
            return redirect('dashboard')
    else:
        form = PortfolioSettingsForm(instance=active_portfolio)

    recent_transactions = Transaction.objects.filter(portfolio=active_portfolio).order_by('-date', '-id')[:20]

    context = {
        'form': form,
        'active_portfolio': active_portfolio,
        'all_portfolios': get_user_portfolios(request.user),
        'recent_transactions': recent_transactions
    }
    return render(request, 'portfolio_settings.html', context)


@login_required
def manage_assets_view(request):
    """
    Widok zarządzania aktywami.
    Logika biznesowa (zapis/sync) przeniesiona do 'actions.py'.
    Pobieranie danych przeniesione do 'selectors.py'.
    """
    active_portfolio = get_active_portfolio(request)

    if request.method == 'POST':
        # --- LOGIKA 1: ZAPIS RĘCZNY ---
        if 'save_changes' in request.POST:
            try:
                # Delegacja do serwisu
                updated_count = update_assets_bulk(request.POST)
                messages.success(request, f"Saved changes for {updated_count} assets.")
                return redirect('manage_assets')
            except Exception as e:
                messages.error(request, f"Error saving: {e}")

        # --- LOGIKA 2: AUTO-FILL Z YAHOO ---
        elif 'sync_yahoo' in request.POST:
            try:
                # Delegacja do serwisu
                updated, errors = sync_all_assets_metadata()
                messages.success(request, f"Auto-filled {updated} assets. (Skipped/Errors: {errors})")
                return redirect('manage_assets')
            except Exception as e:
                messages.error(request, f"Yahoo Sync Error: {e}")

    # GET - Pobieranie danych
    assets = get_all_assets()

    context = {
        'assets': assets,
        'sector_choices': AssetSector.choices,
        'type_choices': AssetType.choices,
        'all_portfolios': get_user_portfolios(request.user),
        'active_portfolio': active_portfolio
    }
    return render(request, 'manage_assets.html', context)


def demo_login_view(request):
    """
    Loguje użytkownika 'demo_user' bez hasła, uprzednio resetując jego dane.
    """
    username = 'demo_user'

    # 1. Reset danych (Clean Slate)
    # To zapewnia, że każdy rekruter widzi świeże dane
    call_command('reset_demo')

    # 2. Pobranie użytkownika (stworzonego przez komendę wyżej)
    try:
        user = User.objects.get(username=username)

        # 3. Wymuszone logowanie (obejście hasła)
        # Backend 'ModelBackend' jest standardem w Django
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')

        messages.success(request, "Zalogowano do trybu DEMO. Dane zostały przywrócone do stanu wzorcowego.")
        return redirect('dashboard')

    except User.DoesNotExist:
        messages.error(request, "Błąd konfiguracji Demo. Użytkownik nie istnieje.")
        return redirect('login')