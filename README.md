# PowerGateway

PowerGateway ist ein modulares Raspberry-Pi- und Debian-Gateway für digitale Stromzähler. Pro Installation wird genau eine aktive Zählerquelle eingelesen, normiert und per MQTT an Home Assistant übertragen.

## Aktueller Stand

Entwicklungszweig: `feature/ui-redesign-1.0`

Aktuelle Entwicklungsversion: **1.3.7-dev**

Der Versionsstand in `version.txt` ist verbindlich. PowerGateway befindet sich weiterhin in Entwicklung. Reale Hardware-, Update-, Backup-, Restore- und Langzeittests müssen vor einer stabilen Freigabe abgeschlossen werden.

## Vorhandene Funktionen

- USB-SML mit Geräteerkennung, Verbindungstest und OBIS-Auswertung
- Tasmota MQTT und Generic MQTT
- Simulation für Tests
- MQTT-Assistent mit TLS, Topic-Suche und JSON-Feldvorschlägen
- Home-Assistant-Discovery
- lokaler MQTT-Puffer mit Nachsendung
- LAN, WLAN, LTE und Setup-Hotspot
- Netzwerkpriorität LAN → WLAN → LTE → Hotspot
- Unterstützung des ZTE MF833U1 im USB-Ethernet-Modus
- WireGuard mit Server-, Client- und Peer-Verwaltung
- SSH- und Reverse-SSH-Tunnel
- No-IP-DDNS mit IPv4 und IPv6
- zentrale Systemübersicht und Diagnose
- LTE-Signaldiagnose und Speedtest
- lokale Energiehistorie
- Export-Center
- Backup-/Restore-Grundlage
- lokale WebGUI
- systemd-Dienste und Debian-Paketbau

## Zielhardware

- Raspberry Pi 3B+ oder neuer
- Raspberry Pi OS Lite 64 Bit oder Debian
- optional USB-SML-Lesekopf
- optional Tasmota-WLAN-Lesekopf
- optional LTE-USB-Modem

## Datenquellen

- USB-SML
- Tasmota MQTT
- Generic MQTT
- Simulation

Es ist immer genau eine Datenquelle aktiv.

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
git checkout feature/ui-redesign-1.0
sudo bash install.sh
```

Danach:

```bash
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
```

Die WebGUI ist je nach Installation erreichbar unter:

```text
http://IP-DES-GERÄTS
```

oder direkt über gunicorn:

```text
http://IP-DES-GERÄTS:8080
```

## Aktualisierung

Vor dem Update ein Backup erstellen.

```bash
cd ~/PowerGateway
git checkout feature/ui-redesign-1.0
git pull --ff-only
sudo bash install.sh
```

## Dokumentation

- [Dokumentationsübersicht](docs/README.md)
- [Projektbeschreibung](docs/PROJECT.md)
- [Installationsanleitung](INSTALLATION.md)
- [Administratorhandbuch](docs/ADMIN_GUIDE.md)
- [Benutzerhandbuch](docs/USER_GUIDE.md)
- [Entwicklerhandbuch](docs/DEVELOPER_GUIDE.md)
- [Raspberry-Pi-Installation](docs/installation/RaspberryPi.md)
- [Home Assistant](docs/installation/HomeAssistant.md)
- [MQTT](docs/configuration/MQTT.md)
- [USB-SML](docs/configuration/USB-SML.md)
- [Roadmap](docs/roadmap/ROADMAP.md)
- [Änderungsprotokoll](CHANGELOG.md)
- [Einstieg für einen neuen Chat](NEUER_CHAT.md)

## Projektaufteilung

PowerGateway übernimmt:

- Zählerwerte einlesen
- Werte normieren
- MQTT-Ausgabe
- Home-Assistant-Discovery
- Netzwerk, LTE, Hotspot und WireGuard
- SSH-/Reverse-SSH-Verbindungen
- No-IP-DDNS
- lokale Diagnose, Energiehistorie, Export und Sicherung

Home Assistant übernimmt bevorzugt:

- Energie-Dashboard
- umfassende Langzeitdiagramme
- Automationen
- Benachrichtigungen
- standortübergreifende Auswertungen

## Typische Pfade

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- TLS: `/etc/powergateway/tls`
- Laufzeitdaten: `/var/lib/powergateway`
- Exportarchiv: `/var/lib/powergateway/exports`
- Hauptdienst: `powergateway.service`
- WebGUI: `powergateway-web.service`
- interner Web-Port: `8080`
- interner LTE-Proxy: `8081`
- nginx: `80` und optional `443`

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Hardwareabhängige Funktionen müssen zusätzlich auf realer Zielhardware geprüft werden.

## Noch vor einer stabilen Freigabe zu erledigen

- reale USB-SML-Tests
- MQTT- und Home-Assistant-Discovery-Tests
- LAN/WLAN/LTE/Hotspot-Failover
- WireGuard- und SSH-Tunnel-Tests
- Backup- und Restore-Test
- Debian-Installations- und Update-Test
- Langzeittest auf Raspberry Pi 3B+
- Sicherheits- und Rechteprüfung

## Lizenz

Die Lizenz wird vor der ersten stabilen Veröffentlichung verbindlich festgelegt.
