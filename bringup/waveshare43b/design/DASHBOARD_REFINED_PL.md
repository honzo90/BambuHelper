# Wydruk z pogodą — propozycja dopracowania

Stan: DESIGN_PREVIEW_ONLY. Firmware 9972d7ca niezmieniony; brak dostępu do urządzenia.
Podgląd 800×480 na danych syntetycznych, wygenerowany przez
preview_dashboard_refined.py (Pillow 12.3, istniejące fonty Inter).

- Czytelniejsza hierarchia procentu i pozostałego czasu.
- Pogoda/lokalizacja oraz godzina/data w nagłówku, niezależna kropka statusu P2S.
- Trzy spójne karty temperatur; żółty wariant zmiany temperatury pozostaje
  wymaganiem wdrożenia, ta ilustracja pokazuje wartości stabilne.
- Wypełnienie poziome postępu i znanych ilości AMS. Brak danych bez wypełnienia.
- Obrys tylko aktywnego slotu. Dolna listwa w dwóch osobnych stanach.
- Bez nowych animacji. Kolory to proponowany motyw, nie zmiana ustawień użytkownika.

Pliki: dashboard-refined-hidden.png, dashboard-refined-navigation.png,
preview_dashboard_refined.py i ten opis. Podgląd sprawdzony wizualnie.
Nie kompilowano firmware, ponieważ nie zmieniono jego kodu.
Następny krok: ocena projektu przez użytkownika; dopiero potem implementacja,
obsługa długich nazw, stanów nieaktualnych i testy dotyku. Widok nie dowodzi
sprzętowej poprawności ani trwałego ustąpienia wcześniejszych artefaktów.

Odtworzenie:
```sh
# z katalogu głównego repozytorium
python3 bringup/waveshare43b/design/preview_dashboard_refined.py
```
