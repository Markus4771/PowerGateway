# PowerGateway – Installationsanleitung

Diese Anleitung beschreibt die Installation und Ersteinrichtung von PowerGateway auf einem Raspberry Pi oder einem Debian-System. PowerGateway liest genau einen digitalen Stromzähler aus und überträgt die Messwerte per MQTT an Home Assistant.

> **Entwicklungsstand:** PowerGateway befindet sich derzeit noch in Entwicklung. Die Installation sollte zunächst in einer Testumgebung erfolgen.

## 1. Unterstützte Systeme

Empfohlen werden:

- Raspberry Pi 3B+ oder neuer
- Raspberry Pi OS Lite 64 Bit
- Debian 13 oder ein vergleichbares aktuelles Debian-System
- mindestens 2 GB freie Speicherkapazität
- Netzwerkzugang über LAN, WLAN oder LTE

Optional:

- USB-IR-Lesekopf für SML-Stromzähler
- Tasmota-WLAN-Lesekopf
- LTE-USB-Modem
- WireGuard-Zugang
- No-IP-Hostname

## 2. System vorbereiten

Das Betriebssystem aktualisieren:

```bash
sudo apt update
sudo apt full-upgrade -y
sudo reboot
```

Nach dem Neustart prüfen:

```bash
hostname -I
uname -a
```

Die angezeigte IP-Adresse wird später für den Aufruf der WebGUI benötigt.

## 3. Repository herunterladen

Git installieren:

```bash
sudo apt install -y git
```

PowerGateway herunterladen:

```bash
cd ~
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
```

Vor der Installation den Versionsstand prüfen:

```bash
cat version.txt
git log -1 --oneline
```

## 4. Installation mit dem Installationsskript

Das Installationsskript ausführbar machen und starten:

```bash
chmod +x install.sh
sudo ./install.sh
```

Alternativ:

```bash
sudo bash install.sh
```

Das Skript installiert die benötigten Pakete, richtet die Python-Umgebung ein und aktiviert die PowerGateway-Dienste.

## 5. Installation als Debian-Paket

### 5.1 Paket selbst bauen

