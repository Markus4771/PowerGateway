# PowerGateway – Einstieg für neue Chats

> **Wichtig:** Diese Datei ist der zentrale Einstiegspunkt für die Weiterentwicklung des Projekts. Vor jeder Entwicklungsarbeit oder bei einem neuen Chat bitte zuerst diese Datei lesen.

## Projektinformationen

| Eigenschaft | Wert |
|---|---|
| Projektname | PowerGateway |
| Repository | Markus4771/PowerGateway |
| Lizenz | GPL v3 |
| Status | Aktiv |
| Zielsystem | Debian Linux |
| Programmiersprache | Python 3 |
| Webserver | nginx |
| Application Server | gunicorn |
| Entwicklungsbranch | `feature/ui-redesign-1.0` |

## Projektziel

PowerGateway ist eine modulare Gateway-Software zur Erfassung, Verarbeitung und Übertragung von Energiedaten. Die Software soll auf kostengünstiger Hardware wie einem Raspberry Pi laufen und eine zuverlässige Kommunikation zwischen Stromzähler und Zielsystemen ermöglichen.

Schwerpunkte:

- einfache Installation
- hohe Stabilität
- modularer Aufbau
- einfache Erweiterbarkeit
- langfristige Wartbarkeit
- sichere Übertragung über MQTT und WireGuard
- Anbindung an Home Assistant

## Architekturgrundsätze

- Modularer Aufbau
- Konfiguration statt Programmierung
- Plugin-System für Erweiterungen
- Möglichst geringe Abhängigkeiten
- Debian-Kompatibilität
- Neue Ideen zunächst unter `docs/backlog/` dokumentieren
- GitHub ist das führende Repository

## Unterstützte Hardware

- Raspberry Pi 3B+
- USB-IR-Lesekopf
- ZTE MF833U1 LTE-Stick
- Tasmota-LAN-Geräte
- WLAN-IR-Lesekopf

Weitere Hardware soll zukünftig über Plugins integriert werden.

## Netzwerkpriorität

1. LAN
2. WLAN
3. LTE
4. Hotspot

Unterstützte beziehungsweise vorgesehene Dienste:

- MQTT
- WireGuard
- Home Assistant
- No-IP
- lokaler Hotspot für die Ersteinrichtung

## Systemarchitektur

Das Projekt besteht aus eigenständigen Modulen und Diensten, unter anderem:

- WebGUI
- MQTT
- LTE
- WireGuard
- Pluginverwaltung
- Energiehistorie
- Diagnose
- Logging
- Updateverwaltung
- Onboarding
- Netzwerkverwaltung

Aktuelle Dienststruktur:

- nginx auf Port 80/443
- gunicorn auf Port 8080
- LTE-Proxy auf Port 8081
- TLS-Dateien unter `/etc/powergateway/tls`

## Installationsart

Die bevorzugte Installationsform ist ein Debian-Paket mit:

- systemd
- nginx
- gunicorn
- Python 3

## Repository-Struktur

```text
docs/
├── architecture/
├── api/
├── backlog/
└── developer/

hardware/
examples/
tests/
diagnostics/
compatibility/
.github/
```

Die tatsächliche Quellcode-Struktur im Repository ist vor Änderungen immer zu prüfen.

## Übergabe: aktueller Stand 1.5.2-dev (2026-11-11)

**Verbindliche Quelle:** GitHub-Branch `feature/ui-redesign-1.0`; Version immer mit `version.txt` abgleichen. Die Angaben in älteren Abschnitten dieser Datei sind historische Projektinformationen und können veraltet sein.

### Zuletzt umgesetzte Funktionen und Korrekturen

- USB-SML-Zähler Iskra/Iskraemeco MT691: Telegramme und OBIS-Dekodierung wurden anhand exportierter Messwerte nachgewiesen. `1-0:16.7.0*255` liefert die Momentanleistung (`power_total`, W), `1-0:1.8.0*255` den Bezug (`energy_import`, kWh), `1-0:2.8.0*255` die Einspeisung (`energy_export`, kWh).
- `src/sml_live_runtime.py` ergänzt dekodierte Messwerte im Hauptdienst ohne zweiten seriellen Leser und schreibt `/var/lib/powergateway/latest_values.json`; `src/service_runtime.py` aktiviert die Integration.
- `src/power_dashboard_v152.py` erweitert die Leistungszuordnung um `power_total` und den vollständigen OBIS-Code und stellt `GET /_internal/power/live` bereit.
- `src/measurement_export_streaming.py` stellt den speicherschonenden CSV-Streaming-Endpunkt `/_internal/measurements/export-stream.csv` bereit. Hintergrund war ein gemeldeter `NetworkError when attempting to fetch resource` bei größeren Exporten.
- `src/energy_history_management.py` ermöglicht das gezielte Löschen historischer Daten nach Von/Bis mit Bestätigung `HISTORIE LÖSCHEN` und automatischer Sicherung vor dem Löschen.
- `src/energy_chart_final_renderer.py` enthält den interaktiven Diagramm-Renderer mit Zoom, Verschieben und Zurücksetzen. Die ältere statische Überschreibung des Renderers war Ursache des gemeldeten Zoom-Problems.
- `src/plugin_webapp.py` bindet die genannten Webmodule ein. `README.md` und `CHANGELOG.md` wurden auf 1.5.2-dev nachgezogen.

