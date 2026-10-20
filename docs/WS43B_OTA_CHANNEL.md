# Kanał OTA – Waveshare ESP32-S3-Touch-LCD-4.3B

## Repo i gałąź źródeł

Firmware dla płytki Waveshare ESP32-S3-Touch-LCD-4.3B opiera się na repo
`honzo90/BambuHelper`, gałąź `waveshare-43b`. Panel WebUI w przeglądarce odpytuje:

```
https://api.github.com/repos/honzo90/BambuHelper/releases/latest
```

Kanal stabilny = opublikowane GitHub Releases (nie draft, nie prerelease).
GitHub `releases/latest` pomija wydania testowe (prerelease).
Inne płytki korzystają z upstream `Keralots/BambuHelper`.

## Status wydania

Przygotowano TESTOWE wydanie `v3.9.1-ws43b-test.1` jako GitHub **prerelease**.
Kanał `releases/latest` nadal pozostaje stabilny i ignoruje prerelease, więc
brak stabilnego release prawidłowo daje komunikat o braku stabilnego release
(HTTP 404), a przycisk instalacji pozostaje ukryty. HTTP 403 i awarie sieci
traktowane są jako błędy.

Testowe wydanie instaluje się **ręcznie**: pobierz plik `-ota.bin`, a następnie
w WebUI otwórz Firmware update → Manual update, wybierz pobrany plik i kliknij
Upload firmware. W trakcie aktualizacji utrzymuj zasilanie i otwartą stronę.
Kanał stabilny nie wybiera tego wydania automatycznie.

## Format assetu OTA

Asset przygotowanego testowego pakietu:

```
BambuHelper-ws_lcd_43b-v3.9.1-ws43b-test.1-ota.bin
```

Wymagania instalacji testowej:

- istniejąca instalacja WS43B z tabelą OTA `app0`/`app1`,
- slot OTA `3145728` bytes,
- binarium aplikacji **nie** służy do pierwszego flashowania czystej płytki
  (full/merged flash ani NVS nie są plikiem OTA).

Build pochodzi z dedykowanego Arduino-ESP32 core 3.3.11 / cache64.

## Poprawny URL początkowy

```
https://github.com/honzo90/BambuHelper/releases/download/<tag>/BambuHelper-ws_lcd_43b-<wersja>-ota.bin
```

Tag i wersja: litery ASCII, cyfry, kropka, myślnik, podkreślenie; wersja
zawiera cyfrę. Odrzucane: inne repo/płytki, query, fragment, dodatkowe
segmenty. Istniejące przekierowanie GitHub do CDN pozostaje obsługiwane.

## Zakres tego commitu

Commit przygotowuje źródła kanału dla testowego prerelease
`v3.9.1-ws43b-test.1`. Dokumentacja opisuje **przygotowany** pakiet — nie
twierdzi, że wydanie zostało już opublikowane ani przetestowane na urządzeniu.
Nie wgrywa urządzenia. Wgrany firmware nie przełączy repo samodzielnie –
wymaga późniejszego świadomego wgrania wersji zawierającej zmianę.

Błąd dark-screen/touch-wake pozostaje **otwarty** (nierozwiązany). Test build
nie oznacza potwierdzenia stabilności sprzętu.

## Ograniczenie OTA

Backend ma retry z `client.setInsecure()`. Wybór repo nie jest podpisem
kryptograficznym firmware. Transport/podpisy to osobna zmiana – obecna
zmiana ich nie naprawia.
