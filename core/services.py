import pandas as pd
import yfinance as yf
import re
import math
import difflib
import feedparser
import urllib.parse
from datetime import timedelta, date
from django.utils import timezone
from django.db.models import QuerySet
from .models import Transaction, Asset, Portfolio


# =============================================================================
# HELPERS (Formatowanie liczb)
# =============================================================================

def fmt_2(value):
    """Ceny i Procenty: Zawsze 2 miejsca po przecinku, kropka (np. 10.00, 0.50)"""
    if value is None: return "0.00"
    return f"{float(value):.2f}"


def fmt_4(value):
    """Ilość (Walory): Zawsze 4 miejsca po przecinku (np. 1.0000, 0.1234)"""
    if value is None: return "0.0000"
    return f"{float(value):.4f}"


# =============================================================================
# MODUŁ 1: KONFIGURACJA
# =============================================================================

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


# =============================================================================
# MODUŁ 2: MARKET SERVICE
# =============================================================================

def get_current_currency_rates():
    try:
        eur = float(yf.Ticker("EURPLN=X").history(period="1d")['Close'].iloc[-1])
        usd = float(yf.Ticker("USDPLN=X").history(period="1d")['Close'].iloc[-1])
    except:
        eur, usd = 4.30, 4.00
    return round(eur, 2), round(usd, 2)


def get_cached_price(asset: Asset):
    now = timezone.now()
    if asset.last_updated and asset.last_price > 0:
        diff = now - asset.last_updated
        if diff.total_seconds() < 900:
            return float(asset.last_price), float(asset.previous_close)

    try:
        ticker = yf.Ticker(asset.yahoo_ticker)
        data = ticker.history(period='5d')
        if not data.empty:
            price = float(data['Close'].iloc[-1])
            prev_close = price
            if len(data) >= 2:
                prev_close = float(data['Close'].iloc[-2])

            asset.last_price = price
            asset.previous_close = prev_close
            asset.last_updated = now
            asset.save()
            return price, prev_close
    except Exception as e:
        print(f"MarketService Error ({asset.symbol}): {e}")

    return float(asset.last_price), float(asset.previous_close)


# =============================================================================
# MODUŁ 3: IMPORT SERVICE
# =============================================================================

def process_xtb_file(uploaded_file, user):
    try:
        xls = pd.ExcelFile(uploaded_file)
    except Exception as e:
        raise ValueError(f"Excel Error: {e}")

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
            header_idx = idx
            break
    if header_idx is None: raise ValueError("Header not found.")

    uploaded_file.seek(0)
    df = pd.read_excel(uploaded_file, sheet_name=target_sheet, header=header_idx)
    df.columns = df.columns.str.strip()

    portfolio, _ = Portfolio.objects.get_or_create(user=user, defaults={'name': 'My IKE'})
    stats = {'added': 0, 'skipped': 0}

    for _, row in df.iterrows():
        if pd.isna(row.get('ID')): continue

        xtb_id = str(row['ID'])
        trans_type = _parse_transaction_type(str(row.get('Type', '')))
        quantity = _parse_quantity(trans_type, str(row.get('Comment', '')))

        try:
            date_obj = pd.to_datetime(row['Time'])
        except:
            continue

        amount = float(row['Amount']) if not pd.isna(row['Amount']) else 0.0

        asset_obj = None
        sym = str(row.get('Symbol', ''))
        if sym in TICKER_CONFIG:
            conf = TICKER_CONFIG[sym]
            asset_obj, _ = Asset.objects.get_or_create(
                symbol=sym,
                defaults={'yahoo_ticker': conf['yahoo'], 'currency': conf['currency'], 'name': conf['name']}
            )

        _, created = Transaction.objects.update_or_create(
            xtb_id=xtb_id,
            defaults={
                'portfolio': portfolio, 'asset': asset_obj, 'date': date_obj,
                'type': trans_type, 'amount': amount, 'quantity': quantity,
                'comment': str(row.get('Comment', ''))
            }
        )
        if created:
            stats['added'] += 1
        else:
            stats['skipped'] += 1

    return stats


def _parse_transaction_type(raw_type):
    raw = raw_type.lower().strip()
    if 'stock' in raw and 'purchase' in raw: return 'BUY'
    if 'stock' in raw and 'sale' in raw: return 'SELL'
    if 'close' in raw or 'profit' in raw: return 'SELL'
    if 'deposit' in raw: return 'DEPOSIT'
    if 'withdrawal' in raw: return 'WITHDRAWAL'
    if 'dividend' in raw: return 'DIVIDEND'
    if 'withholding tax' in raw: return 'TAX'
    return 'OTHER'


