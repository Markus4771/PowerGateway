# Projekt PowerGateway

## Vision

PowerGateway stellt eine robuste, wartbare und datensparsame Verbindung zwischen einem digitalen Stromzähler und einem zentralen Home Assistant her.

## Systemgrenzen

Der Raspberry Pi ist ausschließlich Gateway. Home Assistant und der MQTT-Broker laufen zentral und nicht auf dem Gateway.

## Hardwarebasis

- Raspberry Pi 3B+
- Raspberry Pi OS Lite 64 Bit
- USB-IR-Lesekopf
- ZTE MF833 LTE Cat.4 USB-Dongle

## Architekturprinzipien

- modularer Aufbau
- Konfiguration statt fest codierter Umgebungswerte
- systemd-konformer Betrieb
- sichere Standardwerte
- keine Abhängigkeit von einer bestimmten SIM-Karte oder einem einzelnen MQTT-Broker
- lokale Pufferung bei Netzausfall
- nachvollziehbare Protokollierung ohne sensible Zugangsdaten

## Phasen

### 0.1.0 – technische Basis

- Repository- und Dokumentationsstruktur
- Konfigurationsmodell
- systemd-Dienst
- Geräteerkennung
- MQTT-Verbindungstest
- Installationsskript

### 0.2.0 – Zählerdaten

- SML-Decoder
- OBIS-Zuordnung
- Home-Assistant-Discovery
- lokale Pufferung

### 0.3.0 – LTE und Fernwartung

- ModemManager-Integration
- ZTE-MF833-Diagnose
- WireGuard
- automatische Wiederherstellung der Verbindung

### 0.4.0 – Administration

- Weboberfläche
- Diagnose
- Update- und Backup-Funktionen
- Debian-Paket
