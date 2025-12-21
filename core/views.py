import pandas as pd
import re
from django.shortcuts import render, redirect
from django.contrib import messages
from .forms import UploadFileForm
from .models import Transaction, Asset, Portfolio
import yfinance as yf
from django.db.models import Sum

# Configuration: XTB Symbol -> Yahoo Symbol + Currency + Name
TICKER_CONFIG = {
    # Polish Stocks
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
    # Foreign (ETF)
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
    # STEP 1: Open Excel and find the CASH sheet
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

    if not target_sheet_name:
        target_sheet_name = all_sheets[0]

        # STEP 2: Find the header row
    df_preview = pd.read_excel(uploaded_file, sheet_name=target_sheet_name, header=None, nrows=40)

    header_idx = None
    for idx, row in df_preview.iterrows():
        line_str = " ".join([str(val) for val in row.fillna('').values])
        if "ID" in line_str and "Type" in line_str and "Comment" in line_str:
            header_idx = idx
            break

    if header_idx is None:
        raise ValueError(f"Headers (ID, Type, Comment) not found in sheet '{target_sheet_name}'.")

    # STEP 3: Load actual data
    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, sheet_name=target_sheet_name, header=header_idx)
    df.columns = df.columns.str.strip()

    # STEP 4: Import to DB
    portfolio, _ = Portfolio.objects.get_or_create(user=user, defaults={'name': 'My IKE'})
    stats = {'added': 0, 'skipped': 0}

    print("--- ROZPOCZYNAM ANALIZĘ PLIKU (DEBUG) ---")

    for _, row in df.iterrows():
        if pd.isna(row.get('ID')): continue

        xtb_id = str(row['ID'])

        # --- LOGIKA TYPÓW (CASE INSENSITIVE + STRIP) ---
        raw_type_original = str(row.get('Type', ''))
        raw_type = raw_type_original.lower().strip()

        trans_type = 'OTHER'

        # 1. KUPNO
        if 'stock' in raw_type and 'purchase' in raw_type:
            trans_type = 'BUY'

        # 2. SPRZEDAŻ (Zwrot kapitału) - "Stock sale" lub "Stocks sale"
        elif 'stock' in raw_type and 'sale' in raw_type:
            trans_type = 'SELL'

        # 3. ZYSK ZE SPRZEDAŻY - "Close trade" lub "Profit"
        elif 'close' in raw_type:
            trans_type = 'SELL'
        elif 'profit' in raw_type:
            trans_type = 'SELL'

        # 4. INNE WPŁATY
        elif 'deposit' in raw_type:
            trans_type = 'DEPOSIT'
        elif 'dividend' in raw_type:
            trans_type = 'DIVIDEND'
        elif 'free funds' in raw_type:
            trans_type = 'OTHER'  # Odsetki

        # --- DEBUGGER: Jeśli nadal OTHER, pokaż dlaczego ---
        if trans_type == 'OTHER':
            print(f"[DEBUG] OTHER DETECTED -> ID: {xtb_id} | Type: '{raw_type_original}'")

        # Quantity parsing
        quantity = 0.0
        if trans_type in ['BUY', 'SELL']:
            comment = str(row.get('Comment', ''))
            match = re.search(r'(BUY|SELL) ([0-9./]+)', comment)
            if match:
                qty_str = match.group(2)
                if '/' in qty_str: qty_str = qty_str.split('/')[0]
                try:
                    quantity = float(qty_str)
                except:
                    quantity = 0.0

        # Symbol parsing
        asset_obj = None
        symbol = str(row.get('Symbol', ''))
        if pd.isna(symbol) or symbol == 'nan': symbol = ''

        if symbol in TICKER_CONFIG:
            conf = TICKER_CONFIG[symbol]
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=symbol,
                defaults={'yahoo_ticker': conf['yahoo'], 'currency': conf['currency'], 'name': conf['name']}
            )

        # Date parsing
        try:
            parsed_date = pd.to_datetime(row['Time'])
            if pd.isna(parsed_date): continue
        except:
            continue

        # Amount parsing
        try:
            amount = float(row['Amount'])
        except:
            amount = 0.0

        # Update or Create
        obj, created = Transaction.objects.update_or_create(
            xtb_id=xtb_id,
            defaults={
                'portfolio': portfolio,
                'asset': asset_obj,
                'date': parsed_date,
                'type': trans_type,
                'amount': amount,
                'quantity': quantity,
                'comment': str(row.get('Comment', ''))
            }
        )

        if created:
            stats['added'] += 1
        else:
            stats['skipped'] += 1

    print("--- KONIEC ANALIZY ---")
    return stats


# --- Pamiętaj o imporcie math na górze pliku, jeśli go nie ma ---
import math


# (ale w views.py masz już importy, więc po prostu upewnij się, że yfinance i pandas są)

# --- WKLEJ TO NA DOLE PLIKU core/views.py (Zastąp obecną funkcję dashboard_view) ---

