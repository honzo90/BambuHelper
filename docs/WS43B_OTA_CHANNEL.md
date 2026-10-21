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

Wydanie **v3.9.1** jest przeznaczone do publikacji jako zwykły GitHub release,
aby kanał `releases/latest` mógł je zaoferować w Update online.
Panel porównuje numery major/minor/patch; przy równych numerach wersja bez
suffixu jest nowsza od wersji z suffixem. Dlatego `v3.9.1` będzie oferowana
urządzeniu z `v3.9.1-ws43b-test.1`, a urządzeniu z `v3.9.1` już nie.

Zwykły release GitHub jest **sposobem dystrybucji**, nie dowodem stabilności.
Wyniki nowego buildu i testów należy sprawdzić w `BUILD-INFO.json` dołączonym
do wydania. Sam numer v3.9.1 nie potwierdza wgrania ani akceptacji fizycznej.

## Dowody (dotyczą test.1)

- **PASS** 21.10.2026: ręczny OTA transfer, restart, odczyt całej aplikacji
  i settings — OK.
- **FAIL** runtime120s: świeżość danych mimo WiFi/MQTT; przyczyna nieznana.
- Obraz/dotyk: nieweryfikowane.
- Dark-screen / touch-wake: **OPEN**.
- `setInsecure()` retry i brak podpisów: **nienaprawione**.

## Format assetu OTA

Asset przygotowanego wydania:

```
BambuHelper-ws_lcd_43b-v3.9.1-ota.bin
```

Wymagania instalacji:

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

Commit przygotowuje źródła kanału dla zwykłego wydania **v3.9.1**.
Dokumentacja opisuje **przygotowany** pakiet — nie twierdzi, że wydanie zostało
opublikowane ani przetestowane na urządzeniu. Nie wgrywa urządzenia. Wgrany
firmware nie przełączy repo samodzielnie – wymaga późniejszego świadomego
wgrania wersji zawierającej zmianę.

Błąd dark-screen/touch-wake pozostaje **otwarty** (nierozwiązany). Build
nie oznacza potwierdzenia stabilności sprzętu.

## Ograniczenie OTA

Backend ma retry z `client.setInsecure()`. Wybór repo nie jest podpisem
kryptograficznym firmware. Transport/podpisy to osobna zmiana – obecna
zmiana ich nie naprawia.
