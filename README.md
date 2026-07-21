# PowerGateway

PowerGateway ist ein modulares Raspberry-Pi- und Debian-Gateway für digitale Stromzähler. Es liest genau eine aktive Zählerquelle ein und überträgt die Messwerte per MQTT an Home Assistant.

## Aktueller Stand

Entwicklungsversion: **0.9.7-dev**

Vorhanden sind:

- USB-SML-Grundlage mit Geräteerkennung
- Tasmota MQTT und Generic MQTT
- MQTT-Assistent mit Verbindungstest, Topic-Suche und JSON-Feldvorschlägen
- Home-Assistant-Discovery-Grundlage
- LAN, WLAN, LTE und Setup-Hotspot
- WireGuard-Grundlage
- lokale WebGUI
- einfache Benutzerverwaltung
- Einrichtungsstatus und Systemdiagnose
- systemd-Dienste und Installer

Der aktuelle Stand ist noch nicht als stabile Version freigegeben. Reale USB-SML-Geräte, Home Assistant, Netzwerk-Failover, LTE und WireGuard müssen weiter praktisch getestet werden.

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
- HTTP später

Es ist immer genau eine Datenquelle aktiv.

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

Danach:

```bash
sudo systemctl status powergateway --no-pager -l
sudo systemctl status powergateway-web --no-pager -l
```

Die WebGUI ist standardmäßig erreichbar unter:

```text
http://IP-DES-GERÄTS:8080
```

## Aktualisierung

```bash
cd ~/PowerGateway
git pull
sudo bash install.sh
```

## Dokumentation

- [Installation auf Raspberry Pi](docs/installation/RaspberryPi.md)
- [Home Assistant anbinden](docs/installation/HomeAssistant.md)
- [MQTT konfigurieren](docs/configuration/MQTT.md)
- [USB-SML konfigurieren](docs/configuration/USB-SML.md)
- [Roadmap](docs/roadmap/ROADMAP.md)
- [Projektkontext](CHATGPT_PROJEKTKONTEXT.md)
- [Einstieg für einen neuen Chat](NEUER_CHAT.md)

## Projektaufteilung

PowerGateway übernimmt:

- Zählerwerte einlesen
- Werte normieren
- MQTT-Ausgabe
- Home-Assistant-Discovery
- Netzwerk, LTE, Hotspot und WireGuard
- Einrichtung, Status und Diagnose

Home Assistant übernimmt:

- Diagramme
- Energie-Dashboard
- Tages-, Monats- und Jahresauswertungen
- Langzeitstatistiken
- Automationen und Benachrichtigungen

## Typische Pfade

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- Laufzeitdaten: `/var/lib/powergateway`
- Hauptdienst: `powergateway.service`
- WebGUI: `powergateway-web.service`

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Bewusst nicht enthalten

- lokale Diagramme und Langzeitstatistiken
- öffentliche REST-API
- automatische Softwareupdates
- integrierte Backup- und Wiederherstellungsverwaltung
- komplexe Rollenverwaltung
- Batterie-, Wallbox- oder EMS-Steuerung

## Lizenz

Die Lizenz wird vor der ersten stabilen Veröffentlichung festgelegt.