def dashboard_view(request):
    portfolio = Portfolio.objects.filter(user=request.user).first()
    if not portfolio:
        return render(request, 'dashboard.html', {'error': 'Brak portfela. Wgraj plik Excel.'})

    # 1. Pobieramy kursy walut (Live)
    try:
        # Wymuszamy float, bo yfinance zwraca numpy.float
        eur_pln = float(yf.Ticker("EURPLN=X").history(period="1d")['Close'].iloc[-1])
        usd_pln = float(yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1])
    except:
        eur_pln = 4.30
        usd_pln = 4.00

    # 2. Agregacja danych
    assets_summary = {}
    transactions = Transaction.objects.filter(portfolio=portfolio)

    total_invested_cash = 0.0
    current_cash = 0.0

    for t in transactions:
        # Konwersja Decimal na float dla bezpieczeństwa obliczeń
        amt = float(t.amount)
        qty = float(t.quantity)

        # Gotówka
        if t.type == 'DEPOSIT':
            total_invested_cash += amt
            current_cash += amt
        elif t.type == 'WITHDRAWAL':
            total_invested_cash -= abs(amt)
            current_cash -= abs(amt)
        elif t.type == 'BUY':
            current_cash += amt
        elif t.type == 'SELL':
            current_cash += amt
        elif t.type == 'DIVIDEND':
            current_cash += amt

        # Akcje
        if t.asset:
            symbol = t.asset.symbol
            if symbol not in assets_summary:
                assets_summary[symbol] = {
                    'quantity': 0.0,
                    'cost_basis_pln': 0.0,
                    'obj': t.asset
                }

            if t.type == 'BUY':
                assets_summary[symbol]['quantity'] += qty
                assets_summary[symbol]['cost_basis_pln'] += abs(amt)
            elif t.type == 'SELL':
                current_qty = assets_summary[symbol]['quantity']
                if current_qty > 0:
                    ratio = qty / current_qty
                    if ratio > 1: ratio = 1
                    cost_to_remove = assets_summary[symbol]['cost_basis_pln'] * ratio
                    assets_summary[symbol]['quantity'] -= qty
                    assets_summary[symbol]['cost_basis_pln'] -= cost_to_remove

    # 3. Rozdzielenie na Polskę i Zagranicę + DANE DO WYKRESÓW
    pln_holdings = []
    foreign_holdings = []
    portfolio_value_pln = 0.0

    # Listy pod wykresy (CZYSTE FLOATY)
    chart_labels = []
    chart_allocation = []
    chart_profit_labels = []
    chart_profit_values = []

    for symbol, data in assets_summary.items():
        qty = data['quantity']
        if qty <= 0.0001: continue

        asset = data['obj']
        cost_pln = data['cost_basis_pln']
        avg_price_pln = cost_pln / qty if qty > 0 else 0

        try:
            # Wymuszamy float, na wypadek gdyby to był numpy.float64
            current_price_original = float(yf.Ticker(asset.yahoo_ticker).history(period='1d')['Close'].iloc[-1])
        except:
            current_price_original = 0.0

        if pd.isna(current_price_original): current_price_original = 0.0

        if asset.currency == 'EUR':
            current_val_pln = (qty * current_price_original) * eur_pln
            holding_list = foreign_holdings
            display_currency = 'EUR'
        elif asset.currency == 'USD':
            current_val_pln = (qty * current_price_original) * usd_pln
            holding_list = foreign_holdings
            display_currency = 'USD'
        else:
            current_val_pln = qty * current_price_original
            holding_list = pln_holdings
            display_currency = 'PLN'

        gain_pln = current_val_pln - cost_pln
        gain_percent = (gain_pln / cost_pln * 100) if cost_pln > 0 else 0.0

        item_data = {
            'symbol': symbol,
            'name': asset.name,
            'quantity': round(qty, 4),
            'avg_price_pln': round(avg_price_pln, 2),
            'current_price_orig': round(current_price_original, 2),
            'currency': display_currency,
            'value_pln': round(current_val_pln, 2),
            'gain_pln': round(gain_pln, 2),
            'gain_percent': round(gain_percent, 2)
        }
        holding_list.append(item_data)
        portfolio_value_pln += current_val_pln

        # ZASILANIE WYKRESÓW (Hard Cast to float)
        chart_labels.append(str(symbol))
        chart_allocation.append(float(round(current_val_pln, 2)))

        chart_profit_labels.append(str(symbol))
        chart_profit_values.append(float(round(gain_pln, 2)))

    # Dodajemy Gotówkę do wykresu
    if current_cash > 1:
        chart_labels.append("GOTÓWKA")
        chart_allocation.append(float(round(current_cash, 2)))

    total_account_value = portfolio_value_pln + current_cash
    profit_total = total_account_value - total_invested_cash

    context = {
        'cash': round(current_cash, 2),
        'invested': round(total_invested_cash, 2),
        'stock_value': round(portfolio_value_pln, 2),
        'total_value': round(total_account_value, 2),
        'profit': round(profit_total, 2),
        'pln_holdings': pln_holdings,
        'foreign_holdings': foreign_holdings,
        'eur_rate': round(eur_pln, 2),
        'usd_rate': round(usd_pln, 2),
        # Dane bezpieczne dla JS
        'chart_labels': chart_labels,
        'chart_allocation': chart_allocation,
        'chart_profit_labels': chart_profit_labels,
        'chart_profit_values': chart_profit_values,
    }

    return render(request, 'dashboard.html', context)