```bash
cd ~/PowerGateway
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Das fertige Paket liegt anschließend im Verzeichnis `dist`.

Prüfen:

```bash
ls -lh dist/
```

### 5.2 Paket installieren

Die genaue Paketversion aus dem Verzeichnis `dist` verwenden, zum Beispiel:

```bash
sudo apt install ./dist/powergateway_0.9.12~dev_all.deb
```

Bei einer anderen Version den Dateinamen entsprechend anpassen.

### 5.3 Bereits installierte Version aktualisieren

```bash
sudo apt install ./dist/powergateway_VERSION_all.deb
```

Die vorhandene Konfiguration unter `/etc/powergateway/config.toml` bleibt bei einem normalen Paketupdate erhalten.

## 6. Dienste prüfen

Nach der Installation:

```bash
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
sudo systemctl status powergateway-network.service --no-pager -l
```

Alle drei Dienste sollten als `active (running)` angezeigt werden.

Weitere optionale Dienste prüfen:

```bash
sudo systemctl status powergateway-wireguard-status.timer --no-pager -l
sudo systemctl status powergateway-noip.timer --no-pager -l
sudo systemctl status powergateway-ha-tunnel.service --no-pager -l
```

Nicht konfigurierte optionale Dienste dürfen inaktiv sein.

## 7. WebGUI öffnen

Die WebGUI ist standardmäßig unter Port 8080 erreichbar:

```text
http://IP-DES-POWERGATEWAY:8080
```

Beispiel:

```text
http://192.168.178.40:8080
```

Falls die Seite nicht erreichbar ist:

```bash
sudo ss -tulpn | grep 8080
sudo journalctl -u powergateway-web.service -n 100 --no-pager
```

## 8. Ersteinrichtung

Die Einrichtung erfolgt in dieser Reihenfolge:

1. Netzwerkverbindung prüfen
2. Stromzählerquelle auswählen
3. MQTT-Verbindung konfigurieren
4. Home Assistant Discovery aktivieren
5. optional WireGuard einrichten
6. optional SSH-Tunnel einrichten
7. optional No-IP konfigurieren
8. Verbindung und Diagnose testen

## 9. Netzwerk einrichten

PowerGateway unterstützt:

- LAN
- WLAN
- LTE
- Setup-Hotspot als Fallback

Die Netzwerkdaten werden in der WebGUI eingetragen. Nach Änderungen den Netzwerkdienst prüfen:

```bash
sudo systemctl restart powergateway-network.service
sudo systemctl status powergateway-network.service --no-pager -l
```

Verbindung testen:

```bash
ip address
ip route
ping -c 4 1.1.1.1
ping -c 4 github.com
```

## 10. USB-IR-Lesekopf einrichten

Den USB-Lesekopf anschließen und erkennen lassen:

```bash
lsusb
ls -l /dev/serial/by-id/
```

Der Dienstbenutzer benötigt Zugriff auf serielle Geräte. Prüfen:

```bash
id powergateway
```

Der Benutzer sollte Mitglied der Gruppe `dialout` sein.

Falls nicht:

```bash
sudo usermod -aG dialout powergateway
sudo systemctl restart powergateway.service
```

In der WebGUI:

1. Datenquelle `USB-SML` auswählen
2. Gerät automatisch suchen oder `/dev/serial/by-id/...` eintragen
3. Baudrate automatisch testen lassen
4. `SML-Telegramm testen` ausführen
5. erkannte OBIS-Werte prüfen

## 11. Tasmota-Lesekopf einrichten

Für einen Tasmota-WLAN-Lesekopf:

1. Tasmota mit dem lokalen WLAN verbinden
2. MQTT in Tasmota aktivieren
3. MQTT-Broker, Benutzer und Passwort eintragen
4. das Tasmota-Topic notieren
5. in PowerGateway die Quelle `Tasmota MQTT` auswählen
6. das Eingangs-Topic eintragen
7. MQTT-Nachricht empfangen und erkannte Felder prüfen

Ein typisches Topic kann so aussehen:

```text
tele/Stromzaehler/SENSOR
```

## 12. MQTT konfigurieren

In der WebGUI eintragen:

- MQTT-Server oder IP-Adresse
- Port, normalerweise `1883`
- Benutzername
- Passwort
- optional TLS
- optional CA-Zertifikatsdatei

Verbindung über die Schaltfläche `Verbindung testen` prüfen.

Typische Standardwerte:

```text
Host: 192.168.178.50
Port: 1883
TLS: aus
```

Für TLS wird häufig Port `8883` verwendet. Das tatsächliche Zertifikat und der Port richten sich nach dem MQTT-Broker.

## 13. Home Assistant anbinden

### 13.1 Empfohlene Variante

Empfohlen wird:

```text
PowerGateway → MQTT → Home Assistant
```

Bei einer Verbindung über das Internet:

```text
PowerGateway → WireGuard → MQTT → Home Assistant
```

### 13.2 Home Assistant Discovery

In der WebGUI:

1. MQTT-Verbindung speichern
2. Home-Assistant-Sensoren in der Vorschau prüfen
3. `Discovery senden` auswählen
4. Home Assistant öffnen
5. unter **Einstellungen → Geräte & Dienste → MQTT** prüfen, ob PowerGateway erkannt wurde

PowerGateway kann unter anderem folgende Sensoren bereitstellen:

- aktueller Netzbezug
- aktuelle Einspeisung
- Gesamtbezug
- Gesamteinspeisung
- Momentanleistung
- Spannung je Phase
- Strom je Phase
- Netzfrequenz

Welche Sensoren erscheinen, hängt von den tatsächlich vom Zähler gelieferten OBIS-Werten ab.

## 14. WireGuard einrichten

WireGuard ist die empfohlene Absicherung für MQTT-Verbindungen über das Internet.

In der WebGUI können eingerichtet werden:

- Server- oder Client-Modus
- privater und öffentlicher Schlüssel
- Tunneladresse
- Endpoint
- AllowedIPs
- mehrere Peers
- Client-Konfiguration
- QR-Code
- Live-Status und Handshake

Systemstatus prüfen:

```bash
sudo wg show
ip address show wg0
ip route
```

Dienst prüfen:

```bash
sudo systemctl status wg-quick@wg0.service --no-pager -l
```

Falls ein anderer Interface-Name verwendet wird, `wg0` entsprechend ersetzen.

## 15. SSH-Tunnel einrichten

PowerGateway unterstützt einen SSH-Tunnel als Alternative zu WireGuard.

In der WebGUI:

1. Verbindungsart `SSH-Tunnel + MQTT` auswählen
2. SSH-Host oder No-IP-Hostname eintragen
3. SSH-Port eintragen
4. SSH-Benutzer eintragen
5. Schlüsseldatei festlegen
6. SSH-Schlüssel erzeugen
7. den angezeigten öffentlichen Schlüssel auf dem Zielsystem in `~/.ssh/authorized_keys` eintragen
8. Verbindung testen

Manueller Test:

```bash
sudo -u powergateway ssh -i /var/lib/powergateway/.ssh/id_ed25519 BENUTZER@HOST
```

## 16. Reverse-SSH einrichten

Reverse-SSH kann sinnvoll sein, wenn eine direkte eingehende Verbindung zum PowerGateway wegen LTE, CGNAT oder DS-Lite nicht möglich ist.

Dabei baut das PowerGateway selbstständig eine ausgehende SSH-Verbindung zu einem erreichbaren Server auf.

In der WebGUI:

1. `Reverse-SSH + MQTT` auswählen
2. öffentlichen SSH-Server oder No-IP-Hostname eintragen
3. SSH-Benutzer und Schlüssel konfigurieren
4. lokale und entfernte Ports festlegen
5. Verbindung testen

Dienst prüfen:

```bash
sudo systemctl status powergateway-ha-tunnel.service --no-pager -l
sudo journalctl -u powergateway-ha-tunnel.service -n 100 --no-pager
```

## 17. No-IP einrichten

No-IP stellt einen festen Hostnamen bereit, obwohl sich die öffentliche IP-Adresse ändern kann.

Vorbereitung:

1. No-IP-Konto anlegen
2. einen DDNS-Hostname anlegen, zum Beispiel `mein-gateway.ddns.net`
3. Zugangsdaten bereithalten

In der PowerGateway-WebGUI unter **Home Assistant & No-IP** eintragen:

- No-IP aktivieren
- Hostname
- Benutzername oder E-Mail-Adresse
- Passwort
- Update-Intervall, mindestens 5 Minuten

Danach:

1. Einstellungen speichern
2. `Öffentliche IP ermitteln und No-IP aktualisieren` ausführen
3. Ergebnis prüfen

Mögliche Statusmeldungen:

- `good`: Hostname wurde aktualisiert
- `nochg`: Hostname war bereits aktuell
- `badauth`: Zugangsdaten sind falsch
- `nohost`: Hostname wurde nicht gefunden
- `abuse`: Hostname wurde von No-IP gesperrt
- `911`: vorübergehende Störung bei No-IP

Timer prüfen:

```bash
sudo systemctl status powergateway-noip.timer --no-pager -l
sudo systemctl list-timers | grep powergateway-noip
```

Manuellen Dienstlauf starten:

```bash
sudo systemctl start powergateway-noip.service
sudo journalctl -u powergateway-noip.service -n 100 --no-pager
```

## 18. Firewall und Portfreigaben

Empfohlen:

- MQTT nicht unverschlüsselt ins Internet freigeben
- WireGuard statt einer öffentlichen MQTT-Freigabe verwenden
- SSH nur mit Schlüsseln nutzen
- Passwortanmeldung für öffentliche SSH-Zugänge deaktivieren
- No-IP nur als Namensauflösung verwenden; No-IP ersetzt keine Firewall und kein VPN

Typische Ports:

| Dienst | Port | Hinweis |
|---|---:|---|
| WebGUI | 8080/TCP | möglichst nur im internen Netz oder VPN |
| MQTT | 1883/TCP | unverschlüsselt, nicht öffentlich empfohlen |
| MQTT TLS | 8883/TCP | abhängig vom Broker |
| SSH | 22/TCP | möglichst nur per Schlüssel |
| WireGuard | 51820/UDP | frei konfigurierbar |
| Home Assistant | 8123/TCP | normalerweise nur intern oder per VPN |

## 19. Konfigurations- und Datenpfade

Wichtige Verzeichnisse:

```text
/opt/powergateway                    Programmdateien
/etc/powergateway/config.toml        Hauptkonfiguration
/var/lib/powergateway                Laufzeitdaten
/var/lib/powergateway/.ssh           SSH-Schlüssel
/var/lib/powergateway/noip_config.json  No-IP-Konfiguration
/etc/wireguard                       WireGuard-Konfigurationen
```

Die No-IP- und SSH-Passwörter beziehungsweise Schlüssel dürfen nicht öffentlich weitergegeben oder in GitHub eingecheckt werden.

## 20. Diagnose

### 20.1 Allgemeiner Status

```bash
sudo systemctl --failed
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
```

### 20.2 Protokolle

```bash
sudo journalctl -u powergateway.service -n 200 --no-pager
sudo journalctl -u powergateway-web.service -n 200 --no-pager
sudo journalctl -u powergateway-network.service -n 200 --no-pager
```

Live-Protokoll:

```bash
sudo journalctl -u powergateway.service -f
```

### 20.3 MQTT prüfen

Falls Mosquitto-Clients installiert sind:

```bash
sudo apt install -y mosquitto-clients
mosquitto_sub -h MQTT-SERVER -p 1883 -u BENUTZER -P PASSWORT -t '#' -v
```

Achtung: Passwörter in Befehlszeilen können in der Shell-Historie erscheinen. Für produktive Tests besser eine geschützte Konfigurationsdatei verwenden.

### 20.4 Netzwerk prüfen

```bash
ip address
ip route
resolvectl status
ping -c 4 1.1.1.1
ping -c 4 github.com
```

## 21. Update aus GitHub

Vor dem Update prüfen, ob lokale Änderungen vorhanden sind:

```bash
cd ~/PowerGateway
git status
```

Bei einem sauberen Repository:

```bash
git pull --ff-only
cat version.txt
sudo bash install.sh
```

Wenn `git pull` wegen lokaler Änderungen fehlschlägt, diese zuerst sichern:

```bash
git diff > ~/powergateway-lokale-aenderungen.patch
```

Nur wenn die lokalen Änderungen verworfen werden dürfen:

```bash
git restore DATEIPFAD
git pull --ff-only
```

Für `packaging/build_deb.sh` beispielsweise:

```bash
cp packaging/build_deb.sh /tmp/build_deb.sh.backup
git restore packaging/build_deb.sh
git pull --ff-only
```

## 22. Update per Debian-Paket

```bash
cd ~/PowerGateway
git pull --ff-only
rm -rf dist
./packaging/build_deb.sh
ls -lh dist/
sudo apt install ./dist/powergateway_VERSION_all.deb
```

Anschließend:

```bash
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
```

## 23. Deinstallation

Normale Deinstallation mit Erhalt der Konfiguration:

```bash
sudo apt remove powergateway
```

Vollständige Entfernung einschließlich Laufzeitdaten:

```bash
sudo apt purge powergateway
```

Falls das Repository über `install.sh` installiert wurde, das mitgelieferte Deinstallationsskript verwenden:

```bash
cd ~/PowerGateway
sudo ./uninstall.sh
```

Vollständige Entfernung:

```bash
sudo ./uninstall.sh --purge
```

Vor einer vollständigen Entfernung wichtige Konfigurationsdateien manuell sichern.

## 24. Sicherheitsgrundsätze

- keine Kennwörter oder privaten Schlüssel in GitHub speichern
- SSH ausschließlich mit Schlüsseln betreiben
- MQTT über WireGuard oder TLS absichern
- WebGUI nicht direkt ungeschützt ins Internet veröffentlichen
- Standardkennwörter bei der Ersteinrichtung ändern
- Betriebssystem regelmäßig aktualisieren
- nur notwendige Ports öffnen
- No-IP ist nur ein dynamischer DNS-Dienst und keine Sicherheitsfunktion

## 25. Empfohlene Zielkonfiguration

Für den vorgesehenen Einsatz wird folgende Konfiguration empfohlen:

```text
USB-IR-Lesekopf
        ↓
PowerGateway
        ↓
WireGuard
        ↓
MQTT-Broker
        ↓
Home Assistant
```

No-IP wird nur benötigt, wenn der WireGuard- oder SSH-Endpunkt keine feste öffentliche IP-Adresse besitzt.

## 26. Hilfe bei Fehlern

Bei einer Fehlermeldung folgende Ausgaben sammeln:

```bash
cd ~/PowerGateway
cat version.txt
git log -1 --oneline
git status
sudo systemctl --failed
sudo systemctl status powergateway.service --no-pager -l
sudo systemctl status powergateway-web.service --no-pager -l
sudo journalctl -u powergateway.service -n 100 --no-pager
sudo journalctl -u powergateway-web.service -n 100 --no-pager
```

Private Schlüssel, Passwörter, API-Tokens und vollständige öffentliche IP-Adressen vor dem Weitergeben unkenntlich machen.
