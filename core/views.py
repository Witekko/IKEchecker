import pandas as pd
import yfinance as yf
import re
import math
from datetime import timedelta, date
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import UploadFileForm
from .models import Transaction, Asset, Portfolio

# Configuration
TICKER_CONFIG = {
    'CDR.PL': {'yahoo': 'CDR.WA', 'currency': 'PLN', 'name': 'CD Projekt'},
    'PKN.PL': {'yahoo': 'PKN.WA', 'currency': 'PLN', 'name': 'Orlen'},
    'PZU.PL': {'yahoo': 'PZU.WA', 'currency': 'PLN', 'name': 'PZU'},
    'SNT.PL': {'yahoo': 'SNT.WA', 'currency': 'PLN', 'name': 'Synektik'},
    'XTB.PL': {'yahoo': 'XTB.WA', 'currency': 'PLN', 'name': 'XTB'},
    'DIG.PL': {'yahoo': 'DIG.WA', 'currency': 'PLN', 'name': 'Digital Network'},
    'CBF.PL': {'yahoo': 'CBF.WA', 'currency': 'PLN', 'name': 'Cyber_Folks'},
    'KGH.PL': {'yahoo': 'KGH.WA', 'currency': 'PLN', 'name': 'KGHM'},
    'PKO.PL': {'yahoo': 'PKO.WA', 'currency': 'PLN', 'name': 'PKO BP'},
    'PEO.PL': {'yahoo': 'PEO.WA', 'currency': 'PLN', 'name': 'Pekao'},
    'LPP.PL': {'yahoo': 'LPP.WA', 'currency': 'PLN', 'name': 'LPP'},
    'ALE.PL': {'yahoo': 'ALE.WA', 'currency': 'PLN', 'name': 'Allegro'},
    'IS3N.DE': {'yahoo': 'IS3N.DE', 'currency': 'EUR', 'name': 'iShares MSCI EM'},
    'SXRV.DE': {'yahoo': 'SXRV.DE', 'currency': 'EUR', 'name': 'iShares NASDAQ 100'},
    'EUNL.DE': {'yahoo': 'EUNL.DE', 'currency': 'EUR', 'name': 'iShares Core MSCI World'},
    'VWCE.DE': {'yahoo': 'VWCE.DE', 'currency': 'EUR', 'name': 'Vanguard All-World'},
}


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


def process_xtb_file(uploaded_file, user):
    try:
        xls = pd.ExcelFile(uploaded_file)
    except Exception as e:
        raise ValueError(f"Invalid Excel file (.xlsx). Error: {e}")

    target_sheet_name = None
    all_sheets = xls.sheet_names
    for sheet in all_sheets:
        if "CASH" in sheet.upper():
            target_sheet_name = sheet
            break
    if not target_sheet_name: target_sheet_name = all_sheets[0]

    df_preview = pd.read_excel(uploaded_file, sheet_name=target_sheet_name, header=None, nrows=40)
    header_idx = None
    for idx, row in df_preview.iterrows():
        line_str = " ".join([str(val) for val in row.fillna('').values])
        if "ID" in line_str and "Type" in line_str and "Comment" in line_str:
            header_idx = idx
            break
    if header_idx is None: raise ValueError(f"Headers not found.")

    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, sheet_name=target_sheet_name, header=header_idx)
    df.columns = df.columns.str.strip()

    portfolio, _ = Portfolio.objects.get_or_create(user=user, defaults={'name': 'My IKE'})
    stats = {'added': 0, 'skipped': 0}

    for _, row in df.iterrows():
        if pd.isna(row.get('ID')): continue
        xtb_id = str(row['ID'])
        raw_type = str(row.get('Type', '')).lower().strip()
        trans_type = 'OTHER'

        if 'stock' in raw_type and 'purchase' in raw_type:
            trans_type = 'BUY'
        elif 'stock' in raw_type and 'sale' in raw_type:
            trans_type = 'SELL'
        elif 'close' in raw_type:
            trans_type = 'SELL'
        elif 'profit' in raw_type:
            trans_type = 'SELL'
        elif 'deposit' in raw_type:
            trans_type = 'DEPOSIT'
        elif 'withdrawal' in raw_type:
            trans_type = 'WITHDRAWAL'
        elif 'dividend' in raw_type:
            trans_type = 'DIVIDEND'
        elif 'withholding tax' in raw_type:
            trans_type = 'TAX'
        elif 'free funds' in raw_type:
            trans_type = 'OTHER'

        quantity = 0.0
        if trans_type in ['BUY', 'SELL']:
            comment = str(row.get('Comment', ''))
            match = re.search(r'(BUY|SELL) ([0-9./]+)', comment)
            if match:
                qty_str = match.group(2).split('/')[0]
                try:
                    quantity = float(qty_str)
                except:
                    quantity = 0.0

        asset_obj = None
        symbol = str(row.get('Symbol', ''))
        if pd.isna(symbol) or symbol == 'nan': symbol = ''
        if symbol in TICKER_CONFIG:
            conf = TICKER_CONFIG[symbol]
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=symbol,
                defaults={'yahoo_ticker': conf['yahoo'], 'currency': conf['currency'], 'name': conf['name']}
            )

        try:
            parsed_date = pd.to_datetime(row['Time'])
            if pd.isna(parsed_date): continue
        except:
            continue
        try:
            amount = float(row['Amount'])
        except:
            amount = 0.0

        obj, created = Transaction.objects.update_or_create(
            xtb_id=xtb_id,
            defaults={
                'portfolio': portfolio, 'asset': asset_obj, 'date': parsed_date,
                'type': trans_type, 'amount': amount, 'quantity': quantity,
                'comment': str(row.get('Comment', ''))
            }
        )
        if created:
            stats['added'] += 1
        else:
            stats['skipped'] += 1
    return stats


