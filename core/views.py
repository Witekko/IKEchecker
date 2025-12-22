import pandas as pd
import yfinance as yf
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import UploadFileForm
from .models import Transaction, Asset, Portfolio
from .services import process_xtb_file, get_dashboard_context  # <--- IMPORTUJEMY Z SERVICES


def upload_view(request):
    if request.method == 'POST':
        form = UploadFileForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                stats = process_xtb_file(request.FILES['file'], request.user)
                messages.success(request,
                                 f"Success! Added {stats['added']} operations. Updated/Skipped {stats['skipped']}.")
                return redirect('/admin/core/transaction/')
            except Exception as e:
                messages.error(request, f"Error: {e}")
    else:
        form = UploadFileForm()
    return render(request, 'upload.html', {'form': form})


def dashboard_view(request):
    # Cała logika jest teraz w services.py
    context = get_dashboard_context(request.user)
    return render(request, 'dashboard.html', context)


def asset_details_view(request, symbol):
    # Też można by przenieść, ale na razie zostawmy, bo jest dość krótki
    # Jeśli chcesz być super czysty, przenieś to też do services.py
    # Ale w ramach tej fazy skupiliśmy się na Dashboardzie.

    portfolio = Portfolio.objects.filter(user=request.user).first()
    try:
        asset = Asset.objects.get(symbol=symbol)
    except Asset.DoesNotExist:
        return render(request, 'dashboard.html', {'error': f'Nie znaleziono: {symbol}'})

    transactions = Transaction.objects.filter(portfolio=portfolio, asset=asset).order_by('date')
    if not transactions.exists(): return render(request, 'dashboard.html', {'error': f'Brak transakcji: {symbol}'})

    total_qty = 0.0;
    total_cost_pln = 0.0
    history_table = [];
    trade_events = {}

    for t in transactions:
        qty = float(t.quantity);
        amt = float(t.amount)
        if t.type == 'BUY':
            total_qty += qty;
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

    current_price = 0.0;
    hist = pd.DataFrame()
    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        start_date = transactions.first().date.date()
        hist = ticker.history(start=start_date)
        if not hist.empty:
            hist.index = hist.index.tz_localize(None)
            current_price = float(hist['Close'].iloc[-1])
        else:
            hist = ticker.history(period="5d")
            if not hist.empty: current_price = float(hist['Close'].iloc[-1])
    except:
        current_price = 0.0

    eur_pln = 4.30;
    usd_pln = 4.00
    try:
        e = yf.Ticker("EURPLN=X").history(period="1d");
        if not e.empty: eur_pln = float(e['Close'].iloc[-1])
        u = yf.Ticker("USDPLN=X").history(period="1d");
        if not u.empty: usd_pln = float(u['Close'].iloc[-1])
    except:
        pass

    multiplier = 1.0
    if asset.currency == 'EUR':
        multiplier = eur_pln
    elif asset.currency == 'USD':
        multiplier = usd_pln

    avg_price = (total_cost_pln / total_qty) if total_qty > 0 else 0
    current_value_pln = (total_qty * current_price) * multiplier
    profit_pln = current_value_pln - total_cost_pln
    profit_percent = (profit_pln / total_cost_pln * 100) if total_cost_pln > 0.01 else 0

    chart_dates = [];
    chart_prices = [];
    chart_colors = [];
    chart_radius = []
    if not hist.empty:
        for date_idx, row in hist.iterrows():
            d_str = date_idx.strftime("%Y-%m-%d")
            chart_dates.append(d_str)
            chart_prices.append(float(row['Close']))
            if d_str in trade_events:
                chart_colors.append('#198754' if trade_events[d_str] == 'BUY' else '#dc3545')
                chart_radius.append(6)
            else:
                chart_colors.append('rgba(0,0,0,0)')
                chart_radius.append(0)

    context = {
        'asset': asset, 'current_price': round(current_price, 2), 'qty': round(total_qty, 4),
        'avg_price': round(avg_price, 2), 'value_pln': round(current_value_pln, 2),
        'profit_pln': round(profit_pln, 2), 'profit_percent': round(profit_percent, 2),
        'history': reversed(history_table), 'currency_rate': round(multiplier, 2) if multiplier != 1.0 else None,
        'chart_dates': chart_dates, 'chart_prices': chart_prices, 'chart_colors': chart_colors,
        'chart_radius': chart_radius,
    }
    return render(request, 'asset_details.html', context)