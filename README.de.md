# BambuHelper — Waveshare 4.3B

[English](README.md) | [Polski](README.pl.md) | **Deutsch**

Ein Monitor für Bambu-Lab-Drucker auf dem **Waveshare ESP32-S3-Touch-LCD-4.3B** mit kapazitivem **800×480-RGB-Touchscreen**. BambuHelper zeigt Druckfortschritt, Temperaturen und AMS-Daten sowie eine Uhr und auf Wunsch das Wetter. Die Bedienung am Panel und die Konfiguration im Browser sind auf **Deutsch, Polnisch und Englisch** verfügbar.

Aktuelle Version: **v0.9 / Beta 3**, technische Firmware-Version **`v4.0.0-beta.3`**. Firmware, Prüfsummen und Build-Informationen findest du im **[Beta-3-Release](https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0-beta.3)**.

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
| **Entwicklungswerkzeuge** | Separater Arduino-CLI-Build mit festgelegtem cache64-SDK, Tests auf dem Computer, synthetische MQTT-Daten sowie Grafik- und Schriftgeneratoren. |

Das Profil verwendet `BAMBU_MONITOR_ONLY=0` und enthält auch die Steuerung der Bauraumbeleuchtung und intelligenter Steckdosen. Andere Platinen, Druckermodelle und Konfigurationen mit mehreren Druckern wurden in diesem Projekt noch nicht vollständig geprüft.

## Installation und Updates

### Erste Installation über USB

1. Öffne den **[BambuHelper-Installer](https://honzo90.github.io/BambuHelper/)** in Chrome oder Edge auf einem Computer. Die USB-Installation funktioniert nicht auf dem iPhone.
2. Verbinde das Panel mit einem USB-Kabel, das Datenübertragung unterstützt. Der Installer ist ausschließlich für das **Waveshare ESP32-S3-Touch-LCD-4.3B** vorgesehen.
3. Bestätige das genaue Platinenmodell und das Löschen der Einstellungen. Wähle auf der derzeit polnischen Installationsseite **„Przygotuj instalację“** (Installation vorbereiten), danach **„Połącz i zainstaluj“** (Verbinden und installieren).
4. Richte nach dem Neustart das WLAN über das Netzwerk des Panels ein. Die Verbindungsdaten erscheinen auf dem Display.
5. Der USB-Installer installiert weiterhin **Beta 2**. Wechsle anschließend im WebUI zum Kanal **Beta**, suche nach Updates und installiere **Beta 3**. Danach kannst du **Deutsch** im Menü oder WebUI auswählen.

**Die erste USB-Installation löscht den Flash-Speicher einschließlich WLAN-Einstellungen, Druckerkonfiguration und bisheriger Firmware.** Die Seite prüft das Firmwareabbild, bevor sie die Installation freigibt. Der vollständige Installationsvorgang über den Browser ist noch nicht durch einen Test an einer physischen Platine bestätigt.

### Vorhandenes Panel per OTA aktualisieren

- **Beta 1 oder Beta 2 → Beta 3:** Im WebUI den Kanal **Beta** wählen, nach Updates suchen und die angebotene Version installieren.
- **Alpha → Beta 3:** Einmalig das manuelle Firmware-Update im WebUI verwenden und die Datei **`BambuHelper-ws_lcd_43b-v4.0.0-beta.3-ota.bin`** hochladen.
- Firmware und zugehörige Quellen: **[Beta 3 herunterladen](https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0-beta.3)** · [Alle Releases](https://github.com/honzo90/BambuHelper/releases).

OTA setzt das vorhandene WS43B-Partitionslayout mit **zwei Slots zu je 3 MiB** voraus. Die OTA-Datei enthält nur die Anwendung und eignet sich nicht für die Erstinstallation. Beim erneuten Öffnen der Aktualisierungsseite ist wieder der Kanal **Stable** ausgewählt; Beta muss bewusst gewählt werden.

## Entwicklungsstand

**Rückmeldung vom Gerät:** Am **24.10.2026** bestätigte der Projektbetreiber, dass das deutsche Menü und die deutsche WebUI unter Beta 3 auf seinem WS43B funktionieren. Diese Rückmeldung ersetzt keine Langzeitprüfung des Displays, des Touchscreens oder des Aufweckverhaltens.

Der bekannte [Fehler mit dunklem Bildschirm und fehlendem Aufwecken per Touch](https://github.com/honzo90/BambuHelper/issues/1) bleibt **offen**. Seine Ursache ist noch nicht geklärt. Eine vollständige Prüfung über einen gesamten Druckzyklus steht weiterhin aus; die Sprachergänzung ist keine Behebung dieses Fehlers.

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

Beginne mit den englischen **[Waveshare-Build- und Testhinweisen](WAVESHARE.md)**. Das Profil [`boards/ws_lcd_43b.ini`](boards/ws_lcd_43b.ini) verwendet **Arduino ESP32 3.3.11** und das SDK-Profil **cache64**. Der Build wird über [`bringup/waveshare43b/integration/build.py`](bringup/waveshare43b/integration/build.py) ausgeführt:

```sh
python3 -B bringup/waveshare43b/integration/build.py
```

Dies ist ein eigener Arduino-CLI-Build, keine PlatformIO-Umgebung. Der Befehl baut die Firmware und schreibt sie nicht auf das Gerät.

Die veröffentlichte Quellcodebasis wurde am **18. Oktober 2026** auf macOS aus einem frischen Klon erfolgreich gebaut. Details und Umfang der Tests auf dem Computer stehen in [WAVESHARE.md](WAVESHARE.md#host-tests); die Nachweise für Beta 3 enthält deren [Release](https://github.com/honzo90/BambuHelper/releases/tag/v4.0.0-beta.3). Ein erfolgreicher Build und Host-Tests ersetzen keine Hardwareprüfung.

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