def asset_details_view(request, symbol):
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


def dashboard_view(request):
    portfolio = Portfolio.objects.filter(user=request.user).first()
    if not portfolio: return render(request, 'dashboard.html', {'error': 'Brak portfela.'})

    # 1. Kursy
    try:
        eur_pln = float(yf.Ticker("EURPLN=X").history(period="1d")['Close'].iloc[-1])
        usd_pln = float(yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1])
    except:
        eur_pln = 4.30; usd_pln = 4.00

    # 2. Agregacja
    assets_summary = {}
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('date')
    total_invested_cash = 0.0;
    current_cash = 0.0

    for t in transactions:
        amt = float(t.amount);
        qty = float(t.quantity)
        if t.type == 'DEPOSIT':
            total_invested_cash += amt; current_cash += amt
        elif t.type == 'WITHDRAWAL':
            total_invested_cash -= abs(amt); current_cash -= abs(amt)
        elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
            current_cash += amt

        if t.asset:
            symbol = t.asset.symbol
            if symbol not in assets_summary:
                assets_summary[symbol] = {'quantity': 0.0, 'cost_basis_pln': 0.0, 'realized_pln': 0.0, 'obj': t.asset}

            if t.type == 'BUY':
                assets_summary[symbol]['quantity'] += qty
                assets_summary[symbol]['cost_basis_pln'] += abs(amt)
            elif t.type == 'SELL':
                curr_q = assets_summary[symbol]['quantity']
                if curr_q > 0:
                    ratio = qty / curr_q;
                    if ratio > 1: ratio = 1
                    cost_rem = assets_summary[symbol]['cost_basis_pln'] * ratio
                    realized = amt - cost_rem
                    assets_summary[symbol]['realized_pln'] += realized
                    assets_summary[symbol]['quantity'] -= qty
                    assets_summary[symbol]['cost_basis_pln'] -= cost_rem

    # 3. Listy
    pln_holdings = [];
    foreign_holdings = [];
    closed_holdings = []
    portfolio_value_pln = 0.0
    chart_labels = [];
    chart_allocation = []
    chart_profit_labels = [];
    chart_profit_values = []
    closed_labels = [];
    closed_values = []

    for symbol, data in assets_summary.items():
        qty = data['quantity'];
        asset = data['obj']
        if qty <= 0.0001:
            if abs(data['realized_pln']) > 0.01:
                closed_holdings.append({'symbol': symbol, 'gain_pln': round(data['realized_pln'], 2)})
                closed_labels.append(symbol);
                closed_values.append(round(data['realized_pln'], 2))
            continue

        cost_pln = data['cost_basis_pln']
        avg_price = cost_pln / qty if qty > 0 else 0
        try:
            cur_price = float(yf.Ticker(asset.yahoo_ticker).history(period='1d')['Close'].iloc[-1])
        except:
            cur_price = 0.0
        if math.isnan(cur_price): cur_price = 0.0

        mul = 1.0;
        cur_code = 'PLN';
        t_list = pln_holdings
        if asset.currency == 'EUR':
            mul = eur_pln; cur_code = 'EUR'; t_list = foreign_holdings
        elif asset.currency == 'USD':
            mul = usd_pln; cur_code = 'USD'; t_list = foreign_holdings

        val_pln = (qty * cur_price) * mul
        tot_gain = (val_pln - cost_pln) + data['realized_pln']
        gain_pct = (tot_gain / cost_pln * 100) if cost_pln > 0 else 0

        t_list.append({
            'symbol': symbol, 'name': asset.name, 'quantity': round(qty, 4),
            'avg_price_pln': round(avg_price, 2), 'current_price_orig': round(cur_price, 2),
            'currency': cur_code, 'value_pln': round(val_pln, 2),
            'gain_pln': round(tot_gain, 2), 'gain_percent': round(gain_pct, 2)
        })
        portfolio_value_pln += val_pln
        chart_labels.append(symbol);
        chart_allocation.append(val_pln)
        chart_profit_labels.append(symbol);
        chart_profit_values.append(tot_gain)

    if current_cash > 1: chart_labels.append("GOTÓWKA"); chart_allocation.append(current_cash)

    total_account_value = portfolio_value_pln + current_cash
    profit_total = total_account_value - total_invested_cash

    # 4. BENCHMARK SIMULATION
    timeline_dates = [];
    timeline_deposit_points = []  # <--- PRZYWRÓCONA TABLICA PUNKTÓW

    # Dane PLN
    timeline_total_value = [];
    timeline_invested = []
    timeline_wig = [];
    timeline_sp500 = [];
    timeline_inflation = []
    # Dane %
    timeline_pct_user = [];
    timeline_pct_wig = [];
    timeline_pct_sp500 = [];
    timeline_pct_inflation = []

    if transactions.exists():
        start_date = transactions.first().date.date()
        end_date = date.today()
        user_tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))
        benchmarks = ['^WIG', '^GSPC', 'USDPLN=X']
        all_tickers_to_fetch = list(set(user_tickers + benchmarks))

        try:
            hist_data = yf.download(all_tickers_to_fetch, start=start_date, end=end_date + timedelta(days=1),
                                    group_by='ticker', progress=False)
        except:
            hist_data = pd.DataFrame()

        sim_cash = 0.0;
        sim_invested = 0.0;
        sim_holdings = {}
        bench_wig_units = 0.0;
        bench_sp500_units = 0.0;
        bench_inflation_capital = 0.0

        all_trans_list = list(transactions)
        trans_idx = 0;
        total_trans = len(all_trans_list)
        current_day = start_date

        while current_day <= end_date:
            day_deposit_occured = False  # <--- Flaga wpłaty
            while trans_idx < total_trans and all_trans_list[trans_idx].date.date() <= current_day:
                t = all_trans_list[trans_idx]
                amt = float(t.amount);
                qty = float(t.quantity)

                if t.type == 'DEPOSIT':
                    sim_cash += amt;
                    sim_invested += amt
                    day_deposit_occured = True  # <--- Zaznaczamy wpłatę
                    try:
                        wig_price = float(hist_data['^WIG']['Close'].asof(str(current_day)))
                        if wig_price > 0: bench_wig_units += amt / wig_price
                    except:
                        pass
                    try:
                        usd_rate = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                        sp500_price = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
                        if usd_rate > 0 and sp500_price > 0: bench_sp500_units += (amt / usd_rate) / sp500_price
                    except:
                        pass
                    bench_inflation_capital += amt
                elif t.type == 'WITHDRAWAL':
                    sim_cash -= abs(amt);
                    sim_invested -= abs(amt);
                    bench_inflation_capital -= abs(amt)
                elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                    sim_cash += amt

                if t.asset:
                    tick = t.asset.yahoo_ticker
                    if t.type == 'BUY':
                        sim_holdings[tick] = sim_holdings.get(tick, 0.0) + qty
                    elif t.type == 'SELL':
                        sim_holdings[tick] = sim_holdings.get(tick, 0.0) - qty
                trans_idx += 1

            user_val = sim_cash
            for ticker, quantity in sim_holdings.items():
                if quantity <= 0.0001: continue
                try:
                    price = float(hist_data[ticker]['Close'].asof(str(current_day)))
                    if math.isnan(price): price = 0.0
                    val = price * quantity
                    if '.DE' in ticker:
                        val *= eur_pln
                    elif '.US' in ticker:
                        u_rate = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                        if not math.isnan(u_rate):
                            val *= u_rate
                        else:
                            val *= usd_pln
                    user_val += val
                except:
                    pass

            wig_val = 0.0
            try:
                w_p = float(hist_data['^WIG']['Close'].asof(str(current_day)))
                if not math.isnan(w_p): wig_val = bench_wig_units * w_p
            except:
                pass

            sp500_val_pln = 0.0
            try:
                sp_p = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
                u_r = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                if not math.isnan(sp_p) and not math.isnan(u_r): sp500_val_pln = bench_sp500_units * sp_p * u_r
            except:
                pass

            daily_rate = 1.06 ** (1 / 365)
            bench_inflation_capital *= daily_rate

            timeline_dates.append(current_day.strftime("%Y-%m-%d"))
            timeline_total_value.append(round(user_val, 2))
            timeline_invested.append(round(sim_invested, 2))
            timeline_wig.append(round(wig_val, 2) if wig_val > 0 else round(sim_invested, 2))
            timeline_sp500.append(round(sp500_val_pln, 2) if sp500_val_pln > 0 else round(sim_invested, 2))
            timeline_inflation.append(round(bench_inflation_capital, 2))

            # Dodajemy logikę kropek: 6 jeśli wpłata, 0 jeśli nie
            timeline_deposit_points.append(6 if day_deposit_occured else 0)

            base = sim_invested if sim_invested > 0 else 1.0
            timeline_pct_user.append(round((user_val - sim_invested) / base * 100, 2))
            timeline_pct_wig.append(round((wig_val - sim_invested) / base * 100 if wig_val > 0 else 0, 2))
            timeline_pct_sp500.append(round((sp500_val_pln - sim_invested) / base * 100 if sp500_val_pln > 0 else 0, 2))
            timeline_pct_inflation.append(round((bench_inflation_capital - sim_invested) / base * 100, 2))

            current_day += timedelta(days=1)

    context = {
        'cash': round(current_cash, 2), 'invested': round(total_invested_cash, 2),
        'stock_value': round(portfolio_value_pln, 2), 'total_value': round(total_account_value, 2),
        'profit': round(profit_total, 2),
        'pln_holdings': pln_holdings, 'foreign_holdings': foreign_holdings, 'closed_holdings': closed_holdings,
        'eur_rate': round(eur_pln, 2), 'usd_rate': round(usd_pln, 2),
        'chart_labels': chart_labels, 'chart_allocation': chart_allocation,
        'chart_profit_labels': chart_profit_labels, 'chart_profit_values': chart_profit_values,
        'closed_labels': closed_labels, 'closed_values': closed_values,

        'timeline_dates': timeline_dates,
        'timeline_total_value': timeline_total_value,
        'timeline_invested': timeline_invested,
        'timeline_wig': timeline_wig,
        'timeline_sp500': timeline_sp500,
        'timeline_inflation': timeline_inflation,
        'timeline_deposit_points': timeline_deposit_points,  # <--- PRZEKAZANIE DO TEMPLATE

        'timeline_pct_user': timeline_pct_user,
        'timeline_pct_wig': timeline_pct_wig,
        'timeline_pct_sp500': timeline_pct_sp500,
        'timeline_pct_inflation': timeline_pct_inflation,
    }
    return render(request, 'dashboard.html', context)