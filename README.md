# PowerGateway

PowerGateway ist ein schlankes Raspberry-Pi-Gateway zum Auslesen eines digitalen Stromzählers über einen USB-IR-Lesekopf und zur Übertragung der Messwerte per MQTT an einen zentralen Home Assistant.

## Zielhardware

- Raspberry Pi 3B+
- Raspberry Pi OS Lite 64 Bit
- USB-IR-Schreib-/Lesekopf (Weidmann-kompatibel)
- ZTE MF833 LTE Cat.4 USB-Dongle

## Geplante Funktionen

- automatische Erkennung des IR-Lesekopfs
- SML- und perspektivisch IEC-62056-21-Unterstützung
- MQTT-Übertragung inklusive Home-Assistant-Discovery
- LTE-Status und automatische Wiederverbindung
- optionale WireGuard-Anbindung
- lokale Pufferung bei Verbindungsunterbrechungen
- systemd-Dienst und Debian-Paket
- spätere Weboberfläche für Status und Konfiguration

## Aktueller Stand

Version `0.1.0-dev` – technische Grundstruktur.

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

Anschließend die Konfiguration bearbeiten:

```bash
sudo nano /etc/powergateway/config.toml
sudo systemctl restart powergateway
sudo journalctl -u powergateway -f
```

## Verzeichnisse nach der Installation

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- Daten/Puffer: `/var/lib/powergateway`
- Dienst: `powergateway.service`

## Lizenz

Die Lizenz wird vor der ersten stabilen Veröffentlichung festgelegt.
