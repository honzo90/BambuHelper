# BambuHelper — Waveshare 4.3B

[English](README.md) | [Polski](README.pl.md) | **Deutsch**

Ein Monitor für Bambu-Lab-Drucker auf dem **Waveshare ESP32-S3-Touch-LCD-4.3B** mit kapazitivem **800×480-RGB-Touchscreen**. BambuHelper zeigt Druckfortschritt, Temperaturen und AMS-Daten sowie eine Uhr und auf Wunsch das Wetter. Die Bedienung am Panel und die Konfiguration im Browser sind auf **Deutsch, Polnisch und Englisch** verfügbar.

**Aktuelle stabile Version: [v4.0.0](https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0).** Sie enthält die mit Beta 5 eingeführte Korrektur für Bildartefakte beim Speichern von Einstellungen, etwa für Wetter und Nachtmodus. Das Release verwendet ein neu gebautes SDK mit XIP aus dem PSRAM und einen angeforderten RGB-Pixeltakt von **12 MHz**. Die Funktionen von Beta 5 und die Oberflächen auf **DE / PL / EN** bleiben erhalten. Auf dem Startbildschirm steht weiterhin v0.9; die Firmware-Version in den Geräteinformationen ist **v4.0.0**.

## Funktionen

| Bereich | Funktionsumfang für Waveshare 4.3B |
|---|---|
| **Display und Touch** | ST7262-RGB-Display mit 800×480 Pixeln, kapazitiver GT911-Touchcontroller über I2C und Ansteuerung der Hintergrundbeleuchtung. |
| **Bedienoberfläche** | Eigene Ansichten für Druck, AMS, Druckdetails, Anzeigen, Uhr und Einstellungen mit Navigation für das 4,3-Zoll-Panel. |
| **Druckerdaten** | MQTT/TLS über LAN Direct oder Bambu Cloud; Fortschritt, Schichten, Restzeit, Temperaturen und Lüfterwerte, soweit vom Drucker bereitgestellt. |
| **AMS-Daten** | Material, Farbe, verbleibendes Filament, Temperatur, Feuchtigkeit und Trocknungsstatus, soweit von Drucker oder AMS gemeldet. |
| **Datenaktualität** | Gültigkeit und Alter einzelner Messwerte werden getrennt bewertet. In inkrementellen MQTT-Meldungen ausgelassene Felder bleiben erhalten; ein echter Nullwert wird von einem fehlenden Messwert unterschieden. |
| **Ansichten und Animationen** | Einfacher Modus und ein erweiterter Modus in Entwicklung; Druck-, Trocknungs- und Kühlansichten, Uhr und Bildschirmschoner einschließlich Pong und Wasseruhr. |
| **Deutsch / Polski / English** | Gespeicherte Sprachwahl für Panel und WebUI gemeinsam. Deutsch ist ab Beta 3 verfügbar. |
| **Wetter und Nachtmodus** | Optionale Open-Meteo-Daten, Sonnenaufgang und Sonnenuntergang sowie Nachtzeitplan. Wetterabruf und Ortssuche benötigen Internetzugang. |
| **Konfiguration und Diagnose** | WLAN-, Drucker- und Anzeigeeinstellungen, Steuerungsfunktionen und OTA im Browser; zusätzlich `/monitor/status` und Werkzeuge zur Bildaufzeichnung für die Entwicklung. |
| **Entwicklungswerkzeuge** | Separater Arduino-CLI-Build mit festgelegtem SDK (cache64_xip für v4.0.0), Tests auf dem Computer, synthetische MQTT-Daten sowie Grafik- und Schriftgeneratoren. |

Das Profil verwendet `BAMBU_MONITOR_ONLY=0` und enthält auch die Steuerung der Bauraumbeleuchtung und intelligenter Steckdosen. Andere Platinen, Druckermodelle und Konfigurationen mit mehreren Druckern wurden in diesem Projekt noch nicht vollständig geprüft.

## Installation und Updates

### Erste Installation über USB

