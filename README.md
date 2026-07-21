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
- zusätzliche Kennzahlen für Blindleistung und Leistungsfaktor
- Erhaltung unbekannter numerischer OBIS-Werte für Diagnose und spätere Erweiterungen
- MQTT-Übertragung inklusive Home-Assistant-Discovery
- LTE-Status und automatische Wiederverbindung
- optionale WireGuard-Anbindung
- lokale Pufferung bei Verbindungsunterbrechungen
- lokale, schreibgeschützte Weboberfläche für Status und Diagnose
- systemd-Dienste und Vorbereitung eines Debian-Pakets

## Bewusst nicht enthalten

PowerGateway soll als spezialisiertes, wartungsarmes Gateway schlank bleiben. Daher sind folgende Funktionen nicht Bestandteil des Projekts:

- keine öffentliche REST-API
- keine automatischen Softwareupdates
- keine integrierte Backup- oder Wiederherstellungsfunktion

Softwareaktualisierungen erfolgen später kontrolliert über ein neues Debian-Paket.

## Aktueller Stand

Version `0.6.0-dev` – ausgebaute Weboberfläche auf Basis der OBIS-Engine aus Version 0.5.

Die Weboberfläche zeigt:

- Verbindung zum Stromzähler
- aktuelle Leistung, Energiebezug und Einspeisung
- MQTT-, Internet-, LTE- und WireGuard-Status
- Telegrammzähler und Größe des Offline-Puffers
- Alter des letzten Telegramms und Warnung bei veralteten Messwerten
- alle dekodierten Messwerte mit Einheit, OBIS-Kennung und Qualität
- maskierte, schreibgeschützte Konfigurationsübersicht
- Systemdiagnose für Dienste, LTE, WireGuard und serielle Geräte

Die Browserdaten unter `/_internal` dienen ausschließlich der Weboberfläche und sind keine öffentliche Programmierschnittstelle.

Die OBIS-Engine unterstützt unter anderem:

- `1.8.0`, `1.8.1`, `1.8.2` – Energiebezug
- `2.8.0`, `2.8.1`, `2.8.2` – Einspeisung
- `16.7.0` – Gesamtleistung
- `21.7.0`, `41.7.0`, `61.7.0` sowie herstellerspezifische Phasen-Aliase
- Spannungen und Ströme für L1 bis L3
- Netzfrequenz
- Leistungsfaktor gesamt und je Phase
- Wirk- und Blindleistungswerte

## Schnellstart

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
sudo bash install.sh
```

Anschließend die Konfiguration bearbeiten:

```bash
sudo nano /etc/powergateway/config.toml
sudo systemctl restart powergateway powergateway-web
sudo journalctl -u powergateway -f
```

Die Weboberfläche ist standardmäßig erreichbar unter:

```text
http://IP-DES-RASPBERRY-PI:8080
```

## Verzeichnisse nach der Installation

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