def _parse_quantity(trans_type, comment):
    if trans_type in ['BUY', 'SELL']:
        match = re.search(r'(BUY|SELL) ([0-9./]+)', comment)
        if match:
            try:
                return float(match.group(2).split('/')[0])
            except:
                pass
    return 0.0


# =============================================================================
# MODUŁ 4: PORTFOLIO SERVICE
# =============================================================================

def calculate_current_holdings(transactions: QuerySet, eur_rate: float, usd_rate: float):
    assets_summary = {}
    total_invested = 0.0
    cash = 0.0
    first_transaction_date = timezone.now().date()
    has_transactions = False

    for t in transactions:
        has_transactions = True
        if t.date.date() < first_transaction_date:
            first_transaction_date = t.date.date()

        amt = float(t.amount)
        qty = float(t.quantity)

        if t.type == 'DEPOSIT':
            total_invested += amt
            cash += amt
        elif t.type == 'WITHDRAWAL':
            total_invested -= abs(amt)
            cash -= abs(amt)
        elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
            cash += amt

        if t.asset:
            s = t.asset.symbol
            if s not in assets_summary:
                assets_summary[s] = {'qty': 0.0, 'cost': 0.0, 'realized': 0.0, 'obj': t.asset}

            if t.type == 'BUY':
                assets_summary[s]['qty'] += qty
                assets_summary[s]['cost'] += abs(amt)
            elif t.type == 'SELL':
                cur_qty = assets_summary[s]['qty']
                if cur_qty > 0:
                    ratio = qty / cur_qty
                    if ratio > 1: ratio = 1
                    cost_removed = assets_summary[s]['cost'] * ratio
                    assets_summary[s]['realized'] += (amt - cost_removed)
                    assets_summary[s]['qty'] -= qty
                    assets_summary[s]['cost'] -= cost_removed

    pln_holdings = []
    foreign_holdings = []
    closed_holdings = []

    charts = {'labels': [], 'allocation': [], 'profit_labels': [], 'profit_values': [], 'closed_labels': [],
              'closed_values': []}

    portfolio_value_stock = 0.0
    total_day_change_pln = 0.0

    unrealized_profit = 0.0
    gainers_count = 0
    losers_count = 0

    for s, data in assets_summary.items():
        qty = data['qty']
        asset = data['obj']

        if qty <= 0.0001:
            if abs(data['realized']) > 0.01:
                closed_holdings.append({'symbol': s, 'gain_pln': fmt_2(data['realized'])})
                charts['closed_labels'].append(s)
                charts['closed_values'].append(round(data['realized'], 2))
            continue

        cost = data['cost']
        avg_price = cost / qty if qty > 0 else 0

        cur_price, prev_close = get_cached_price(asset)

        multiplier = 1.0
        currency_code = 'PLN'
        target_list = pln_holdings
        if asset.currency == 'EUR':
            multiplier = eur_rate
            currency_code = 'EUR'
            target_list = foreign_holdings
        elif asset.currency == 'USD':
            multiplier = usd_rate
            currency_code = 'USD'
            target_list = foreign_holdings

        value_pln = (qty * cur_price) * multiplier

        current_position_gain = value_pln - cost
        unrealized_profit += current_position_gain

        total_gain = current_position_gain + data['realized']
        gain_percent = (total_gain / cost * 100) if cost > 0 else 0

        day_change_pct = ((cur_price - prev_close) / prev_close * 100) if prev_close > 0 else 0.0
        day_change_val = (qty * (cur_price - prev_close)) * multiplier
        total_day_change_pln += day_change_val

        if day_change_pct > 0:
            gainers_count += 1
        elif day_change_pct < 0:
            losers_count += 1

        target_list.append({
            'symbol': s,
            'name': asset.name,
            # WALORY: 4 miejsca po przecinku
            'quantity': fmt_4(qty),
            # CENY: 2 miejsca po przecinku
            'avg_price_pln': fmt_2(avg_price),
            'current_price_orig': fmt_2(cur_price),
            'currency': currency_code,
            'value_pln': fmt_2(value_pln),
            'gain_pln': fmt_2(total_gain),
            'gain_pln_raw': total_gain,
            'gain_percent': fmt_2(gain_percent),
            'day_change_pct': fmt_2(day_change_pct),
            'day_change_pct_raw': day_change_pct
        })

        portfolio_value_stock += value_pln
        charts['labels'].append(s)
        charts['allocation'].append(value_pln)
        charts['profit_labels'].append(s)
        charts['profit_values'].append(total_gain)

    if cash > 1:
        charts['labels'].append("CASH")
        charts['allocation'].append(cash)

    total_portfolio_value = portfolio_value_stock + cash
    total_profit = total_portfolio_value - total_invested

    value_yesterday = total_portfolio_value - total_day_change_pln
    portfolio_day_change_pct = (total_day_change_pln / value_yesterday * 100) if value_yesterday > 0 else 0.0
    total_return_pct = (total_profit / total_invested * 100) if total_invested > 0 else 0.0

    annual_return_pct = 0.0
    if has_transactions and total_invested > 0:
        days_investing = (date.today() - first_transaction_date).days
        if days_investing > 0:
            years = days_investing / 365.25
            if years < 1:
                annual_return_pct = total_return_pct
            else:
                annual_return_pct = total_return_pct / years

    return {
        'cash': fmt_2(cash),
        'invested': fmt_2(total_invested),
        'stock_value': fmt_2(portfolio_value_stock),

        # RAW VALUES (For Logic & Charts)
        'tile_value_raw': total_portfolio_value,
        'tile_day_pct_raw': portfolio_day_change_pct,
        'tile_total_profit_raw': total_profit,
        'tile_return_pct_raw': total_return_pct,
        'tile_day_pln_raw': total_day_change_pln,
        'tile_current_profit_raw': unrealized_profit,
        'tile_annual_pct_raw': annual_return_pct,

        # FORMATTED STRINGS (For Display - 2 decimal places, DOT separator)
        'tile_value_str': fmt_2(total_portfolio_value),
        'tile_day_pct_str': fmt_2(portfolio_day_change_pct),
        'tile_total_profit_str': fmt_2(total_profit),
        'tile_return_pct_str': fmt_2(total_return_pct),
        'tile_day_pln_str': fmt_2(total_day_change_pln),
        'tile_current_profit_str': fmt_2(unrealized_profit),
        'tile_annual_pct_str': fmt_2(annual_return_pct),

        'tile_gainers': gainers_count,
        'tile_losers': losers_count,

        'pln_holdings': pln_holdings,
        'foreign_holdings': foreign_holdings,
        'closed_holdings': closed_holdings,
        'charts': charts
    }


