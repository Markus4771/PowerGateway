# PowerGateway – Projektkontext

## Ziel

PowerGateway ist ein kompaktes, modulares Gateway für digitale Stromzähler auf Raspberry Pi und Debian. Es liest Messwerte aus einer aktiven Quelle ein und stellt sie über MQTT sowie Home-Assistant-Discovery bereit.

## Architekturgrundsätze

- GitHub ist die verbindliche Quelle.
- Modularer Aufbau für Datenquellen, Netzwerk und Ausgaben.
- Konfiguration statt Programmierung.
- Genau eine aktive Zählerquelle.
- Lokale WebGUI für Einrichtung, Status und Diagnose.
- Historische Diagramme, Energieauswertungen und Langzeitspeicherung erfolgen in Home Assistant.

## Unterstützte Datenquellen

- USB-SML
- Tasmota MQTT
- Generic MQTT
- Simulation
- HTTP ist für später vorgesehen.

## Ausgaben

- MQTT
- Home-Assistant-Discovery
- lokale Statusdateien
- kleine lokale Pufferung für Verbindungsunterbrechungen

## Netzwerk

Priorität: LAN → WLAN → LTE.

Zusätzlich:
- automatisches Failover
- Setup-Hotspot in den Modi `auto`, `always`, `off`
- WireGuard-Client

## WebGUI

- Dashboard
- Stromzähler
- MQTT und Home Assistant
- Netzwerk
- WireGuard
- Einrichtung
- Benutzer
- Diagnose

Die vorhandene einfache Benutzerverwaltung ist ausreichend. Eine komplexe Rollenverwaltung ist nicht geplant.

## Einrichtungsassistent

Geplante Reihenfolge:
1. Sprache
2. Benutzer
3. Netzwerk
4. Datenquelle
5. MQTT
6. Home Assistant
7. Abschlussprüfung

## Aktueller Stand

Entwicklungsversion: siehe `version.txt`.

Vorhanden:
- modulare Quellenstruktur
- USB-Geräteerkennung
- Tasmota- und Generic-MQTT-Konfiguration
- MQTT-Verbindungstest
- Topic-Erkennung
- JSON-Feldvorschläge
- Home-Assistant-Discovery-Grundlage
- Netzwerkverwaltung
- LTE-Grundlage
- WireGuard-Grundlage
- Einrichtungsstatus und Diagnose
- systemd-Dienste und Installer

## Offene Hauptaufgaben

- USB-SML mit realen Leseköpfen und Zählern vollständig testen und stabilisieren
- automatische Baudraten- und OBIS-Erkennung verbessern
- Home-Assistant-Discovery praktisch testen
- MQTT-Assistent mit realen Brokern testen
- Netzwerk-Failover, LTE, Hotspot und WireGuard testen
- geführten Einrichtungsassistenten abschließen
- Diagnose und Protokolle ausbauen
- Debian-Paket und Release 1.0.0 erstellen

## Bewusst nicht enthalten

- öffentliche REST-API
- automatische Updates
- Backup- und Wiederherstellungsverwaltung
- Batterie-, Wallbox- oder EMS-Steuerung
- lokale Diagramme und Langzeitstatistiken
- komplexe Mehrbenutzer- und Rollenverwaltung

## Arbeitsweise

Jede Änderung erhält:
- nachvollziehbaren Commit
- Aktualisierung der Versionsdatei bei Entwicklungsstufen
- Eintrag im Änderungsprotokoll
- Aktualisierung der betroffenen Dokumentation
- möglichst automatisierte Tests