1. Öffne den **[BambuHelper-Installer](https://honzo90.github.io/BambuHelper/)** in Chrome oder Edge auf einem Computer. Die USB-Installation funktioniert nicht auf dem iPhone.
2. Verbinde das Panel mit einem USB-Kabel, das Datenübertragung unterstützt. Der Installer ist ausschließlich für das **Waveshare ESP32-S3-Touch-LCD-4.3B** vorgesehen.
3. Bestätige das genaue Platinenmodell und das Löschen der Einstellungen. Wähle auf der derzeit polnischen Installationsseite **„Przygotuj instalację“** (Installation vorbereiten), danach **„Połącz i zainstaluj“** (Verbinden und installieren).
4. Richte nach dem Neustart das WLAN über das Netzwerk des Panels ein. Die Verbindungsdaten erscheinen auf dem Display.
5. Der USB-Installer installiert weiterhin **Beta 2**. Wechsle anschließend im WebUI zum Kanal **Stable**, suche nach Updates und installiere **v4.0.0**. Danach kannst du **Deutsch** im Menü oder WebUI auswählen.

**Die erste USB-Installation löscht den Flash-Speicher einschließlich WLAN-Einstellungen, Druckerkonfiguration und bisheriger Firmware.** Die Seite prüft das Firmwareabbild, bevor sie die Installation freigibt. Der vollständige Installationsvorgang über den Browser ist noch nicht durch einen Test an einer physischen Platine bestätigt.

### Vorhandenes Panel per OTA aktualisieren

- Im WebUI den Kanal **Stable** wählen, nach Updates suchen und **v4.0.0** installieren. Nutzer von v3.9.1 und v4.0.0-alpha.1 können ihre bisherige Update-Suche verwenden; Versionen ohne Kanalauswahl suchen nach stabilen Releases. Auch der Beta-Kanal bietet v4.0.0 als neuere Version als Beta 5 an.
- **Manuelles Update:** [`BambuHelper-ws_lcd_43b-v4.0.0-ota.bin`](https://github.com/honzo90/BambuHelper/releases/download/v4.0.0/BambuHelper-ws_lcd_43b-v4.0.0-ota.bin) herunterladen und auf der Firmware-Update-Seite im WebUI hochladen. Dies ist auch eine Option, wenn das Online-Update das Release nicht anbietet.
- [Versionshinweise und Quellen für v4.0.0](https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0) · [Prüfsummen](https://github.com/honzo90/BambuHelper/releases/download/v4.0.0/SHA256SUMS) · [Alle Releases](https://github.com/honzo90/BambuHelper/releases).

OTA setzt das vorhandene WS43B-Partitionslayout mit **zwei Slots zu je 3 MiB** voraus. Die OTA-Datei enthält nur die Anwendung und eignet sich nicht für die Erstinstallation.

## Entwicklungsstand

**Rückmeldung vom Gerät:** Der Projektbetreiber bestätigte, dass Beta 5 funktioniert und das physische Display stabil ist. Für v4.0.0 wurde derselbe Code mit ausschließlich geänderter Firmware-Versionsnummer neu gebaut. Das neu nummerierte Firmwareabbild wurde nicht separat auf Hardware getestet. Langzeitbetrieb und Wiederherstellung nach Störungen müssen noch geprüft werden.

Der frühere [Fehler mit dunklem Bildschirm und fehlendem Aufwecken per Touch](https://github.com/honzo90/BambuHelper/issues/1) bleibt zur weiteren Beobachtung **offen**.

## Beispielansichten

Die folgenden Bilder sind **auf dem Computer erzeugte 800×480-Vorschauen** mit den Anzeigefunktionen, Schriften und Grafiken des Projekts sowie synthetischen Daten. Sie zeigen die **polnische Oberfläche**, keine Fotos oder Bildschirmaufnahmen einer deutschen Installation. Demo-Kopfzeile und Darstellung können vom Gerät abweichen.

| Druckübersicht | AMS |
|---|---|
| ![Druckfortschritt, Temperaturen und aktives Filament](img/waveshare-43b/print.png) | ![Filamentspulen, Feuchtigkeit und Trocknungsstatus des AMS](img/waveshare-43b/ams.png) |

| Druckdetails | Einstellungen |
|---|---|
| ![Schichten, Bauraumtemperatur, Geschwindigkeit und Lüfter](img/waveshare-43b/details.png) | ![Einstellungen für Darstellung, Uhr, Wetter und Sprache](img/waveshare-43b/settings.png) |

| Darstellung | Startbildschirm |
|---|---|
| ![Farbschemata und Anzeigemodi](img/waveshare-43b/appearance.png) | ![Startphasen und Warten auf Druckerdaten](img/waveshare-43b/boot.png) |

[Herkunft der Vorschauen und Prüfsummen der Quellen](img/waveshare-43b/provenance.json). Die Vorschauen belegen nicht die Stabilität von Display, Touch oder Aufwecken.

## Firmware bauen und prüfen

Das **Release v4.0.0** verwendet **Arduino ESP32 3.3.11**, **ESP-IDF 5.5.5**, das neu gebaute SDK **cache64_xip** und einen angeforderten RGB-Pixeltakt von **12 MHz**. Die genauen Quellen stehen unter [Tag v4.0.0](https://github.com/honzo90/BambuHelper/tree/v4.0.0); SDK-Herkunft, Konfiguration und Prüfergebnisse enthält [BUILD-INFO.json](https://github.com/honzo90/BambuHelper/releases/download/v4.0.0/BUILD-INFO.json). Zum Nachbauen sind das separat vorbereitete XIP-SDK, sein passendes Manifest mit SHA-256 sowie `WS43B_SDK_PROFILE=cache64_xip` und `WS43B_RGB_PCLK_HZ=12000000` erforderlich. Der Standard-Build mit cache64 reproduziert dieses Release nicht.

Für die Entwicklung dienen die englischen **[Waveshare-Build- und Testhinweise](WAVESHARE.md)**, das Profil [`boards/ws_lcd_43b.ini`](boards/ws_lcd_43b.ini) und [`bringup/waveshare43b/integration/build.py`](bringup/waveshare43b/integration/build.py). Dies ist ein eigener Arduino-CLI-Build, keine PlatformIO-Umgebung.

Der Build und die Prüfungen des Firmwareabbilds v4.0.0 waren erfolgreich, ebenso **48 Fälle zur Update-Auswahl** in acht Quellcode-/Sprachkombinationen. Der Umfang der physischen Bestätigung ist oben beschrieben; Build und Host-Tests ersetzen keine Hardwareprüfung.

## Orientierung im Quellcode

- **Display und Touch:** [Displayintegration](src/lgfx_panel_ws43b.cpp), [Toucheingaben](src/button_touch_ws43b.cpp), [Paneloberfläche](src/display_ws43b.cpp).
- **Telemetrie und MQTT:** [Datenmodell](include/bambu_monitor.h), [Parser der Druckermeldungen](include/bambu_monitor_parser.h), [MQTT-Verbindung](src/bambu_mqtt.cpp).
- **Uhr, Wetter und Sprache:** [Uhreinstellungen](src/ws43b_clock_settings.cpp), [Wetter](src/ws43b_weather.cpp), [Sprachwahl](src/ws43b_language.cpp).
- **Werkzeuge:** [Host-Tests](bringup/waveshare43b/integration/tests), [Build-Vorbereitung](prepare_build.py), [Hinweise zu Drittkomponenten](THIRD_PARTY_NOTICES.md).

## Weiterführende Dokumentation

Die erhaltene englische Dokumentation behandelt auch andere Platinen. Deren GPIO-, PlatformIO- und Installationsanleitungen gelten nicht unmittelbar für das 4.3B; dafür sind die obigen Schritte und [WAVESHARE.md](WAVESHARE.md) maßgeblich.

- [Weitere unterstützte Platinen](README.md#supported-boards)
- [Verbindung zu Bambu Cloud](README.md#connecting-to-bambu-cloud) und [Sicherheit im Cloud-Modus](README.md#cloud-mode-security-notice)
- [Energiemessung](README.md#power-monitoring)
- [Druckerfehler und HMS-Codes](README.md#printer-errors-hms)
- [Eigene geglättete Schriften](README.md#custom-smooth-fonts)

## Lizenz und Mitwirkende

MIT. Dieses Projekt basiert auf [BambuHelper von Keralots und Mitwirkenden](https://github.com/Keralots/BambuHelper). Der Zweig `waveshare-43b` entstand auf Grundlage von v3.9.0 (`23347fbb`); `main` bewahrt die Geschichte des Ausgangsprojekts. Die Lizenzen externer Komponenten sind in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) aufgeführt.
