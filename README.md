# PowerGateway

PowerGateway ist ein modulares Raspberry-Pi-Gateway für digitale Stromzähler. Messwerte können über einen USB-SML-Lesekopf, einen Tasmota-WLAN-Lesekopf oder den integrierten Simulator eingelesen und per MQTT an Home Assistant übertragen werden.

## Zielhardware

- Raspberry Pi 3B+
- Raspberry Pi OS Lite 64 Bit
- optional USB-IR-Schreib-/Lesekopf
- optional WLAN-IR-Lesekopf mit Tasmota Sensor53
- optional ZTE MF833 LTE Cat.4 USB-Dongle

## Kernfunktionen

- austauschbare Datenquellen
- USB-SML mit automatischer Geräteerkennung
- Tasmota-MQTT für WLAN-Leseköpfe
- hardwareunabhängiger SML-Simulator
- SML-Auswertung mit modularer OBIS-Registry
- MQTT-Übertragung inklusive Home-Assistant-Discovery
- LTE-Status und optionale WireGuard-Anbindung
- lokale Pufferung bei Verbindungsunterbrechungen
- lokale Weboberfläche für Status und Diagnose
- systemd-Dienste und Vorbereitung eines Debian-Pakets

## Aktueller Stand

Version `0.8.0-dev` – modulares Datenquellen-Framework mit USB-SML, Simulation und Tasmota-MQTT.

## Datenquelle auswählen

Konfiguration öffnen:

```bash
sudo nano /etc/powergateway/config.toml
```

### USB-SML-Lesekopf

```toml
[meter]
source = "usb_sml"
device = "auto"
baudrate = 9600
```

### Simulation

```toml
[meter]
source = "simulation"
simulation_profile = "generic"
simulation_interval = 5.0
simulation_seed = 4771
```

### Tasmota-WLAN-Lesekopf

Der vorhandene Lesekopf veröffentlicht diese Nachricht:

```json
{"Home":{"Power_curr":245,"total_in":41222.86}}
```

Passende Konfiguration:

```toml
[meter]
source = "tasmota_mqtt"

[meter.tasmota]
topic = "tele/Stromzaehler/SENSOR"
power_path = "Home.Power_curr"
energy_import_path = "Home.total_in"
```

Der Broker wird im Abschnitt `[mqtt]` eingerichtet:

```toml
[mqtt]
enabled = true
host = "192.168.178.50"
port = 1883
username = ""
password = ""
topic_prefix = "powergateway/powergateway-01"
homeassistant_discovery = true
```

Anschließend:

```bash
sudo systemctl restart powergateway
sudo journalctl -u powergateway -f
```

Erwartete Meldungen:

```text
Tasmota-MQTT verbunden und Topic abonniert: tele/Stromzaehler/SENSOR
Tasmota-Messwerte empfangen: power_total, energy_import
```

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

Die Weboberfläche ist standardmäßig unter `http://IP-DES-RASPBERRY:8080` erreichbar.

## Verzeichnisse

- Programm: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- Daten/Puffer: `/var/lib/powergateway`
- Messwerte: `/var/lib/powergateway/latest_values.json`
- Hauptdienst: `powergateway.service`
- Weboberfläche: `powergateway-web.service`

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Bewusst nicht enthalten

- keine öffentliche REST-API
- keine automatischen Softwareupdates
- keine integrierte Backup- oder Wiederherstellungsfunktion

## Lizenz

Die Lizenz wird vor der ersten stabilen Veröffentlichung festgelegt.
