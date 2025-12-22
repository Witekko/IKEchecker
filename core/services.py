import pandas as pd
import yfinance as yf
import re
import math
from datetime import timedelta, date
from django.utils import timezone  # Do obsługi czasu
from .models import Transaction, Asset, Portfolio

# --- KONFIGURACJA ---
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


# --- POMOCNIK: POBIERANIE CENY Z CACHE (Reguła 15 min) ---
def get_cached_price(asset):
    now = timezone.now()

    # 1. Sprawdź czy cena jest w miarę świeża (np. młodsza niż 15 min)
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:  # 900 sekund = 15 minut
            return float(asset.last_price)

    # 2. Jeśli stara lub brak -> Pobierz z Yahoo
    try:
        # Pobieramy 1 dzień, żeby mieć pewność ostatniego zamknięcia
        ticker = yf.Ticker(asset.yahoo_ticker)
        data = ticker.history(period='1d')

        if not data.empty:
            price = float(data['Close'].iloc[-1])

            # Zapisz do bazy na przyszłość
            asset.last_price = price
            asset.last_updated = now
            asset.save()  # Zapis w DB

            return price
    except Exception as e:
        print(f"Błąd pobierania ceny dla {asset.symbol}: {e}")

    # 3. Fallback: Jeśli Yahoo padło, zwróć starą cenę (lepsza stara niż 0)
    return float(asset.last_price)


# --- LOGIKA IMPORTERA ---
def process_xtb_file(uploaded_file, user):
    try:
        xls = pd.ExcelFile(uploaded_file)
    except Exception as e:
        raise ValueError(f"Invalid Excel file: {e}")

    target_sheet = None
    for sheet in xls.sheet_names:
        if "CASH" in sheet.upper():
            target_sheet = sheet
            break
    if not target_sheet: target_sheet = xls.sheet_names[0]

    df_preview = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=None, nrows=40)
    header_idx = None
    for idx, row in df_preview.iterrows():
        s = " ".join([str(v) for v in row.fillna('').values])
        if "ID" in s and "Type" in s and "Comment" in s:
            header_idx = idx;
            break
    if header_idx is None: raise ValueError("Headers not found.")

    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=header_idx)
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
            c = str(row.get('Comment', ''))
            m = re.search(r'(BUY|SELL) ([0-9./]+)', c)
            if m:
                try:
                    quantity = float(m.group(2).split('/')[0])
                except:
                    quantity = 0.0

        asset_obj = None
        sym = str(row.get('Symbol', ''))
        if pd.isna(sym) or sym == 'nan': sym = ''
        if sym in TICKER_CONFIG:
            conf = TICKER_CONFIG[sym]
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=sym,
                defaults={'yahoo_ticker': conf['yahoo'], 'currency': conf['currency'], 'name': conf['name']}
            )

        try:
            d = pd.to_datetime(row['Time'])
        except:
            continue
        try:
            amt = float(row['Amount'])
        except:
            amt = 0.0

        _, created = Transaction.objects.update_or_create(
            xtb_id=xtb_id,
            defaults={'portfolio': portfolio, 'asset': asset_obj, 'date': d, 'type': trans_type, 'amount': amt,
                      'quantity': quantity, 'comment': str(row.get('Comment', ''))}
        )
        if created:
            stats['added'] += 1
        else:
            stats['skipped'] += 1
    return stats


