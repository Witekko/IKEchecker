# IKE Tracker / Portfolio Manager 📈

Aplikacja webowa oparta na *Django* do śledzenia wyników portfela inwestycyjnego (specjalizacja: konta IKE/IKZE oraz XTB).
Automatyzuje import transakcji, pobiera aktualne kursy giełdowe i walutowe oraz oblicza zaawansowane wskaźniki rentowności (TWR, MWR).

## 🚀 Kluczowe Funkcjonalności

* *Import Danych XTB:* Obsługa plików .csv i .xlsx z raportów XTB (Cash Operations).
    * Inteligentny mechanizm *Upsert*: Rozpoznaje duplikaty i aktualizuje istniejące wpisy zamiast je dublować.
    * Wykrywanie i usuwanie "duchów" (błędnych wpisów manualnych) w importowanym zakresie dat.
* *Integracja z Yahoo Finance:*
    * Automatyczne pobieranie cen akcji i ETF-ów.
    * Pobieranie metadanych (Sektor, Typ aktywa, Waluta).
    * Obsługa walut (automatyczne przeliczanie USD/EUR/GBP na PLN).
* *Analityka Portfela:*
    * Obliczanie *TWR* (Time-Weighted Return) i *MWR/XIRR* (Money-Weighted Return).
    * Wykresy wartości portfela w czasie vs wpłacony kapitał.
    * Alokacja wg sektorów i typów aktywów.
    * Śledzenie dywidend.
* *Tryb Demo:* Wbudowana komenda do generowania przykładowego portfela w celu przetestowania aplikacji.

## 🛠️ Technologie

* *Backend:* Python 3.12+, Django 5.x
* *Data Processing:* Pandas, NumPy
* *Market Data:* yfinance
* *Baza Danych:* SQLite (domyślnie) / PostgreSQL

## 🧪 Tryb DEMO

Aplikacja posiada wbudowany tryb demonstracyjny, który czyści bazę i ładuje zestaw przykładowych danych (bazujących na realnych transakcjach historycznych).
