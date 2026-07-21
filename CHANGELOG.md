# Änderungsprotokoll

## 0.9.9-dev – 2026-07-21

- Entwicklungsversion auf 0.9.9-dev erhöht
- sicheres Deinstallationsskript ergänzt
- Standard-Deinstallation behält Konfiguration und Betriebsdaten
- vollständige Entfernung über `uninstall.sh --purge` ergänzt
- Debian-Paketbau über `packaging/build_deb.sh` vorbereitet
- Paket-Metadaten, Abhängigkeiten und Maintainer-Skripte ergänzt
- bestehende Konfiguration wird bei Paketupdates erhalten
- systemd-Dienste werden durch das Debian-Paket eingerichtet und verwaltet
- Anleitung für Paketbau, Installation, Update und Deinstallation ergänzt

## 0.9.8-dev – 2026-07-21

- USB-SML-Verbindungstest in der WebGUI ergänzt
- automatische Prüfung üblicher Baudratenprofile vorbereitet
- vollständige SML-Frames werden erkannt und ausgewertet
- erkannte Messwerte und unbekannte OBIS-Kennzahlen werden im Test angezeigt
- verständliche Fehlermeldungen für fehlende Geräte, Rechte und Telegramme ergänzt
- Home-Assistant-Discovery-Vorschau ergänzt
- Discovery kann manuell veröffentlicht oder gelöscht werden
- Availability wird beim manuellen Veröffentlichen gesetzt
- Status der PowerGateway-Dienste wird in der WebGUI angezeigt
- Journal-Protokolle können über die Diagnoseoberfläche gelesen werden
- Installer ergänzt den Dienstbenutzer um Journal-Leserechte, sofern verfügbar

## 0.9.7-dev – 2026-07-21

- MQTT-Assistent ergänzt
- echte MQTT-Anmeldung mit Benutzername und Passwort
- TLS- und CA-Unterstützung
- Topic-Erkennung über abonnierte MQTT-Nachrichten
- Live-Nachrichten und JSON-Vorschau
- automatische Vorschläge für Leistung, Bezug und Einspeisung
- vollständige GitHub-Dokumentationsstruktur begonnen
- README, Roadmap, Installations- und Konfigurationsanleitungen aktualisiert
- Projektkontext und Einstieg für neue Chats ergänzt
- festgelegt, dass Diagramme und Langzeitauswertungen in Home Assistant erfolgen

## 0.9.6-dev – 2026-07-21

- Einrichtungsstatus in der WebGUI ergänzt
- USB-SML-Geräteerkennung ergänzt
- Hardware- und Systemdiagnose ergänzt
- Einrichtungs- und Diagnosemodule in Installer und WebGUI eingebunden

## 0.9.5-dev – 2026-07-21

- WireGuard-Konfiguration, Anwendung und Statusdienst ergänzt
- WireGuard-Weboberfläche eingebunden
- systemd-Dienste und Installer erweitert

## 0.8.0-dev – 2026-07-21

- modulares Datenquellen-Framework
- USB-SML, Simulation und Tasmota MQTT als Quellen
- Laufzeitkonfiguration und WebGUI erweitert
- Netzwerkverwaltung für LAN, WLAN, LTE und Hotspot
- einfache Benutzerverwaltung und Ersteinrichtung

## 0.3.0-dev – 2026-07-21

- modulare SML-/OBIS-Auswertung ergänzt
- bekannte OBIS-Kennzahlen für Bezug, Einspeisung, Leistung, Spannung, Strom und Frequenz definiert
- Skalierung und Einheiten der Messwerte normiert
- Energieangaben für Home Assistant von Wh nach kWh umgerechnet
- Home-Assistant-Discovery für Zähler- und Phasensensoren ergänzt
- Werkzeug `scripts/decode_sml.py` zum Prüfen aufgezeichneter Telegramme ergänzt
- automatisierte Tests für bekannte und unbekannte OBIS-Werte ergänzt

## 0.2.0-dev – 2026-07-21

- serielle SML-Rahmenerkennung implementiert
- MQTT-Publisher und Home-Assistant-Discovery ergänzt
- Offline-Pufferung mit SQLite und automatisches Nachsenden umgesetzt
- LTE- und WireGuard-Statusprüfung ergänzt
- maschinenlesbare Statusdatei und Diagnoseskript ergänzt
- automatisierte Tests und GitHub-Actions-Workflow ergänzt

## 0.1.0-dev – 2026-07-21

- Projekt PowerGateway initialisiert
- Zielhardware Raspberry Pi 3B+, USB-IR-Lesekopf und LTE festgelegt
- Projekt- und Installationsstruktur begonnen
- Konfigurations- und Dienstgrundlage vorbereitet
