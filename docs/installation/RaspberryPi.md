# Installation auf Raspberry Pi

## Voraussetzungen

- Raspberry Pi 3B+ oder neuer
- Raspberry Pi OS Lite 64 Bit
- Netzwerkzugang
- Benutzer mit `sudo`-Rechten
- optional USB-SML-Lesekopf, Tasmota-Lesekopf oder LTE-Stick

## Installation

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

## Dienste prüfen

```bash
sudo systemctl status powergateway --no-pager -l
sudo systemctl status powergateway-web --no-pager -l
```

## WebGUI öffnen

Im Browser:

```text
http://IP-DES-RASPBERRY:8080
```

Beim ersten Aufruf den Administrator einrichten und anschließend Netzwerk, Stromzähler, MQTT und Home Assistant konfigurieren.

## Aktualisierung aus GitHub

```bash
cd ~/PowerGateway
git pull
sudo bash install.sh
```

## Protokolle

```bash
sudo journalctl -u powergateway -n 100 --no-pager
sudo journalctl -u powergateway-web -n 100 --no-pager
```

## Typische Pfade

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- Laufzeitdaten: `/var/lib/powergateway`
- Hauptdienst: `powergateway.service`
- WebGUI: `powergateway-web.service`

## USB-Lesekopf prüfen

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

Der Dienstbenutzer muss Zugriff auf die serielle Schnittstelle haben. Nach Änderungen an Gruppenrechten ist ein Neustart sinnvoll.