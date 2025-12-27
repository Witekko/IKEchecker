import yfinance as yf
import pandas as pd

# Ustawiamy ticker, który na 100% działa (Dolar do Złotego)
ticker = "SNK.WA"

print(f"--- SPRAWDZANIE DLA TICKERA: {ticker} ---\n")

# TEST 1: Dane historyczne (Rok 2024) - To POWINNO działać
print("1. Próba pobrania danych z przeszłości (Styczeń 2024)...")
try:
    data_past = yf.download(ticker, start="2024-01-01", end="2024-01-10", progress=False)
    if not data_past.empty:
        print("   SUKCES! Pobrano wierszy:", len(data_past))
        print(data_past.head(2))  # Pokaż pierwsze 2 wiersze
    else:
        print("   BŁĄD: Pusta tabela dla 2024!")
except Exception as e:
    print(f"   CRITICAL ERROR: {e}")

print("\n" + "=" * 30 + "\n")

# TEST 2: Dane z Twojego Excela (Wrzesień - Grudzień 2025)
print("2. Próba pobrania danych dla Twoich transakcji (2025-09-01 do 2025-12-27)...")
try:
    # To jest zakres, o który pyta Twój Dashboard
    data_future = yf.download(ticker, start="2025-09-01", end="2025-12-27", progress=False)

    if data_future.empty:
        print("   WYNIK: PUSTA TABELA (Empty DataFrame).")
        print("   DIAGNOZA: Yahoo Finance odmówiło danych dla tego okresu.")
    else:
        print("   WYNIK: NIESPODZIANKA! Mamy dane:")
        print(data_future)
except Exception as e:
    print(f"   BŁĄD SYSTEMOWY: {e}")