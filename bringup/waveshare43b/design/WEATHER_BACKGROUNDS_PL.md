# Statyczna pogoda w tle Wydruku — podglądy

Stan DESIGN_PREVIEW_ONLY. Firmware 9972d7ca bez zmian, bez dostępu do urządzenia.
Generator preview_dashboard_weather_backgrounds.py korzysta z kodu układu
preview_dashboard_refined.py i fontów Inter. Pillow12.3, dane syntetyczne.
Każdy wariant ma 800×480 i osobny obraz z widoczną/ukrytą listwą.

Warianty dashboard-weather-{cloud,clear,rain,snow,night,neutral}.png.
Motyw znajduje się pod nieprzezroczystymi kartami. Wypełnienia postępu i AMS
pozostają zielone. Brak świeżej pogody: neutralne tło, temperatura —.
Nocny przykład pokazuje pogodną noc; księżyc jest symbolem, nie fazą astronomiczną.
Przy implementacji noc/dzień należy łączyć z pogodą (np. deszcz także nocą),
nie zastępować każdej pogody księżycem. Brak danych słonecznych nie może
udawać potwierdzonej nocy. Gradient jest ilustracją; koszt renderowania i
buforowania trzeba zmierzyć na ESP32. Nie obiecuje się płynności na podstawie PNG.

Wygenerowano wszystkie warianty; cloud/night sprawdzone wizualnie.
Nie kompilowano, ponieważ nie zmieniono kodu firmware. Nie wykonano testu
sprzętowego. Następny krok: wybór wyglądu, potem wdrożenie statycznego motywu
z zachowaniem niekolidujących obszarów pogody, zegara i HMS.

Odtworzenie:
```sh
# z katalogu głównego repozytorium
python3 bringup/waveshare43b/design/preview_dashboard_weather_backgrounds.py
```