# =============================================================================
# MODUŁ 5: TIMELINE & NEWS
# =============================================================================

def calculate_historical_timeline(transactions: QuerySet, eur_rate, usd_rate):
    if not transactions.exists(): return {}
    start_date = transactions.first().date.date()
    end_date = date.today()

    user_tickers = list(set([t.asset.yahoo_ticker for t in transactions if t.asset]))
    benchmarks = ['^WIG', '^GSPC', 'USDPLN=X']
    all_tickers = list(set(user_tickers + benchmarks))

    try:
        hist_data = yf.download(all_tickers, start=start_date, end=end_date + timedelta(days=1), group_by='ticker',
                                progress=False, threads=True)
    except:
        hist_data = pd.DataFrame()

    sim = {'cash': 0.0, 'invested': 0.0, 'holdings': {}, 'wig_units': 0.0, 'sp500_units': 0.0, 'inflation_capital': 0.0}
    timeline = {'dates': [], 'points': [], 'val_user': [], 'val_inv': [], 'val_wig': [], 'val_sp': [], 'val_inf': [],
                'pct_user': [], 'pct_wig': [], 'pct_sp': [], 'pct_inf': []}

    trans_list = list(transactions)
    trans_idx = 0
    total_trans = len(trans_list)
    current_day = start_date

    while current_day <= end_date:
        is_deposit_day = False
        while trans_idx < total_trans and trans_list[trans_idx].date.date() <= current_day:
            t = trans_list[trans_idx]
            amt = float(t.amount)
            qty = float(t.quantity)
            if t.type == 'DEPOSIT':
                sim['cash'] += amt;
                sim['invested'] += amt;
                sim['inflation_capital'] += amt;
                is_deposit_day = True
                try:
                    p_wig = float(hist_data['^WIG']['Close'].asof(str(current_day)))
                    if p_wig > 0: sim['wig_units'] += amt / p_wig
                except:
                    pass
                try:
                    p_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                    p_sp = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
                    if p_usd > 0 and p_sp > 0: sim['sp500_units'] += (amt / p_usd) / p_sp
                except:
                    pass
            elif t.type == 'WITHDRAWAL':
                sim['cash'] -= abs(amt);
                sim['invested'] -= abs(amt);
                sim['inflation_capital'] -= abs(amt)
            elif t.type in ['BUY', 'SELL', 'DIVIDEND', 'TAX']:
                sim['cash'] += amt
            if t.asset:
                tk = t.asset.yahoo_ticker
                if t.type == 'BUY':
                    sim['holdings'][tk] = sim['holdings'].get(tk, 0.0) + qty
                elif t.type == 'SELL':
                    sim['holdings'][tk] = sim['holdings'].get(tk, 0.0) - qty
            trans_idx += 1

        user_val = sim['cash']
        for tk, q in sim['holdings'].items():
            if q <= 0.0001: continue
            try:
                price = float(hist_data[tk]['Close'].asof(str(current_day)))
                if math.isnan(price): price = 0.0
                val = price * q
                if '.DE' in tk:
                    val *= eur_rate
                elif '.US' in tk:
                    hist_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
                    if not math.isnan(hist_usd):
                        val *= hist_usd
                    else:
                        val *= usd_rate
                user_val += val
            except:
                pass

        wig_val = 0.0
        try:
            p = float(hist_data['^WIG']['Close'].asof(str(current_day)))
            if not math.isnan(p): wig_val = sim['wig_units'] * p
        except:
            pass

        sp_val = 0.0
        try:
            p_sp = float(hist_data['^GSPC']['Close'].asof(str(current_day)))
            p_usd = float(hist_data['USDPLN=X']['Close'].asof(str(current_day)))
            if not math.isnan(p_sp) and not math.isnan(p_usd): sp_val = sim['sp500_units'] * p_sp * p_usd
        except:
            pass

        sim['inflation_capital'] *= 1.06 ** (1 / 365)

        timeline['dates'].append(current_day.strftime("%Y-%m-%d"))
        timeline['points'].append(6 if is_deposit_day else 0)
        timeline['val_user'].append(round(user_val, 2))
        timeline['val_inv'].append(round(sim['invested'], 2))
        timeline['val_wig'].append(round(wig_val, 2) if wig_val > 0 else round(sim['invested'], 2))
        timeline['val_sp'].append(round(sp_val, 2) if sp_val > 0 else round(sim['invested'], 2))
        timeline['val_inf'].append(round(sim['inflation_capital'], 2))

        base = sim['invested'] if sim['invested'] > 0 else 1.0
        timeline['pct_user'].append(round((user_val - base) / base * 100, 2))
        timeline['pct_wig'].append(round((wig_val - base) / base * 100 if wig_val > 0 else 0, 2))
        timeline['pct_sp'].append(round((sp_val - base) / base * 100 if sp_val > 0 else 0, 2))
        timeline['pct_inf'].append(round((sim['inflation_capital'] - base) / base * 100, 2))

        current_day += timedelta(days=1)

    return timeline


