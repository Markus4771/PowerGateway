# Roadmap

## 0.9.9-dev – aktueller Entwicklungsstand

- MQTT-Assistent mit Broker-Anmeldung, TLS, Topic-Suche und JSON-Feldvorschlägen
- USB-SML-Geräteerkennung und Verbindungstest
- SML-Frame- und OBIS-Auswertung in der WebGUI
- Home-Assistant-Discovery-Vorschau
- Discovery manuell senden und löschen
- Dienste und Systemprotokolle in der Diagnoseoberfläche
- Einrichtungsstatus
- WireGuard- und Netzwerkgrundlage
- sicheres Deinstallationsskript
- Debian-Paketbau mit Abhängigkeiten und Maintainer-Skripten
- Dokumentation für Paketbau, Update und Deinstallation

## 0.9.10-dev – Einrichtung und automatische Bereinigung

- geführten Einrichtungsassistenten als feste Schrittfolge abschließen
- veraltete Home-Assistant-Discovery-Einträge nach Konfigurationsänderungen automatisch bereinigen
- Diagnose für LTE und Netzwerk-Failover erweitern
- Protokollfilter und begrenzte Diagnoseausgabe verbessern
- Versionsangaben im laufenden Dienst vollständig zentralisieren

## 0.9.11-dev – Praxistests und Fehlerkorrekturen

- Discovery mit einer echten Home-Assistant-Installation prüfen
- Sensoren, Einheiten, Geräteklassen und Langzeitstatistiken prüfen
- Availability beim normalen Dienstbetrieb prüfen und härten
- LAN/WLAN/LTE-Failover prüfen
- Setup-Hotspot prüfen
- WireGuard-Client praktisch prüfen
- Neustart- und Fehlerverhalten prüfen
- USB-SML mit echten Zählermodellen und unterschiedlichen Leseköpfen prüfen
- Debian-Paket auf Raspberry Pi OS und Debian installieren und aktualisieren

## 1.0.0 – erste stabile Version

- offene Fehler aus den Praxistests beheben
- Installation auf sauberem Raspberry Pi OS und Debian freigeben
- Debian-Paket final bauen und signieren beziehungsweise als Release-Artefakt bereitstellen
- Update und Deinstallation abschließend prüfen
- Dateirechte und systemd-Dienste härten
- Dokumentation vervollständigen
- Release-Test und Freigabe

## Später

- HTTP-Datenquelle
- weitere konfigurierbare Datenquellenmodule
- zusätzliche Diagnosewerkzeuge

## Nicht geplant

- lokale Diagramme und Langzeitstatistiken
- öffentliche REST-API
- automatische Updates
- Backup-Verwaltung
- Batterien, Wallboxen oder Energiemanagement
