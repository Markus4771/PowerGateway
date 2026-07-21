# Änderungsprotokoll

## 0.3.0-dev – 2026-07-21

- modulare SML-/OBIS-Auswertung ergänzt
- bekannte OBIS-Kennzahlen für Bezug, Einspeisung, Leistung, Spannung, Strom und Frequenz definiert
- Skalierung und Einheiten der Messwerte werden normiert
- Energieangaben werden für Home Assistant von Wh nach kWh umgerechnet
- Messwerte werden zusätzlich unter `meter/values` veröffentlicht
- Home-Assistant-Discovery für Zähler- und Phasensensoren ergänzt
- eigenständiges Werkzeug `scripts/decode_sml.py` zum Prüfen aufgezeichneter Telegramme ergänzt
- automatisierte Tests für bekannte und unbekannte OBIS-Werte ergänzt
- modularer Dienststarter `src/service.py` aktiviert

## 0.2.0-dev – 2026-07-21

- serielle SML-Rahmenerkennung implementiert
- MQTT-Publisher und Home-Assistant-Discovery ergänzt
- Offline-Pufferung mit SQLite und automatisches Nachsenden umgesetzt
- LTE- und WireGuard-Statusprüfung ergänzt
- maschinenlesbare Statusdatei und Diagnoseskript ergänzt
- automatisierte Tests und GitHub-Actions-Workflow ergänzt

## 0.1.0-dev – 2026-07-21

- Projekt PowerGateway initialisiert
- Zielhardware Raspberry Pi 3B+, USB-IR-Lesekopf und ZTE MF833 festgelegt
- Projekt- und Installationsstruktur begonnen
- Konfigurations- und Dienstgrundlage vorbereitet
