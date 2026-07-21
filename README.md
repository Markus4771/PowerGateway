# PowerGateway

PowerGateway ist ein schlankes Raspberry-Pi-Gateway zum Auslesen eines digitalen Stromzählers über einen USB-IR-Lesekopf und zur Übertragung der Messwerte per MQTT an einen zentralen Home Assistant.

## Zielhardware

- Raspberry Pi 3B+
- Raspberry Pi OS Lite 64 Bit
- USB-IR-Schreib-/Lesekopf (Weidmann-kompatibel)
- ZTE MF833 LTE Cat.4 USB-Dongle

## Kernfunktionen

- automatische Erkennung des IR-Lesekopfs
- SML-Auswertung mit modularer OBIS-Registry
- Energiebezug und Einspeisung, Tarifregister, Leistung, Spannung, Strom und Netzfrequenz
- Blindleistung und Leistungsfaktor
- Erhaltung unbekannter numerischer OBIS-Werte für Diagnose und spätere Erweiterungen
- MQTT-Übertragung inklusive Home-Assistant-Discovery
- LTE-Status und optionale WireGuard-Anbindung
- lokale Pufferung bei Verbindungsunterbrechungen
- lokale Weboberfläche für Status, Diagnose und Konfiguration
- hardwareunabhängiger SML-Simulationsmodus
- systemd-Dienste und Vorbereitung eines Debian-Pakets

## Bewusst nicht enthalten

PowerGateway bleibt ein spezialisiertes, wartungsarmes Gateway. Nicht Bestandteil sind:

- keine REST-API
- keine automatischen Softwareupdates
- keine integrierte Backup- oder Wiederherstellungsfunktion

Softwareaktualisierungen erfolgen kontrolliert über ein neues Debian-Paket.

## Aktueller Stand

Version `0.7.0-dev` – hardwareunabhängiger Simulations- und Testmodus.

Die Simulation erzeugt SML-Transportframes und führt sie durch denselben Parser-, MQTT-, Puffer- und WebGUI-Pfad wie später der echte USB-Lesekopf.

Verfügbare Profile:

- `generic` – generischer Dreiphasenzähler
- `emh` – EMH-eHZ-ähnliches Profil
- `easymeter` – EasyMeter-ähnliches Profil
- `iskra` – Iskra-ähnliches Profil
- `kaifa` – Kaifa-ähnliches Profil
- `solar` – Zweirichtungszähler mit Bezug und Einspeisung
- `unknown` – zusätzliche unbekannte OBIS-Kennzahl für Diagnosetests

## Simulation aktivieren

Konfiguration öffnen:

```bash
sudo nano /etc/powergateway/config.toml
```

Im Abschnitt `[meter]` einstellen:

```toml
[meter]
mode = "simulation"
simulation_profile = "generic"
simulation_interval = 5.0
simulation_seed = 4771
```

Danach den Dienst neu starten:

```bash
sudo systemctl restart powergateway
sudo journalctl -u powergateway -f
```

Zurück auf echte Hardware:

```toml
[meter]
mode = "serial"
device = "auto"
```

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

Anschließend:

```bash
sudo nano /etc/powergateway/config.toml
sudo systemctl restart powergateway
sudo journalctl -u powergateway -f
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
python3 -m unittest discover -s tests -v
```

## Lizenz

Die Lizenz wird vor der ersten stabilen Veröffentlichung festgelegt.