# --- LOGIKA DASHBOARDU ---
def get_dashboard_context(user):
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {'error': 'Brak portfela.'}

    # 1. Waluty (Też można by cache'ować, ale tu zostawmy na razie simple live dla walut)
    try:
        eur_pln = float(yf.Ticker("EURPLN=X").history(period="1d")['Close'].iloc[-1])
        usd_pln = float(yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1])
    except:
        eur_pln = 4.30; usd_pln = 4.00

    assets_summary = {}
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('date')
    total_invested = 0.0;
    cash = 0.0

    for t in transactions:
        amt = float(t.amount);
        qty = float(t.quantity)
        if t.type == 'DEPOSIT':
            total_invested += amt; cash += amt
        elif t.type == 'WITHDRAWAL':
            total_invested -= abs(amt); cash -= abs(amt)
        elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
            cash += amt

        if t.asset:
            s = t.asset.symbol
            if s not in assets_summary: assets_summary[s] = {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'obj': t.asset}
            if t.type == 'BUY':
                assets_summary[s]['qty'] += qty
                assets_summary[s]['cost'] += abs(amt)
            elif t.type == 'SELL':
                cur_q = assets_summary[s]['qty']
                if cur_q > 0:
                    r = qty / cur_q;
                    if r > 1: r = 1
                    c_rem = assets_summary[s]['cost'] * r
                    assets_summary[s]['realized'] += (amt - c_rem)
                    assets_summary[s]['qty'] -= qty
                    assets_summary[s]['cost'] -= c_rem

    pln_h = [];
    for_h = [];
    clo_h = []
    val_pln = 0.0
    c_lbl = [];
    c_all = [];
    c_pl = [];
    c_pv = [];
    cl_l = [];
    cl_v = []

    for s, data in assets_summary.items():
        qty = data['qty'];
        asset = data['obj']
        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                clo_h.append({'symbol': s, 'gain_pln': round(data['realized'], 2)})
                cl_l.append(s);
                cl_v.append(round(data['realized'], 2))
            continue

        cost = data['cost']
        avg_p = cost / qty if qty > 0 else 0

        # --- TU UŻYWAMY NOWEGO CACHE (Zamiast yf.Ticker bezpośrednio) ---
        cur_price = get_cached_price(asset)
        # ----------------------------------------------------------------

        mul = 1.0;
        code = 'PLN';
        t_list = pln_h
        if asset.currency == 'EUR':
            mul = eur_pln; code = 'EUR'; t_list = for_h
        elif asset.currency == 'USD':
            mul = usd_pln; code = 'USD'; t_list = for_h

        v_pln = (qty * cur_price) * mul
        gain = (v_pln - cost) + data['realized']
        g_pct = (gain / cost * 100) if cost > 0 else 0

        t_list.append({
            'symbol': s, 'name': asset.name, 'quantity': round(qty, 4),
            'avg_price_pln': round(avg_p, 2), 'current_price_orig': round(cur_price, 2),
            'currency': code, 'value_pln': round(v_pln, 2),
            'gain_pln': round(gain, 2), 'gain_percent': round(g_pct, 2)
        })
        val_pln += v_pln
        c_lbl.append(s);
        c_all.append(v_pln);
        c_pl.append(s);
        c_pv.append(gain)

    if cash > 1: c_lbl.append("GOTÓWKA"); c_all.append(cash)

    total_val = val_pln + cash
    prof_tot = total_val - total_invested

    # --- WEHIKUŁ CZASU (Cache'owanie tu jest trudniejsze, bo to bulk download) ---
    # Na razie zostawiamy yf.download, bo pobiera dane hurtem i jest szybki.
    # W przyszłości można to też zoptymalizować.

    t_dates = [];
    t_pts = []
    t_tot = [];
    t_inv = [];
    t_wig = [];
    t_sp500 = [];
    t_inf = []
    p_usr = [];
    p_wig = [];
    p_sp500 = [];
    p_inf = []

    if transactions.exists():
        start = transactions.first().date.date()
        end = date.today()
        tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))
        bench = ['^WIG', '^GSPC', 'USDPLN=X']

        # Używamy download z opcją threads=True dla szybkości
        try:
            h_data = yf.download(list(set(tickers + bench)), start=start, end=end + timedelta(days=1),
                                 group_by='ticker', progress=False, threads=True)
        except:
            h_data = pd.DataFrame()

        sim_c = 0.0;
        sim_i = 0.0;
        sim_h = {}
        b_wig = 0.0;
        b_sp = 0.0;
        b_inf = 0.0

        trans_list = list(transactions)
        idx = 0;
        count = len(trans_list)
        cur = start

        while cur <= end:
            dep = False
            while idx < count and trans_list[idx].date.date() <= cur:
                t = trans_list[idx]
                a = float(t.amount);
                q = float(t.quantity)
                if t.type == 'DEPOSIT':
                    sim_c += a;
                    sim_i += a;
                    dep = True
                    try:
                        wp = float(h_data['^WIG']['Close'].asof(str(cur)))
                        if wp > 0: b_wig += a / wp
                    except:
                        pass
                    try:
                        ur = float(h_data['USDPLN=X']['Close'].asof(str(cur)))
                        sp = float(h_data['^GSPC']['Close'].asof(str(cur)))
                        if ur > 0 and sp > 0: b_sp += (a / ur) / sp
                    except:
                        pass
                    b_inf += a
                elif t.type == 'WITHDRAWAL':
                    sim_c -= abs(a);
                    sim_i -= abs(a);
                    b_inf -= abs(a)
                elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                    sim_c += a

                if t.asset:
                    tk = t.asset.yahoo_ticker
                    if t.type == 'BUY':
                        sim_h[tk] = sim_h.get(tk, 0.0) + q
                    elif t.type == 'SELL':
                        sim_h[tk] = sim_h.get(tk, 0.0) - q
                idx += 1

            u_val = sim_c
            for tk, q in sim_h.items():
                if q <= 0.0001: continue
                try:
                    p = float(h_data[tk]['Close'].asof(str(cur)))
                    if math.isnan(p): p = 0.0
                    v = p * q
                    if '.DE' in tk:
                        v *= eur_pln
                    elif '.US' in tk:
                        ur = float(h_data['USDPLN=X']['Close'].asof(str(cur)))
                        if not math.isnan(ur):
                            v *= ur
                        else:
                            v *= usd_pln
                    u_val += v
                except:
                    pass

            w_val = 0.0
            try:
                p = float(h_data['^WIG']['Close'].asof(str(cur)))
                if not math.isnan(p): w_val = b_wig * p
            except:
                pass

            sp_val = 0.0
            try:
                p = float(h_data['^GSPC']['Close'].asof(str(cur)))
                ur = float(h_data['USDPLN=X']['Close'].asof(str(cur)))
                if not math.isnan(p) and not math.isnan(ur): sp_val = b_sp * p * ur
            except:
                pass

            b_inf *= (1.06 ** (1 / 365))

            t_dates.append(cur.strftime("%Y-%m-%d"))
            t_tot.append(round(u_val, 2))
            t_inv.append(round(sim_i, 2))
            t_wig.append(round(w_val, 2) if w_val > 0 else round(sim_i, 2))
            t_sp500.append(round(sp_val, 2) if sp_val > 0 else round(sim_i, 2))
            t_inf.append(round(b_inf, 2))
            t_pts.append(6 if dep else 0)

            base = sim_i if sim_i > 0 else 1.0
            p_usr.append(round((u_val - sim_i) / base * 100, 2))
            p_wig.append(round((w_val - sim_i) / base * 100 if w_val > 0 else 0, 2))
            p_sp500.append(round((sp_val - sim_i) / base * 100 if sp_val > 0 else 0, 2))
            p_inf.append(round((b_inf - sim_i) / base * 100, 2))

            cur += timedelta(days=1)

    return {
        'cash': round(cash, 2), 'invested': round(total_invested, 2),
        'stock_value': round(val_pln, 2), 'total_value': round(total_val, 2),
        'profit': round(prof_tot, 2),
        'pln_holdings': pln_h, 'foreign_holdings': for_h, 'closed_holdings': clo_h,
        'eur_rate': round(eur_pln, 2), 'usd_rate': round(usd_pln, 2),
        'chart_labels': c_lbl, 'chart_allocation': c_all,
        'chart_profit_labels': c_pl, 'chart_profit_values': c_pv,
        'closed_labels': cl_l, 'closed_values': cl_v,
        'timeline_dates': t_dates, 'timeline_total_value': t_tot, 'timeline_invested': t_inv,
        'timeline_wig': t_wig, 'timeline_sp500': t_sp500, 'timeline_inflation': t_inf,
        'timeline_deposit_points': t_pts,
        'timeline_pct_user': p_usr, 'timeline_pct_wig': p_wig,
        'timeline_pct_sp500': p_sp500, 'timeline_pct_inflation': p_inf,
    }