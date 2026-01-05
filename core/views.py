# core/views.py

from datetime import timedelta, date, datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login
from django.utils import timezone

# --- MODELE ---
from .models import Portfolio, Transaction, Asset, AssetType, AssetSector
from .forms import UploadFileForm, CustomUserCreationForm, PortfolioSettingsForm

# --- SERWISY ---
from .services import (
    process_xtb_file, get_dashboard_context, get_dividend_context,
    get_asset_details_context
)
from .services.taxes import get_taxes_context
from .services.analytics import analyze_history, analyze_holdings
from .services.market import get_current_currency_rates, fetch_asset_metadata
from .services.news import get_asset_news
from .services.performance import PerformanceCalculator
from .services.portfolio import enrich_assets_context
from .services.actions import add_manual_transaction  # <--- NOWY IMPORT

try:
    from .services.config import fmt_2
except ImportError:
    def fmt_2(val):
        return "{:.2f}".format(val)


# --- MIXINS / SERVICES ---

class DashboardService:
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
        if range_mode == '1m':
            return today - timedelta(days=30)
        elif range_mode == '3m':
            return today - timedelta(days=90)
        elif range_mode == '6m':
            return today - timedelta(days=180)
        elif range_mode == 'ytd':
            return date(today.year, 1, 1)
        elif range_mode == '1y':
            return today - timedelta(days=365)
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
        if not transactions.exists(): return "0.00", "0.00", "0.00", "0.00", {}
        rates = get_current_currency_rates()
        eur = rates.get('EUR', 4.30);
        usd = rates.get('USD', 4.00)
        full_timeline = analyze_history(transactions, eur, usd)
        stats = analyze_holdings(transactions, eur, usd)
        current_val = stats['total_value']
        perf = PerformanceCalculator(transactions)
        metrics = perf.calculate_metrics(timeline_data=full_timeline, start_date=start_date,
                                         current_total_value=current_val)
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
    context['tile_mwr'] = mwr;
    context['tile_twr'] = twr;
    context['tile_return_pct_str'] = roi;
    context['tile_total_profit_str'] = profit
    try:
        context['tile_total_profit_raw'] = float(profit); context['tile_return_pct_raw'] = float(roi)
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
    if 'error' in context: return render(request, 'dashboard.html', {'error': context['error']})
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
    transactions = Transaction.objects.filter(portfolio=active_portfolio)
    mwr, twr, roi, profit, _ = DashboardService.calculate_performance_metrics(transactions, start_date)
    context['tile_mwr'] = mwr;
    context['tile_twr'] = twr;
    context['tile_return_pct_str'] = roi;
    context['tile_total_profit_str'] = profit
    try:
        context['tile_total_profit_raw'] = float(profit); context['tile_return_pct_raw'] = float(roi)
    except:
        pass
    rates = get_current_currency_rates()
    eur = rates.get('EUR', 4.30);
    usd = rates.get('USD', 4.00)
    dynamic_stats = analyze_holdings(transactions, eur, usd, start_date=start_date)
    enrich_assets_context(context, dynamic_stats['assets'], dynamic_stats['total_value'])
    if 'error' in context: return render(request, 'dashboard.html', {'error': context['error']})
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
        return render(request, 'dashboard.html',
                      {'error': context['error'], 'all_portfolios': Portfolio.objects.filter(user=request.user),
                       'active_portfolio': active_portfolio})
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
    return render(request, 'upload.html', {'form': form, 'all_portfolios': Portfolio.objects.filter(user=request.user),
                                           'active_portfolio': active_portfolio})


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
        name = request.POST.get('name');
        p_type = request.POST.get('type')
        if name and p_type:
            p = Portfolio.objects.create(user=request.user, name=name, portfolio_type=p_type)
            request.session['active_portfolio_id'] = p.id;
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