**Wichtig:** Diese Änderungen wurden in GitHub eingetragen; ein vollständiger erfolgreicher Laufzeit-, Browser- und Hardwaretest der Version 1.5.2-dev auf dem Raspberry Pi ist noch **nicht bestätigt**. Daher keine Produktionsreife oder vollständige Fehlerfreiheit behaupten.

### Nächste Priorität: Praxis- und Regressionstests

1. Webdienst nach Installation auf Import-/Startfehler prüfen.
2. Momentanleistung im Dashboard mit `latest_values.json`, `status.json` und der OBIS-Ausgabe vergleichen.
3. Diagramm-Zoom per Mausrad, Bedienelementen und Zeitraumauswahl testen.
4. CSV-Export mit großem Datensatz und allen Messwerten auf Abbruch und Vollständigkeit prüfen.
5. Historien-Löschen ausschließlich mit einem **entbehrlichen Testzeitraum** prüfen; Backup und Ergebnis kontrollieren.
6. Danach weitere Fehler beheben, Tests ergänzen und Versionsnummer erhöhen.

### Installation / Update auf Raspberry Pi

Vor dem Update Konfiguration und Betriebsdaten sichern. `git reset --hard` verwirft lokale, nicht gesicherte Änderungen im Repository.

```bash
cd ~/PowerGateway
git fetch origin
git switch feature/ui-redesign-1.0
git reset --hard origin/feature/ui-redesign-1.0
sudo bash install.sh
sudo systemctl restart powergateway.service
sudo systemctl restart powergateway-energy-history.service
sudo systemctl restart powergateway-web.service
cat /opt/powergateway/version.txt
```

Erwartete Version: `1.5.2-dev`. Anschließend Weboberfläche mit Strg+F5 neu laden.

### Fehlerdiagnose

```bash
sudo systemctl status powergateway.service powergateway-web.service powergateway-energy-history.service --no-pager -l
sudo journalctl -u powergateway-web.service -n 120 --no-pager
sudo journalctl -u powergateway.service -n 120 --no-pager
sudo cat /var/lib/powergateway/latest_values.json
sudo cat /var/lib/powergateway/status.json
sudo sqlite3 /var/lib/powergateway/energy_history.sqlite3 "SELECT datetime(ts,'unixepoch','localtime'),power_w,energy_kwh FROM measurements ORDER BY ts DESC LIMIT 10;"
```

Wichtige Datenpfade: `/var/lib/powergateway/energy_history.sqlite3`, `/var/lib/powergateway/measurement_history.jsonl`, `/var/lib/powergateway/latest_values.json`, `/var/lib/powergateway/status.json`.

### Arbeitsanweisung für den nächsten KI-Chat

Bitte **zuerst** `NEUER_CHAT.md`, `version.txt`, `README.md`, `CHANGELOG.md` und die betroffenen Quellcodedateien **im Branch** `feature/ui-redesign-1.0` lesen. Nicht ungeprüft den Default-Branch verwenden. Bestehende Funktionen, Historie und Konfiguration erhalten. Fehler anhand aktueller Logs und Dateien nachvollziehen, dann möglichst kleine Änderungen durchführen, testen, dokumentieren und committen. Nach jedem GitHub-Update die Commit-SHA nennen. Bei fehlenden Raspberry-Pi-Testergebnissen diese ausdrücklich anfordern.

## Aktueller Entwicklungsstand

Aktueller Schwerpunkt:

1. Software vollständig testen
2. Fehler beheben
3. Stabilität verbessern
4. anschließend Dokumentation vervollständigen
5. stabilen Release vorbereiten

Bereits umgesetzt beziehungsweise vorhanden:

- WebGUI
- modulare Grundstruktur
- MQTT-Unterstützung
- WireGuard-Funktionen
- Energiehistorie
- Diagnosefunktionen
- Plugin-Laufzeit und Modulverwaltung
- Ereignisdiagnose
- öffentliche Plugin-Registrierung
- Debian- und systemd-Integration
- Repository-Grundstruktur
- GPL-v3-Lizenz