def get_asset_news(symbol, name):
    news_list = []
    clean_name = name.split(' ')[0]

    if symbol.endswith('.PL'):
        ticker_clean = symbol.replace('.PL', '')
        query = f'"{clean_name}" OR "{ticker_clean}"'
        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'pl', 'gl': 'PL', 'ceid': 'PL:pl'}
    else:
        query = f'"{clean_name}" stock'
        base_url = "https://news.google.com/rss/search"
        params = {'q': f"({query}) when:30d", 'hl': 'en-US', 'gl': 'US', 'ceid': 'US:en'}

    encoded_query = urllib.parse.urlencode(params)
    rss_url = f"{base_url}?{encoded_query}"

    try:
        feed = feedparser.parse(rss_url)
        today = date.today()
        seen_titles = []
        for entry in feed.entries[:15]:
            title = entry.title
            is_duplicate = False
            for seen in seen_titles:
                if difflib.SequenceMatcher(None, title, seen).ratio() > 0.60:
                    is_duplicate = True;
                    break
            if is_duplicate: continue
            seen_titles.append(title)

            dt_obj = date(2000, 1, 1)
            date_label = "Recent"
            freshness = 2

            if hasattr(entry, 'published_parsed'):
                try:
                    dt_obj = date(entry.published_parsed.tm_year, entry.published_parsed.tm_mon,
                                  entry.published_parsed.tm_mday)
                    delta = (today - dt_obj).days
                    if delta <= 1:
                        date_label = "TODAY 🔥" if delta == 0 else "YESTERDAY"; freshness = 0
                    elif delta <= 7:
                        date_label = dt_obj.strftime("%Y-%m-%d"); freshness = 1
                    else:
                        date_label = dt_obj.strftime("%Y-%m-%d"); freshness = 2
                except:
                    pass

            tags = []
            title_lower = entry.title.lower()
            if 'espi' in title_lower or 'ebi' in title_lower or 'raport' in title_lower: tags.append('OFFICIAL')
            if 'dywidend' in title_lower or 'dividend' in title_lower: tags.append('MONEY')
            if 'wyniki' in title_lower or 'results' in title_lower: tags.append('RESULTS')

            news_list.append({'title': entry.title, 'link': entry.link,
                              'source': entry.source.title if hasattr(entry, 'source') else 'Google',
                              'date_label': date_label, 'date_obj': dt_obj, 'freshness': freshness, 'tags': tags})

        news_list.sort(key=lambda x: x['date_obj'], reverse=True)
        news_list = news_list[:6]
    except Exception as e:
        print(f"News Error: {e}")

    return news_list


