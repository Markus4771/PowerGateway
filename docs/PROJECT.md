# PowerGateway – Projektbeschreibung

## 1. Zweck

PowerGateway ist ein modulares Gateway für Raspberry Pi und Debian. Es liest genau eine aktive Stromzählerquelle ein, normiert die Messwerte und stellt sie über MQTT für Home Assistant bereit. Zusätzlich übernimmt das System die lokale Einrichtung, Netzwerkverwaltung, Diagnose, Export- sowie Sicherungsfunktionen.

## 2. Zielsystem

PowerGateway ist für den dezentralen Einsatz direkt am Stromzähler ausgelegt. Pro Installation wird ein Stromzähler betrieben. Die typische Zielhardware ist ein Raspberry Pi 3B+ oder neuer mit Raspberry Pi OS Lite 64 Bit beziehungsweise ein aktuelles Debian-System.

## 3. Unterstützte Zählerquellen

- USB-SML-Lesekopf
- Tasmota MQTT
- generische MQTT-Quelle
- Simulation für Tests

Es ist immer nur eine Quelle aktiv. Die Auswahl erfolgt über die Konfiguration beziehungsweise die Weboberfläche.

## 4. Hauptfunktionen

### Messwerterfassung

- Erkennung serieller USB-Geräte
- SML-Rahmenerkennung
- OBIS-Auswertung
- Normierung von Einheiten und Skalierungen
- Erkennung unbekannter OBIS-Kennzahlen
- lokale Zwischenspeicherung bei unterbrochener MQTT-Verbindung

### MQTT und Home Assistant

- MQTT mit Benutzername und Passwort
- optional TLS und CA-Zertifikat
- Topic-Erkennung und Live-Nachrichten
- Home-Assistant-Discovery
- Availability-Status
- automatische Übertragung gepufferter Messwerte

### Netzwerk

Die vorgesehene Priorität lautet:

1. LAN
2. WLAN
3. LTE
4. lokaler Setup-Hotspot

Der Hotspot dient als lokaler administrativer Zugang und verwendet standardmäßig das Netz `192.168.50.0/24` mit der Adresse `192.168.50.1`.

### Fernzugriff

- WireGuard im Server- oder Client-Modus
- mehrere WireGuard-Peers
- QR-Code und Client-Konfigurationen
- SSH- und Reverse-SSH-Tunnel
- No-IP-DDNS mit IPv4- und IPv6-Unterstützung

### Betrieb und Wartung

- zentrale Systemübersicht
- Dienst- und Journaldiagnose
- LTE- und Internetdiagnose
- Speedtest
- Energiehistorie
- Export-Center
- Backup- und Restore-Grundlage
- Debian-Paketbau
- systemd-Dienste und Timer

## 5. Architektur

```text
Stromzähler / MQTT-Quelle
          │
          ▼
   Datenquellenmodul
          │
          ▼
 SML-/OBIS-Normierung
          │
          ├──► lokale Laufzeitdaten
          ├──► Energiehistorie
          ├──► Export / Backup
          │
          ▼
     MQTT-Publisher
          │
          ▼
    Home Assistant
```

Die Weboberfläche läuft getrennt vom Erfassungsdienst. Dadurch kann die Messwerterfassung unabhängig von der Bedienoberfläche weiterarbeiten.

## 6. Standardpfade

| Zweck | Pfad |
|---|---|
| Programm | `/opt/powergateway` |
| Konfiguration | `/etc/powergateway/config.toml` |
| TLS-Dateien | `/etc/powergateway/tls` |
| Laufzeitdaten | `/var/lib/powergateway` |
| Exportarchiv | `/var/lib/powergateway/exports` |
| Hauptdienst | `powergateway.service` |
| Webdienst | `powergateway-web.service` |
| Webanwendung intern | Port `8080` |
| LTE-Proxy intern | Port `8081` |
| nginx | Port `80` und optional `443` |

## 7. Sicherheitsgrundsätze

- Dienste laufen nicht als root, soweit keine Systemaktion zwingend erforderlich ist.
- Privilegierte Aktionen werden auf eng begrenzte sudo-Regeln beschränkt.
- Passwörter und private Schlüssel dürfen nicht in Git eingecheckt werden.
- MQTT über öffentliche Netze soll ausschließlich über TLS, WireGuard oder einen abgesicherten SSH-Tunnel erfolgen.
- Konfiguration, Backup und Export können sensible Daten enthalten und müssen entsprechend geschützt werden.

## 8. Entwicklungsgrundsätze

- GitHub ist die verbindliche Quelle.
- Modularer Aufbau.
- Konfiguration statt Programmierung, wo sinnvoll.
- Raspberry Pi und Debian sind die Hauptziele.
- Eine Installation verwaltet genau einen Stromzähler.
- Neue Funktionen benötigen Dokumentation, Tests und einen Changelog-Eintrag.
- Entwicklungsstände werden nicht als produktionsreif bezeichnet, bevor Hardware- und Langzeittests abgeschlossen sind.

## 9. Abgrenzung

Home Assistant bleibt das primäre System für Automationen, Benachrichtigungen und umfassende Langzeitvisualisierungen. PowerGateway konzentriert sich auf Erfassung, Transport, lokale Diagnose und sicheren Betrieb am Zählerstandort.

Nicht Bestandteil des aktuellen Kernumfangs sind:

- Steuerung von Wallboxen, Batterien oder Energiemanagementsystemen
- zentrale Verwaltung mehrerer Standorte
- öffentliche, ungeschützte REST-API
- Abrechnung gegenüber Energieversorgern

## 10. Aktueller Entwicklungsstand

Der aktuelle Entwicklungszweig ist `feature/ui-redesign-1.0`. Die Versionsdatei ist die verbindliche Quelle für den Softwarestand. Vor einer stabilen Freigabe müssen insbesondere USB-SML, LTE, Netzwerk-Failover, WireGuard, MQTT, Home-Assistant-Discovery sowie Backup und Wiederherstellung praktisch getestet werden.
