# core/services/config.py

# MAPOWANIE SUFIKSÓW (Reguły Tłumaczenia XTB -> Yahoo)
# Klucz: Końcówka w XTB
# Wartość: {
#    'yahoo_suffix': na co zamienić w Yahoo (None = usuń końcówkę),
#    'default_currency': waluta, jeśli Yahoo nie odpowie
# }

SUFFIX_MAP = {
    '.PL': {'yahoo_suffix': '.WA', 'default_currency': 'PLN'},
    '.US': {'yahoo_suffix': '',    'default_currency': 'USD'},  # Np. AAPL.US -> AAPL
    '.DE': {'yahoo_suffix': '.DE', 'default_currency': 'EUR'},
    '.UK': {'yahoo_suffix': '.L',  'default_currency': 'GBP'},  # Tu uwaga: Yahoo często ma .L
    '.FR': {'yahoo_suffix': '.PA', 'default_currency': 'EUR'},
    '.NL': {'yahoo_suffix': '.AS', 'default_currency': 'EUR'},
    # Możesz dodawać kolejne (np. .ES dla Hiszpanii)
}

# Formatowanie liczb (pomocnicze)
def fmt_2(value):
    if value is None: return "0.00"
    return f"{float(value):.2f}"

def fmt_4(value):
    if value is None: return "0.0000"
    return f"{float(value):.4f}"