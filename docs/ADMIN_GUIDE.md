# PowerGateway – Administratorhandbuch

## 1. Anmeldung und Zugriff

Die Weboberfläche wird im lokalen Netz über die IP-Adresse des Geräts geöffnet. Je nach Installation erfolgt der Zugriff direkt über Port `8080` oder über nginx auf Port `80` beziehungsweise `443`.

```text
http://IP-DES-POWERGATEWAY
```

Für Wartungsarbeiten steht zusätzlich SSH zur Verfügung. Der SSH-Zugang sollte nur mit Schlüsseln und möglichst über das lokale Netz oder WireGuard verwendet werden.

## 2. Wichtige Systempfade

- Anwendung: `/opt/powergateway`
- Konfiguration: `/etc/powergateway/config.toml`
- TLS: `/etc/powergateway/tls`
- Laufzeitdaten: `/var/lib/powergateway`
- Exporte: `/var/lib/powergateway/exports`

Vor manuellen Änderungen an der Konfiguration immer eine Sicherung erstellen.

## 3. Dienste verwalten

Status der Kerndienste:

```bash
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
sudo systemctl status powergateway-network.service --no-pager -l
```

Neustart:

```bash
sudo systemctl restart powergateway.service
sudo systemctl restart powergateway-web.service
```

Protokolle:

```bash
sudo journalctl -u powergateway.service -n 200 --no-pager
sudo journalctl -u powergateway-web.service -n 200 --no-pager
```

## 4. Stromzähler konfigurieren

Unter der Zähler- beziehungsweise Quellenkonfiguration wird genau eine aktive Quelle ausgewählt.

### USB-SML

1. Lesekopf anschließen.
2. Gerät unter `/dev/serial/by-id/` auswählen.
3. Verbindungstest starten.
4. Baudrate und erkannte OBIS-Werte prüfen.
5. Einstellungen speichern.

Prüfung auf der Konsole:

```bash
ls -l /dev/serial/by-id/
id powergateway
```

Der Dienstbenutzer muss Mitglied der Gruppe `dialout` sein.

### Tasmota oder Generic MQTT

1. Eingangsbroker und Topic eintragen.
2. Verbindung testen.
3. Nachrichten mitschneiden.
4. JSON-Felder für Leistung, Bezug und Einspeisung zuordnen.
5. Quelle aktivieren.

## 5. MQTT-Ausgabe

Zu konfigurieren sind:

- Hostname oder IP-Adresse
- Port
- Benutzername und Passwort
- TLS ja/nein
- CA-Datei bei eigener Zertifizierungsstelle
- Basis-Topic

Empfohlene Ports:

- `1883` nur im vertrauenswürdigen lokalen Netz oder über VPN
- `8883` für MQTT mit TLS

Nach dem Speichern immer den Verbindungstest durchführen.

## 6. Home Assistant

Die empfohlene Verbindung lautet:

```text
PowerGateway → MQTT → Home Assistant
```

Vorgehen:

1. MQTT-Verbindung erfolgreich testen.
2. Discovery-Vorschau kontrollieren.
3. Discovery-Konfiguration veröffentlichen.
4. In Home Assistant unter **Einstellungen → Geräte & Dienste → MQTT** prüfen.
5. Availability und Messwerte kontrollieren.

## 7. Netzwerkverwaltung

Die vorgesehene Priorität lautet LAN → WLAN → LTE → Hotspot.

### LAN

LAN wird bevorzugt. Prüfen:

```bash
ip address
ip route
```

### WLAN

SSID und Passwort in der Weboberfläche eintragen. Nach Änderungen:

```bash
sudo systemctl restart powergateway-network.service
```

### LTE

Der ZTE MF833U1 kann als USB-Ethernet-Gerät erscheinen. In diesem Fall erfolgt die Verbindung über DHCP und nicht über eine klassische ModemManager-APN-Konfiguration.

Prüfen:

```bash
lsusb
nmcli device status
ip route
```

### Setup-Hotspot

Standardwerte:

```text
SSID: PowerGateway-Setup
Gateway: 192.168.50.1
Netz: 192.168.50.0/24
```

Der Hotspot ist für lokale Administration vorgesehen und soll nicht als allgemeiner Internetzugang verwendet werden.