@login_required
def portfolio_settings_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)

    if request.method == 'POST':
        # A. MANUAL ADD - DELEGACJA DO SERWISU
        if 'manual_add' in request.POST:
            try:
                # Przygotowanie danych dla serwisu
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

                # Wywołanie logiki biznesowej
                msg = add_manual_transaction(active_portfolio, data)
                messages.success(request, msg)
                return redirect('portfolio_settings')

            except ValueError as e:
                messages.error(request, str(e))  # Błędy walidacji
                return redirect('portfolio_settings')
            except Exception as e:
                messages.error(request, f"System error: {e}")
                return redirect('portfolio_settings')

        # B. SAVE SETTINGS
        elif 'save_settings' in request.POST:
            form = PortfolioSettingsForm(request.POST, instance=active_portfolio)
            if form.is_valid():
                form.save()
                messages.success(request, "Portfolio settings updated successfully.")
                return redirect('portfolio_settings')

        # C. CLEAR / DELETE
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

    context = {
        'form': form,
        'active_portfolio': active_portfolio,
        'all_portfolios': Portfolio.objects.filter(user=request.user)
    }
    return render(request, 'portfolio_settings.html', context)


@login_required
def manage_assets_view(request):
    active_portfolio = DashboardService.get_active_portfolio(request)

    if request.method == 'POST':
        # --- LOGIKA 1: ZAPIS RĘCZNY (To co już masz) ---
        if 'save_changes' in request.POST:
            try:
                all_assets = {str(a.id): a for a in Asset.objects.all()}
                updated_count = 0
                for key, value in request.POST.items():
                    if key.startswith('asset_') and key.endswith('_name'):
                        parts = key.split('_')
                        if len(parts) == 3:
                            asset_id = parts[1]
                            if asset_id in all_assets:
                                asset = all_assets[asset_id]
                                new_name = value.strip()
                                new_sector = request.POST.get(f'asset_{asset_id}_sector')
                                new_type = request.POST.get(f'asset_{asset_id}_type')

                                changed = False
                                if asset.name != new_name: asset.name = new_name; changed = True
                                if asset.sector != new_sector: asset.sector = new_sector; changed = True
                                if asset.asset_type != new_type: asset.asset_type = new_type; changed = True

                                if changed:
                                    asset.save()
                                    updated_count += 1
                messages.success(request, f"Saved changes for {updated_count} assets.")
                return redirect('manage_assets')
            except Exception as e:
                messages.error(request, f"Error saving: {e}")

        # --- LOGIKA 2: AUTO-FILL Z YAHOO (Nowość) ---
        elif 'sync_yahoo' in request.POST:
            try:
                assets = Asset.objects.all()
                updated_count = 0
                errors = 0

                for asset in assets:
                    # Pomijamy waluty (CASH), bo Yahoo ich nie sklasyfikuje sensownie
                    if asset.symbol == 'CASH' or 'PLN' in asset.symbol and len(asset.symbol) == 3:
                        continue

                    # Pobieramy dane z Yahoo
                    ticker = asset.yahoo_ticker if asset.yahoo_ticker else asset.symbol
                    data = fetch_asset_metadata(ticker)

                    if data['success']:
                        # Aktualizujemy tylko jeśli mamy dane
                        changed = False

                        # Aktualizuj Sektor jeśli jest OTHER (nie nadpisuj ręcznych zmian na razie)
                        if asset.sector == 'OTHER' and data['sector'] != 'OTHER':
                            asset.sector = data['sector']
                            changed = True

                        # Aktualizuj Typ jeśli STOCK (domyślny) a wykryto co innego
                        if asset.asset_type == 'STOCK' and data['asset_type'] != 'STOCK':
                            asset.asset_type = data['asset_type']
                            changed = True

                        # Aktualizuj nazwę jeśli jest pusta lub to sam ticker
                        if not asset.name or asset.name == asset.symbol:
                            if data['name']:
                                asset.name = data['name']
                                changed = True

                        if changed:
                            asset.save()
                            updated_count += 1
                    else:
                        errors += 1

                messages.success(request, f"Auto-filled {updated_count} assets from Yahoo. (Errors/Skipped: {errors})")
                return redirect('manage_assets')

            except Exception as e:
                messages.error(request, f"Yahoo Sync Error: {e}")

    # GET
    assets = Asset.objects.all().order_by('symbol')
    context = {
        'assets': assets,
        'sector_choices': AssetSector.choices,
        'type_choices': AssetType.choices,
        'all_portfolios': Portfolio.objects.filter(user=request.user),
        'active_portfolio': active_portfolio
    }
    return render(request, 'manage_assets.html', context)