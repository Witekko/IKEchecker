# core/services/config.py

# MAPOWANIE SUFIKSÓW (Reguły Tłumaczenia XTB -> Yahoo)
# Klucz: Końcówka w XTB
# Wartość: {
#    'yahoo_suffix': na co zamienić w Yahoo (pusty string = usuń końcówkę),
#    'default_currency': waluta (opcjonalne, do przyszłego użytku)
# }

SUFFIX_MAP = {
    '.PL': {'yahoo_suffix': '.WA', 'default_currency': 'PLN'}, # Polska
    '.US': {'yahoo_suffix': '',    'default_currency': 'USD'}, # USA (AAPL.US -> AAPL)
    '.DE': {'yahoo_suffix': '.DE', 'default_currency': 'EUR'}, # Niemcy
    '.UK': {'yahoo_suffix': '.L',  'default_currency': 'GBP'}, # UK
    '.FR': {'yahoo_suffix': '.PA', 'default_currency': 'EUR'}, # Francja
    '.NL': {'yahoo_suffix': '.AS', 'default_currency': 'EUR'}, # Holandia
    '.ES': {'yahoo_suffix': '.MC', 'default_currency': 'EUR'}, # Hiszpania
    '.IT': {'yahoo_suffix': '.MI', 'default_currency': 'EUR'}, # Włochy
    '.BE': {'yahoo_suffix': '.BR', 'default_currency': 'EUR'}, # Belgia
    '.PT': {'yahoo_suffix': '.LS', 'default_currency': 'EUR'}, # Portugalia
    '.FI': {'yahoo_suffix': '.HE', 'default_currency': 'EUR'}, # Finlandia
    '.NO': {'yahoo_suffix': '.OL', 'default_currency': 'NOK'}, # Norwegia
    '.SE': {'yahoo_suffix': '.ST', 'default_currency': 'SEK'}, # Szwecja
    '.DK': {'yahoo_suffix': '.CO', 'default_currency': 'DKK'}, # Dania
    '.CH': {'yahoo_suffix': '.SW', 'default_currency': 'CHF'}, # Szwajcaria
    '.CZ': {'yahoo_suffix': '.PR', 'default_currency': 'CZK'}, # Czechy
}

# Formatowanie liczb (pomocnicze)
def fmt_2(value):
    if value is None: return "0.00"
    return f"{float(value):.2f}"

def fmt_4(value):
    if value is None: return "0.0000"
    return f"{float(value):.4f}"