## 8. WireGuard

WireGuard ist die bevorzugte Methode für sicheren Fernzugriff und MQTT über nicht vertrauenswürdige Netze.

Status:

```bash
sudo wg show
sudo systemctl status wg-quick@wg0.service --no-pager -l
```

Bei Peer-Änderungen:

- doppelte Schlüssel vermeiden
- AllowedIPs kontrollieren
- abgelaufene Peers deaktivieren
- QR-Codes nur an berechtigte Personen weitergeben

## 9. No-IP und SSH-Tunnel

No-IP wird nur benötigt, wenn ein wechselnder öffentlicher Anschluss direkt adressiert werden muss. Bei DS-Lite oder CGNAT ist Reverse-SSH oder ein ausgehender WireGuard-Tunnel meist geeigneter.

SSH-Tunnel prüfen:

```bash
sudo systemctl status powergateway-ha-tunnel.service --no-pager -l
sudo journalctl -u powergateway-ha-tunnel.service -n 100 --no-pager
```

## 10. Export-Center

Das Export-Center stellt Mess- und Verlaufsdaten in mehreren Formaten bereit. Je nach installiertem Stand sind CSV, JSON, XLSX, PDF und ZIP vorgesehen.

Exporte werden unter folgendem Pfad archiviert:

```text
/var/lib/powergateway/exports
```

Exportdateien können vertrauliche Verbrauchs- und Standortdaten enthalten. Nicht benötigte Exporte regelmäßig löschen.

## 11. Backup und Wiederherstellung

Eine Sicherung soll mindestens enthalten:

- `/etc/powergateway`
- `/var/lib/powergateway`
- Versions- und Prüfsummeninformationen

Vor einer Wiederherstellung:

1. aktuelle Sicherung erstellen
2. Version und Prüfsumme des Zielbackups prüfen
3. Dienste stoppen
4. Restore zunächst in einen Staging-Bereich entpacken
5. Inhalt prüfen
6. erst danach produktive Daten ersetzen
7. Dienste starten und Diagnose durchführen

Backup-Timer prüfen:

```bash
sudo systemctl status powergateway-backup.timer --no-pager -l
sudo systemctl list-timers | grep powergateway
```

Da Backup und Restore sicherheitskritisch sind, muss die Wiederherstellung vor produktivem Einsatz praktisch getestet werden.

## 12. Aktualisierung

Vor jedem Update:

```bash
cat /opt/powergateway/version.txt 2>/dev/null || true
sudo systemctl --failed
```

Bei Git-Installation:

```bash
cd ~/PowerGateway
git pull --ff-only
sudo bash install.sh
```

Bei Debian-Paket:

```bash
sudo apt install ./powergateway_VERSION_all.deb
```

Nach dem Update:

```bash
sudo systemctl daemon-reload
sudo systemctl restart powergateway.service powergateway-web.service
sudo systemctl --failed
```

## 13. Regelmäßige Wartung

Wöchentlich:

- Systemübersicht kontrollieren
- fehlgeschlagene Dienste prüfen
- freien Speicher kontrollieren
- MQTT- und Home-Assistant-Status prüfen

Monatlich:

- Backup testweise lesen
- Exportarchiv bereinigen
- Betriebssystemupdates installieren
- WireGuard-Peers prüfen
- LTE- und Netzwerkdiagnose kontrollieren

Vor jeder größeren Änderung:

- Backup erstellen
- aktuelle Konfiguration dokumentieren
- Versionsstand notieren

## 14. Fehlerdiagnose

Gesamtstatus:

```bash
sudo systemctl --failed
free -h
df -h
ip address
ip route
```

MQTT-Probleme:

- DNS-Auflösung prüfen
- Port prüfen
- Zugangsdaten kontrollieren
- CA-Zertifikat und Systemzeit kontrollieren

Keine Zählerwerte:

- USB-Gerät vorhanden?
- Gruppe `dialout` korrekt?
- richtige Quelle aktiv?
- Baudrate richtig?
- SML-Telegramme vorhanden?

WebGUI nicht erreichbar:

```bash
sudo ss -tulpn | grep -E ':80|:443|:8080'
sudo journalctl -u powergateway-web.service -n 100 --no-pager
```
