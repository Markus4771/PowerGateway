# Neuer Chat – PowerGateway

Arbeite am GitHub-Projekt `Markus4771/PowerGateway`.

## Verbindlicher Arbeitszweig

Bevorzugter Entwicklungszweig:

```text
feature/ui-redesign-1.0
```

Vor Änderungen prüfen, ob dieser Zweig weiterhin aktuell ist und ob dort unübernommene Änderungen liegen.

## Verbindliche Reihenfolge

1. Lies `CHATGPT_PROJEKTKONTEXT.md`.
2. Lies `version.txt`, `README.md`, `CHANGELOG.md` und `docs/roadmap/ROADMAP.md`.
3. Lies `docs/PROJECT.md` und `docs/DEVELOPER_GUIDE.md`.
4. Prüfe anschließend den tatsächlichen Quellcode und die letzten Commits.
5. Bestätige zuerst Version, Ist-Stand, Branch und offene Aufgaben.
6. Entwickle ausschließlich auf Basis des aktuellen GitHub-Stands weiter.
7. Aktualisiere bei jeder Änderung Tests, Dokumentation und Changelog.

## Projektziel

PowerGateway ist ein modulares Raspberry-Pi- und Debian-Gateway für genau einen digitalen Stromzähler. Es liest eine aktive Quelle ein, normiert die Werte und überträgt sie per MQTT an Home Assistant.

## Zielhardware

- Raspberry Pi 3B+ oder neuer
- Raspberry Pi OS Lite 64 Bit oder Debian
- optional USB-SML-Lesekopf
- optional Tasmota-WLAN-Lesekopf
- optional ZTE MF833U1 oder vergleichbares LTE-Gerät

## Netzwerkpriorität

```text
LAN → WLAN → LTE → Setup-Hotspot
```

Standard-Hotspot:

```text
SSID: PowerGateway-Setup
Adresse: 192.168.50.1
Netz: 192.168.50.0/24
```

## Typische Betriebsdaten

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- TLS: `/etc/powergateway/tls`
- Laufzeitdaten: `/var/lib/powergateway`
- Exporte: `/var/lib/powergateway/exports`
- Hauptdienst: `powergateway.service`
- Webdienst: `powergateway-web.service`
- gunicorn intern: Port `8080`
- LTE-Proxy intern: Port `8081`
- nginx: Port `80` und optional `443`

## Projektgrundsätze

- GitHub ist die verbindliche Quelle.
- Modularer Aufbau.
- Konfiguration statt Programmierung.
- Raspberry Pi und Debian als Hauptziele.
- Genau eine aktive Zählerquelle.
- Home Assistant übernimmt umfassende Langzeitvisualisierung und Automationen.
- Keine Zugangsdaten, privaten Schlüssel oder produktiven Zertifikate ins Repository eintragen.
- Änderungen müssen dokumentiert, getestet und versioniert werden.
- Entwicklungsfunktionen nicht als produktionsreif bezeichnen, bevor reale Tests abgeschlossen sind.

## Vorhandene Funktionsbereiche

- USB-SML, Tasmota MQTT, Generic MQTT und Simulation
- SML-/OBIS-Auswertung
- MQTT-Assistent und Home-Assistant-Discovery
- LAN, WLAN, LTE und Setup-Hotspot
- WireGuard
- SSH- und Reverse-SSH-Tunnel
- No-IP mit IPv4 und IPv6
- Systemübersicht und Diagnose
- LTE-Signaldiagnose und Speedtest
- Energiehistorie
- Export-Center
- Backup-/Restore-Grundlage
- Debian-Paket und systemd-Dienste

## Aktuelle Dokumentation

- `docs/README.md`
- `docs/PROJECT.md`
- `INSTALLATION.md`
- `docs/ADMIN_GUIDE.md`
- `docs/USER_GUIDE.md`
- `docs/DEVELOPER_GUIDE.md`
- `CHANGELOG.md`

## Nächste technische Schwerpunkte

1. tatsächlichen Versionsstand und letzte Commits verifizieren
2. Dokumentation gegen den Quellcode prüfen
3. USB-SML auf realer Hardware testen
4. MQTT und Home-Assistant-Discovery praktisch testen
5. LAN/WLAN/LTE/Hotspot-Failover testen
6. WireGuard und SSH-Tunnel testen
7. Backup und Wiederherstellung vollständig testen
8. Debian-Installation, Update und Deinstallation testen
9. Langzeittest auf Raspberry Pi 3B+ durchführen
10. erst danach stabile Release-Kandidaten vorbereiten
