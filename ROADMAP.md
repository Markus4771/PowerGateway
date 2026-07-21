# Roadmap

## 0.9.10-dev – aktueller Entwicklungsstand

Umgesetzt:

- internes Ereignissystem mit abonnierbaren Ereignissen und begrenzter Historie
- konfigurationsbasierte Plugin-Grundlage
- Plugin-Lebenszyklus für Initialisierung, Start, Stop, Status und Diagnose
- Fehlerisolierung für optionale Plugins
- modularer Einrichtungsassistent mit fester Schrittfolge
- Pflicht- und optionale Einrichtungsschritte
- Fortschrittswert und Ermittlung des nächsten offenen Schritts
- zentrale Versionsausgabe aus `version.txt`
- Integration des Wizard-Zustands in den bestehenden Einrichtungsstatus

Noch offen in 0.9.10-dev:

- vollständige Wizard-Darstellung mit Vor/Zurück-Navigation in der WebGUI
- Plugin-Manager in den Hauptdienst-Lebenszyklus einbinden
- vorhandene Datenquellen schrittweise als Plugins registrieren
- veraltete Home-Assistant-Discovery-Einträge automatisch bereinigen
- Diagnose für LTE und Netzwerk-Failover erweitern
- Protokollfilter und begrenzte Diagnoseausgabe verbessern

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
- Debian-Paket final bauen und als Release-Artefakt bereitstellen
- Update und Deinstallation abschließend prüfen
- Dateirechte und systemd-Dienste härten
- Dokumentation vervollständigen
- Release-Test und Freigabe

## Später

- HTTP-Datenquelle
- Modbus, M-Bus, KNX, Shelly, Tasmota und ESPHome als optionale Module
- zusätzliche Diagnosewerkzeuge

## Nicht geplant

- lokale Diagramme und Langzeitstatistiken
- öffentliche REST-API
- automatische Updates
- Backup-Verwaltung
- Batterien, Wallboxen oder Energiemanagement