## Wichtige zuletzt behobene Fehler

### Energiehistorie

Die Historie blieb leer, obwohl Live-Werte vorhanden waren.

Ursache:

- `energy_history_runner.py` erwartete veraltete Schlüssel beziehungsweise Dateien.

Lösung:

- Verwendung von `latest_values.json`
- Mapping `power_total` → `power_w`
- Mapping `energy_import` → `energy_kwh`

Zugehöriger Commit:

```text
8c37e2db0bdacc32d8729e936aa7ea0ce48f8bb9
```

Der Fehler wurde anschließend erfolgreich getestet.

## Bekannte offene Punkte

- LTE-Erkennung des ZTE MF833U1 weiter prüfen
- Hotspot-Funktion vollständig testen
- Netzwerk-Fallback LAN → WLAN → LTE → Hotspot testen
- WireGuard-Konfiguration und Verbindungsstatus prüfen
- MQTT-Konfiguration und Übertragung testen
- Home-Assistant-Anbindung testen
- Installation und Update über Debian-Paket testen
- WebGUI vollständig auf Bedienbarkeit prüfen
- Diagnose- und Logfunktionen vervollständigen
- TLS- und nginx-Konfiguration testen
- Dokumentation nach der Stabilisierung vervollständigen

## Dokumentation

Geplante beziehungsweise vorhandene zentrale Dokumente:

- `README.md`
- `PROJECT.md`
- `NEUER_CHAT.md`
- `INSTALLATION.md`
- `CHANGELOG.md`
- `ROADMAP.md`
- `BACKLOG.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `LICENSE`

Nicht vorhandene Dokumente dürfen in einem neuen Chat nicht einfach als vorhanden angenommen werden. Zuerst immer das Repository prüfen.

## Entwicklungsregeln

Vor Änderungen:

1. aktuellen Branch prüfen
2. letzten Commit prüfen
3. bestehende Architektur analysieren
4. vorhandene Funktionen nicht unbeabsichtigt entfernen
5. Änderungen möglichst klein und nachvollziehbar halten

Vor jedem Commit:

- Änderungen testen
- Fehlerbehandlung prüfen
- Dokumentation bei Bedarf aktualisieren
- Versionsnummer prüfen
- Changelog bei Release-relevanten Änderungen ergänzen

Nach jedem größeren Entwicklungsschritt:

- Änderungen nach GitHub übertragen
- `NEUER_CHAT.md` aktualisieren
- bekannte Fehler und nächste Aufgaben aktualisieren

## GitHub-Regeln

Repository:

```text
Markus4771/PowerGateway
```

Bevorzugter Entwicklungsbranch:

```text
feature/ui-redesign-1.0
```

Arbeitsablauf:

1. bestehenden Stand lesen
2. entwickeln
3. testen
4. Dokumentation aktualisieren
5. committen
6. nach GitHub übertragen

Nach einem GitHub-Schreibvorgang immer die Commit-SHA nennen.

## Ablauf für neue Chats

1. `NEUER_CHAT.md` lesen
2. aktuellen Repository-Stand prüfen
3. `README.md` lesen
4. vorhandene Projekt- und Installationsdokumentation prüfen
5. letzte Commits ansehen
6. bekannte Fehler prüfen
7. aktuelle Prioritäten bestätigen
8. Entwicklung an der höchsten Priorität fortsetzen

Empfohlener Startsatz:

> Bitte lies zuerst die `NEUER_CHAT.md` im Repository `Markus4771/PowerGateway` und setze die Entwicklung auf dem aktuellen Branch fort.

## Hinweise für ChatGPT und weitere Entwickler

- keine Architekturänderungen ohne nachvollziehbare Begründung
- modularen Aufbau beibehalten
- neue Funktionen bevorzugt als Module oder Plugins entwickeln
- Debian-Kompatibilität sicherstellen
- Raspberry Pi 3B+ als wichtige Zielplattform berücksichtigen
- keine unnötigen Abhängigkeiten einführen
- bestehende Daten und Konfigurationen bei Updates schützen
- neue Ideen zunächst im Backlog dokumentieren
- bei Unsicherheit zuerst den aktuellen Repository-Inhalt prüfen
- keine Dateien, Versionen oder Commits erfinden

## Änderungsverlauf

| Version | Datum | Änderung |
|---|---|---|
| 1.0 | 2026-07-29 | Einführung von `NEUER_CHAT.md` als zentralem Einstieg für neue Chats |

Diese Datei ist ein lebendes Übergabedokument und soll bei größeren Änderungen, neuen Releases oder geänderten Prioritäten aktualisiert werden.
