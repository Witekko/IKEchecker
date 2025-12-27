from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .forms import UploadFileForm, CustomUserCreationForm
from .models import Portfolio
from .services.taxes import get_taxes_context
# Importujemy serwisy
from .services import (
    process_xtb_file,
    get_dashboard_context,
    get_dividend_context,
    get_asset_details_context
)
# Importujemy newsy osobno
from .services.news import get_asset_news


# --- HELPER: POBIERANIE AKTYWNEGO PORTFELA ---
def get_active_portfolio(request):
    user_portfolios = Portfolio.objects.filter(user=request.user).order_by('id')
    if not user_portfolios.exists():
        new_p = Portfolio.objects.create(user=request.user, name="My IKE", portfolio_type='IKE')
        request.session['active_portfolio_id'] = new_p.id
        return new_p

    active_id = request.session.get('active_portfolio_id')
    if active_id:
        portfolio = user_portfolios.filter(id=active_id).first()
        if portfolio: return portfolio

    first_portfolio = user_portfolios.first()
    request.session['active_portfolio_id'] = first_portfolio.id
    return first_portfolio


# --- WIDOKI ---

@login_required
def dashboard_view(request):
    active_portfolio = get_active_portfolio(request)
    context = get_dashboard_context(request.user, portfolio_id=active_portfolio.id)

    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})
    return render(request, 'dashboard.html', context)


@login_required
def assets_list_view(request):
    active_portfolio = get_active_portfolio(request)
    context = get_dashboard_context(request.user, portfolio_id=active_portfolio.id)

    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})
    return render(request, 'assets_list.html', context)


@login_required
def dividends_view(request):
    active_portfolio = get_active_portfolio(request)

    # --- ZMIANA: Przekazujemy ID aktywnego portfela ---
    context = get_dividend_context(request.user, portfolio_id=active_portfolio.id)

    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'dividends.html', context)


@login_required
def asset_details_view(request, symbol):
    active_portfolio = get_active_portfolio(request)

    # 1. Pobieramy dane finansowe (z portfolio.py)
    context = get_asset_details_context(request.user, symbol, portfolio_id=active_portfolio.id)

    # Fallback przy błędzie
    if 'error' in context:
        return render(request, 'dashboard.html', {
            'error': context['error'],
            'all_portfolios': Portfolio.objects.filter(user=request.user),
            'active_portfolio': active_portfolio
        })

    # 2. Pobieramy newsy
    asset_name = context.get('asset_name', '')
    context['news'] = get_asset_news(symbol, asset_name)

    # Switcher
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio

    return render(request, 'asset_details.html', context)


@login_required
def upload_view(request):
    active_portfolio = get_active_portfolio(request)
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                stats = process_xtb_file(request.FILES['file'], active_portfolio)
                messages.success(request, f"Success! Added: {stats['added']} transactions to {active_portfolio.name}.")
                return redirect('dashboard')
            except Exception as e:
                messages.error(request, f"Error: {e}")
    else:
        form = UploadFileForm()

    return render(request, 'upload.html', {
        'form': form,
        'all_portfolios': Portfolio.objects.filter(user=request.user),
        'active_portfolio': active_portfolio
    })


# --- ZARZĄDZANIE PORTFELAMI ---

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

    # Logika podatkowa
    context = get_taxes_context(request.user, portfolio_id=active_portfolio.id)

    # Standardowe dane nawigacyjne
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio

    return render(request, 'taxes.html', context)