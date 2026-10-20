# Kanał OTA – Waveshare ESP32-S3-Touch-LCD-4.3B

## Repo i gałąź źródeł

Firmware dla płytki Waveshare ESP32-S3-Touch-LCD-4.3B opiera się na repo
`honzo90/BambuHelper`, gałąź `waveshare-43b`. Panel WebUI w przeglądarce odpytuje:

```
https://api.github.com/repos/honzo90/BambuHelper/releases/latest
```

Kanal stabilny = opublikowane GitHub Releases (nie draft, nie prerelease).
Inne płytki korzystają z upstream `Keralots/BambuHelper`.

## Status wydania

Nie istnieje jeszcze żadne wydanie. Firmware przy HTTP 404 wyświetla czytelny
komunikat o braku stabilnego release; przycisk instalacji pozostaje ukryty.
HTTP 403 i awarie sieci traktowane są jako błędy.

## Format assetu OTA

Przyszły asset aplikacji:

```
BambuHelper-ws_lcd_43b-v<wersja>-ota.bin
```

Przykład planu: tag `v3.9.1`, asset `BambuHelper-ws_lcd_43b-v3.9.1-ota.bin`.
Firmware obecnie v3.9.0 – nie podniesiony w tej zmianie.

Wydanie wymaga: zgodnego `FW_VERSION`, nowszej wersji, binarium z dedykowanego
Arduino-ESP32 core 3.3.11/cache64 oraz poprawnego slotu OTA. Full/merged flash/NVS
nigdy nie są plikiem OTA.

## Poprawny URL początkowy

```
https://github.com/honzo90/BambuHelper/releases/download/<tag>/BambuHelper-ws_lcd_43b-<wersja>-ota.bin
```

Tag i wersja: litery ASCII, cyfry, kropka, myślnik, podkreślenie; wersja
zawiera cyfrę. Odrzucane: inne repo/płytki, query, fragment, dodatkowe
segmenty. Istniejące przekierowanie GitHub do CDN pozostaje obsługiwane.

## Plan publikacji przyszłego wydania

1. Sprawdzić sprzęt osobno.
2. Nadać zgodną wersję/tag.
3. Build + checksum.
4. Opublikować release z kompatybilnym assetem i opisem zmian.
5. Sprawdzić na urządzeniu.

To plan przyszłych czynności, nie wykonane działania.

## Zakres tego commitu

Commit przygotowuje źródła kanału. Nie tworzy wydania, nie udostępnia `.bin`
i nie wgrywa urządzenia. Wgrany firmware nie przełączy repo samodzielnie –
wymaga późniejszego świadomego wgrania wersji zawierającej zmianę.

Błąd dark-screen/touch-wake pozostaje nierozwiązany. Test build nie oznacza
potwierdzenia stabilności sprzętu.

## Ograniczenie OTA

Backend ma retry z `client.setInsecure()`. Wybór repo nie jest podpisem
kryptograficznym firmware. Transport/podpisy to osobna zmiana – obecna
zmiana ich nie naprawia.
