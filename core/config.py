# core/config.py

# --- CHART FORMATTING ---
def fmt_2(val):
    """Format float to 2 decimal places with spaces as thousand separators."""
    if val is None: return "0.00"
    return "{:,.2f}".format(val).replace(",", " ")

# --- MARKET CONSTANTS ---

# Benchmarks used in ROI calculations
BENCHMARKS = {
    'SP500': 'SPY',        # S&P 500 ETF
    'WIG': 'WIG.WA',       # Warsaw Stock Exchange Index
    'ACWI': 'ACWI'         # MSCI All Country World Index ETF
}

# Mapping of currency codes to Yahoo Finance tickers
CURRENCY_TICKERS = {
    'USD': 'USDPLN=X',
    'EUR': 'EURPLN=X',
    'GBP': 'GBPPLN=X',
    'CHF': 'CHFPLN=X',
    'NOK': 'NOKPLN=X',
    'SEK': 'SEKPLN=X',
    'DKK': 'DKKPLN=X',
    'CZK': 'CZKPLN=X'
}

# Standard list of currencies to track in market summary
SUMMARY_CURRENCIES = ["USDPLN=X", "EURPLN=X", "GBPPLN=X", "JPYPLN=X", "AUDPLN=X"]

# Standard list of indices to track in market summary
SUMMARY_INDICES = {
    '^GSPC': 'S&P 500',
    '^IXIC': 'Nasdaq',
    'WIG.WA': 'WIG',
    'WIG20.WA': 'WIG20',
    'MWIG40.WA': 'mWIG40',
    'sWIG80.WA': 'sWIG80'
}

# Inflation calculation constants
INFLATION_RATE_YEARLY = 1.06  # 6% assumed inflation
DAILY_INFLATION_RATE = INFLATION_RATE_YEARLY ** (1 / 365)


# --- FORMATTING HELPERS ---
def fmt_4(val):
    """Format float to 4 decimal places."""
    if val is None: return "0.0000"
    return f"{float(val):.4f}"


# --- TICKET TRANSLATION RULES (XTB -> YAHOO) ---
# Key: Suffix in XTB
# Value: {
#    'yahoo_suffix': replacement suffix (empty string = remove suffix),
#    'default_currency': currency code
# }
SUFFIX_MAP = {
    '.PL': {'yahoo_suffix': '.WA', 'default_currency': 'PLN'}, # Poland
    '.US': {'yahoo_suffix': '',    'default_currency': 'USD'}, # USA
    '.DE': {'yahoo_suffix': '.DE', 'default_currency': 'EUR'}, # Germany
    '.UK': {'yahoo_suffix': '.L',  'default_currency': 'EUR'}, # UK
    '.FR': {'yahoo_suffix': '.PA', 'default_currency': 'EUR'}, # France
    '.NL': {'yahoo_suffix': '.AS', 'default_currency': 'EUR'}, # Netherlands
    '.ES': {'yahoo_suffix': '.MC', 'default_currency': 'EUR'}, # Spain
    '.IT': {'yahoo_suffix': '.MI', 'default_currency': 'EUR'}, # Italy
    '.BE': {'yahoo_suffix': '.BR', 'default_currency': 'EUR'}, # Belgium
    '.PT': {'yahoo_suffix': '.LS', 'default_currency': 'EUR'}, # Portugal
    '.FI': {'yahoo_suffix': '.HE', 'default_currency': 'EUR'}, # Finland
    '.NO': {'yahoo_suffix': '.OL', 'default_currency': 'NOK'}, # Norway
    '.SE': {'yahoo_suffix': '.ST', 'default_currency': 'SEK'}, # Sweden
    '.DK': {'yahoo_suffix': '.CO', 'default_currency': 'DKK'}, # Denmark
    '.CH': {'yahoo_suffix': '.SW', 'default_currency': 'CHF'}, # Switzerland
    '.CZ': {'yahoo_suffix': '.PR', 'default_currency': 'CZK'}, # Czech Republic
}