def get_dividend_context(user):
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {}
    eur, usd = get_current_currency_rates()
    txs = Transaction.objects.filter(portfolio=portfolio, type__in=['DIVIDEND', 'TAX']).order_by('date')

    total_received_pln = 0.0
    total_tax_pln = 0.0
    yearly_data = {}
    monthly_data = {}
    payers = {}
    available_years = set()

    for t in txs:
        amt = float(t.amount)
        if t.asset:
            if t.asset.currency == 'EUR':
                amt *= eur
            elif t.asset.currency == 'USD':
                amt *= usd

        net_amount = amt
        if t.type == 'DIVIDEND':
            total_received_pln += amt
        elif t.type == 'TAX':
            total_tax_pln += abs(amt)

        year = t.date.year;
        month = t.date.month - 1
        available_years.add(year)
        yearly_data[year] = yearly_data.get(year, 0.0) + net_amount
        if year not in monthly_data: monthly_data[year] = [0.0] * 12
        monthly_data[year][month] += net_amount
        if t.type == 'DIVIDEND' and t.asset:
            sym = t.asset.symbol
            payers[sym] = payers.get(sym, 0.0) + amt

    sorted_years = sorted(list(available_years))
    yearly_values = [round(yearly_data.get(y, 0), 2) for y in sorted_years]
    sorted_payers = sorted(payers.items(), key=lambda item: item[1], reverse=True)
    top_payers_list = [{'symbol': k, 'amount': fmt_2(v)} for k, v in sorted_payers]

    return {
        'total_net': fmt_2(total_received_pln - total_tax_pln),
        'total_gross': fmt_2(total_received_pln),
        'total_tax': fmt_2(total_tax_pln),
        'top_payer': top_payers_list[0] if top_payers_list else None,
        'payers_list': top_payers_list,
        'years_labels': sorted_years,
        'years_data': yearly_values,
        'monthly_data': monthly_data,
    }


def get_dashboard_context(user):
    portfolio = Portfolio.objects.filter(user=user).first()
    if not portfolio: return {'error': 'No portfolio found.'}

    eur_rate, usd_rate = get_current_currency_rates()
    transactions = Transaction.objects.filter(portfolio=portfolio).order_by('date')

    current_state = calculate_current_holdings(transactions, eur_rate, usd_rate)
    timeline_data = calculate_historical_timeline(transactions, eur_rate, usd_rate)

    context = current_state.copy()
    context.update({
        'eur_rate': fmt_2(eur_rate),
        'usd_rate': fmt_2(usd_rate),
        'timeline_dates': timeline_data.get('dates', []),
        'timeline_deposit_points': timeline_data.get('points', []),
        'timeline_total_value': timeline_data.get('val_user', []),
        'timeline_invested': timeline_data.get('val_inv', []),
        'timeline_wig': timeline_data.get('val_wig', []),
        'timeline_sp500': timeline_data.get('val_sp', []),
        'timeline_inflation': timeline_data.get('val_inf', []),
        'timeline_pct_user': timeline_data.get('pct_user', []),
        'timeline_pct_wig': timeline_data.get('pct_wig', []),
        'timeline_pct_sp500': timeline_data.get('pct_sp', []),
        'timeline_pct_inflation': timeline_data.get('pct_inf', []),
        'chart_labels': current_state['charts']['labels'],
        'chart_allocation': current_state['charts']['allocation'],
        'chart_profit_labels': current_state['charts']['profit_labels'],
        'chart_profit_values': current_state['charts']['profit_values'],
        'closed_labels': current_state['charts']['closed_labels'],
        'closed_values': current_state['charts']['closed_values'],
    })

    return context