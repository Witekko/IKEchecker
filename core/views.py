import pandas as pd
import yfinance as yf
from django.shortcuts import render, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from .forms import UploadFileForm
from .models import Transaction, Asset, Portfolio
# Importujemy wszystkie 4 główne funkcje z services
from .services import process_xtb_file, get_dashboard_context, get_dividend_context, get_asset_news


@login_required
def upload_view(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                stats = process_xtb_file(request.FILES['file'], request.user)
                messages.success(request, f"Sukces! Dodano: {stats['added']}, Pominięto: {stats['skipped']}.")
                return redirect('/admin/core/transaction/')
            except Exception as e:
                messages.error(request, f"Błąd: {e}")
    else:
        form = UploadFileForm()
    return render(request, 'upload.html', {'form': form})


@login_required
def dashboard_view(request):
    context = get_dashboard_context(request.user)
    return render(request, 'dashboard.html', context)


@login_required
def dividends_view(request):
    context = get_dividend_context(request.user)
    return render(request, 'dividends.html', context)


@login_required
def asset_details_view(request, symbol):
    # Logika szczegółów aktywa (zostawiamy w widoku dla uproszczenia)
    portfolio = Portfolio.objects.filter(user=request.user).first()
    try:
        asset = Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return render(request, 'dashboard.html', {'error': f'Nie znaleziono: {symbol}'})

    transactions = Transaction.objects.filter(portfolio=portfolio, asset=asset).order_by('date')

    total_qty = 0.0
    total_cost_pln = 0.0
    history_table = []
    trade_events = {}  # Do oznaczania kropek na wykresie

    for t in transactions:
        qty = float(t.quantity)
        amt = float(t.amount)

        if t.type == 'BUY':
            total_qty += qty
            total_cost_pln += abs(amt)
            trade_events[t.date.date().strftime("%Y-%m-%d")] = 'BUY'
        elif t.type == 'SELL':
            if total_qty > 0:
                ratio = qty / total_qty
                if ratio > 1: ratio = 1
                total_cost_pln -= (total_cost_pln * ratio)
                total_qty -= qty
            trade_events[t.date.date().strftime("%Y-%m-%d")] = 'SELL'

        history_table.append({
            'date': t.date, 'type': t.get_type_display(), 'quantity': round(qty, 4),
            'amount': round(amt, 2), 'comment': t.comment
        })

    # Pobieranie ceny i historii (Yahoo)
    current_price = 0.0
    hist = pd.DataFrame()
    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        # Pobieramy historię od pierwszej transakcji
        start_date = transactions.first().date.date() if transactions.exists() else None
        if start_date:
            hist = ticker.history(start=start_date)
        else:
            hist = ticker.history(period="1mo")

        if not hist.empty:
            # Usuwamy strefę czasową dla spójności
            hist.index = hist.index.tz_localize(None)
            current_price = float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"Error fetching asset details: {e}")

    # Waluty
    eur_pln = 4.30
    usd_pln = 4.00
    try:
        # Szybki check walut (można by brać z services, ale tu robimy local import dla prostoty)
        e = yf.Ticker("EURPLN=X").history(period="1d")
        if not e.empty: eur_pln = float(e['Close'].iloc[-1])
        u = yf.Ticker("USDPLN=X").history(period="1d")
        if not u.empty: usd_pln = float(u['Close'].iloc[-1])
    except:
        pass

    multiplier = 1.0
    if asset.currency == 'EUR':
        multiplier = eur_pln
    elif asset.currency == 'USD':
        multiplier = usd_pln

    # Obliczenia końcowe
    avg_price = (total_cost_pln / total_qty) if total_qty > 0 else 0
    current_value_pln = (total_qty * current_price) * multiplier
    profit_pln = current_value_pln - total_cost_pln
    profit_percent = (profit_pln / total_cost_pln * 100) if total_cost_pln > 0.01 else 0

    # Przygotowanie wykresu
    chart_dates = []
    chart_prices = []
    chart_colors = []
    chart_radius = []

    if not hist.empty:
        for date_idx, row in hist.iterrows():
            d_str = date_idx.strftime("%Y-%m-%d")
            chart_dates.append(d_str)
            chart_prices.append(float(row['Close']))

            # Czy w tym dniu była transakcja?
            if d_str in trade_events:
                chart_colors.append('#00ff7f' if trade_events[d_str] == 'BUY' else '#ff4d4d')  # Zieleń/Czerwień
                chart_radius.append(6)
            else:
                chart_colors.append('rgba(0,0,0,0)')
                chart_radius.append(0)

    news_data = get_asset_news(asset.symbol, asset.name)

    context = {
        'asset': asset,
        'current_price': round(current_price, 2),
        'qty': round(total_qty, 4),
        'avg_price': round(avg_price, 2),
        'value_pln': round(current_value_pln, 2),
        'profit_pln': round(profit_pln, 2),
        'profit_percent': round(profit_percent, 2),
        'history': reversed(history_table),
        'currency_rate': round(multiplier, 2) if multiplier != 1.0 else None,
        'chart_dates': chart_dates,
        'chart_prices': chart_prices,
        'chart_colors': chart_colors,
        'chart_radius': chart_radius,
        'news_list': news_data  # <--- PRZEKAZUJEMY DO HTML
    }
    return render(request, 'asset_details.html', context)