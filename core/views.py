from datetime import timedelta, date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from .services.portfolio import enrich_assets_context
# --- MODELE ---
from .models import Portfolio, Transaction
from .forms import UploadFileForm, CustomUserCreationForm

# --- SERWISY ---
from .services import (
    process_xtb_file, get_dashboard_context, get_dividend_context,
    get_asset_details_context
)
from .services.taxes import get_taxes_context
from .services.analytics import analyze_history, analyze_holdings
from .services.market import get_current_currency_rates
from .services.news import get_asset_news
from .services.performance import PerformanceCalculator

try:
    from .services.config import fmt_2
except ImportError:
    def fmt_2(val):
        return "{:.2f}".format(val)


# --- MIXINS / SERVICES ---

class DashboardService:
    """Encapsulates dashboard logic to keep views thin."""
    
    @staticmethod
    def get_active_portfolio(request):
        user_portfolios = Portfolio.objects.filter(user=request.user).order_by('id')
        if not user_portfolios.exists():
            new_p = Portfolio.objects.create(user=request.user, name="My IKE", portfolio_type='IKE')
            request.session['active_portfolio_id'] = new_p.id
            return new_p
        active_id = request.session.get('active_portfolio_id')
        if active_id:
            p = user_portfolios.filter(id=active_id).first()
            if p: return p
        first_p = user_portfolios.first()
        request.session['active_portfolio_id'] = first_p.id
        return first_p

    @staticmethod
    def calculate_range_dates(range_mode):
        today = date.today()
        if range_mode == '1m': return today - timedelta(days=30)
        elif range_mode == '3m': return today - timedelta(days=90)
        elif range_mode == '6m': return today - timedelta(days=180)
        elif range_mode == 'ytd': return date(today.year, 1, 1)
        elif range_mode == '1y': return today - timedelta(days=365)
        return None

    @staticmethod
    def filter_timeline(timeline, start_date):
        if not start_date: return timeline
        dates_str = timeline.get('dates', [])
        if not dates_str: return timeline
        start_idx = 0
        for i, d_str in enumerate(dates_str):
            try:
                if datetime.strptime(d_str, "%Y-%m-%d").date() >= start_date:
                    start_idx = i
                    break
            except:
                pass
        filtered = {}
        for key, val in timeline.items():
            if isinstance(val, list) and len(val) == len(dates_str):
                filtered[key] = val[start_idx:]
            else:
                filtered[key] = val
        return filtered

    @staticmethod
    def calculate_performance_metrics(transactions, start_date=None):
        if not transactions.exists():
            return "0.00", "0.00", "0.00", "0.00", {}

        rates = get_current_currency_rates()
        eur = rates.get('EUR', 4.30)
        usd = rates.get('USD', 4.00)

        full_timeline = analyze_history(transactions, eur, usd)
        stats = analyze_holdings(transactions, eur, usd)
        current_val = stats['total_value']

        perf = PerformanceCalculator(transactions)
        metrics = perf.calculate_metrics(
            timeline_data=full_timeline,
            start_date=start_date,
            current_total_value=current_val
        )

        mwr_str = fmt_2(metrics['xirr'])
        roi_str = fmt_2(metrics['simple_return'])
        profit_str = fmt_2(metrics['profit'])

        twr_percent = perf.calculate_twr(full_timeline, start_date_filter=start_date)
        twr_str = fmt_2(twr_percent)

        filtered_timeline = DashboardService.filter_timeline(full_timeline, start_date)

        return mwr_str, twr_str, roi_str, profit_str, filtered_timeline


# --- WIDOKI ---

@login_required
def dashboard_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)
    range_mode = request.GET.get('range', 'all')
    start_date = DashboardService.calculate_range_dates(range_mode)

    context = get_dashboard_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    context['current_range'] = range_mode

    transactions = Transaction.objects.filter(portfolio=active_portfolio)
    mwr, twr, roi, profit, chart_data = DashboardService.calculate_performance_metrics(transactions, start_date)

    context['tile_mwr'] = mwr
    context['tile_twr'] = twr
    context['tile_return_pct_str'] = roi
    context['tile_total_profit_str'] = profit

    try:
        context['tile_total_profit_raw'] = float(profit)
        context['tile_return_pct_raw'] = float(roi)
    except:
        pass

    if chart_data:
        context['timeline_dates'] = chart_data.get('dates', [])
        context['timeline_total_value'] = chart_data.get('val_user', [])
        context['timeline_invested'] = chart_data.get('val_inv', [])
        context['timeline_deposit_points'] = chart_data.get('points', [])
        context['timeline_pct_user'] = chart_data.get('pct_user', [])
        context['timeline_pct_wig'] = chart_data.get('pct_wig', [])
        context['timeline_pct_sp500'] = chart_data.get('pct_sp500', [])
        context['timeline_pct_inflation'] = chart_data.get('pct_inf', [])

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})
    return render(request, 'dashboard.html', context)


@login_required
def assets_list_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)

    range_mode = request.GET.get('range', 'all')
    start_date = DashboardService.calculate_range_dates(range_mode)

    context = get_dashboard_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    context['current_range'] = range_mode

    # Metryki Globalne (TWR, ROI)
    transactions = Transaction.objects.filter(portfolio=active_portfolio)
    mwr, twr, roi, profit, _ = DashboardService.calculate_performance_metrics(transactions, start_date)

    context['tile_mwr'] = mwr
    context['tile_twr'] = twr
    context['tile_return_pct_str'] = roi
    context['tile_total_profit_str'] = profit

    try:
        context['tile_total_profit_raw'] = float(profit)
        context['tile_return_pct_raw'] = float(roi)
    except:
        pass

    # DYNAMICZNA TABELA (Kluczowa zmiana)
    rates = get_current_currency_rates()
    eur = rates.get('EUR', 4.30)
    usd = rates.get('USD', 4.00)

    # 1. Pobieramy surowe dane (floaty) z analityki
    dynamic_stats = analyze_holdings(transactions, eur, usd, start_date=start_date)

    # 2. Formatujemy je do wyświetlenia (stringi), używając helpera z portfolio.py
    # To nadpisuje pln_items/foreign_items w kontekście
    enrich_assets_context(context, dynamic_stats['assets'], dynamic_stats['total_value'])

    if 'error' in context:
        return render(request, 'dashboard.html', {'error': context['error']})
    return render(request, 'assets_list.html', context)


@login_required
def dividends_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)
    context = get_dividend_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'dividends.html', context)


@login_required
def asset_details_view(request, symbol):
    active_portfolio = DashboardService.get_active_portfolio(request)
    context = get_asset_details_context(request.user, symbol, portfolio_id=active_portfolio.id)
    if 'error' in context:
        return render(request, 'dashboard.html', {
            'error': context['error'],
            'all_portfolios': Portfolio.objects.filter(user=request.user),
            'active_portfolio': active_portfolio
        })
    asset_name = context.get('asset_name', '')
    context['news'] = get_asset_news(symbol, asset_name)
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'asset_details.html', context)


@login_required
def upload_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)
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
    active_portfolio = DashboardService.get_active_portfolio(request)
    context = get_taxes_context(request.user, portfolio_id=active_portfolio.id)
    context['all_portfolios'] = Portfolio.objects.filter(user=request.user)
    context['active_portfolio'] = active_portfolio
    return render(request, 'taxes.html', context)