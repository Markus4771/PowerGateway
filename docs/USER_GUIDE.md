# PowerGateway – Benutzerhandbuch

## 1. Aufgabe von PowerGateway

PowerGateway liest die Daten eines digitalen Stromzählers ein und überträgt sie an einen MQTT-Broker beziehungsweise an Home Assistant. Die Weboberfläche dient zur Einrichtung, Statuskontrolle, Diagnose und Verwaltung der lokalen Daten.

## 2. Weboberfläche öffnen

PowerGateway wird im Browser über die IP-Adresse des Geräts geöffnet:

```text
http://IP-DES-POWERGATEWAY
```

Falls nginx nicht verwendet wird, kann die interne Weboberfläche über Port `8080` erreichbar sein:

```text
http://IP-DES-POWERGATEWAY:8080
```

## 3. Dashboard

Das Dashboard zeigt den Gesamtzustand des Systems. Typische Bereiche sind:

- Stromzähler
- Internet und DNS
- MQTT
- Home Assistant
- Netzwerk
- LTE
- WireGuard
- SSH-Tunnel
- No-IP
- PowerGateway-Dienste

### Statusfarben

- **Grün:** Funktion arbeitet ordnungsgemäß.
- **Gelb:** Funktion ist nicht vollständig eingerichtet oder nur eingeschränkt verfügbar.
- **Rot:** Es liegt ein Fehler vor.
- **Grau:** Optionale Funktion ist deaktiviert oder nicht konfiguriert.

Eine deaktivierte optionale Funktion ist nicht automatisch ein Fehler.

## 4. Einrichtungsassistent

Die empfohlene Reihenfolge lautet:

1. Netzwerk prüfen
2. Stromzählerquelle auswählen
3. Zählerdaten testen
4. MQTT konfigurieren
5. Home Assistant anbinden
6. optional WireGuard oder SSH-Tunnel einrichten
7. Diagnose durchführen
8. Backup erstellen

Pflichtschritte und optionale Schritte werden getrennt dargestellt.

## 5. Stromzähler

PowerGateway unterstützt verschiedene Quellen.

### USB-SML

Bei einem USB-Lesekopf:

1. Lesekopf am Raspberry Pi anschließen.
2. USB-SML als Quelle auswählen.
3. erkannte Schnittstelle auswählen.
4. Verbindungstest starten.
5. erkannte Messwerte prüfen.
6. Konfiguration speichern.

### Tasmota MQTT

Bei einem Tasmota-Lesekopf:

1. Tasmota mit WLAN und MQTT verbinden.
2. Tasmota MQTT als Quelle auswählen.
3. Eingangs-Topic eintragen.
4. Nachrichtensuche starten.
5. erkannte Felder zuordnen.
6. Konfiguration speichern.

### Simulation

Die Simulation dient ausschließlich zum Testen der Oberfläche und der MQTT-Ausgabe. Sie darf nicht mit echten Zählerwerten verwechselt werden.

## 6. MQTT

In der MQTT-Konfiguration werden Broker, Port und Zugangsdaten eingetragen. Die Schaltfläche **Verbindung testen** prüft, ob PowerGateway den Broker erreichen und sich anmelden kann.

Ein erfolgreicher Verbindungstest bedeutet noch nicht automatisch, dass Home Assistant bereits Sensoren anzeigt. Dafür muss zusätzlich die Discovery-Konfiguration veröffentlicht werden.

## 7. Home Assistant

Nach erfolgreicher MQTT-Konfiguration:

1. Discovery-Vorschau öffnen.
2. Sensoren und Einheiten prüfen.
3. Discovery senden.
4. Home Assistant öffnen.
5. unter **Einstellungen → Geräte & Dienste → MQTT** nach PowerGateway suchen.

Welche Sensoren verfügbar sind, hängt vom Stromzähler ab. Typisch sind:

- Gesamtbezug
- Gesamteinspeisung
- aktuelle Leistung
- Spannung
- Strom
- Frequenz

## 8. Netzwerk

PowerGateway bevorzugt normalerweise LAN vor WLAN und LTE. Der Setup-Hotspot stellt einen lokalen Zugang bereit, falls keine andere Verbindung verfügbar ist oder Wartungsarbeiten erforderlich sind.

Standard-Hotspot:

```text
SSID: PowerGateway-Setup
Adresse der Weboberfläche: http://192.168.50.1
```

## 9. LTE

Im LTE-Bereich können je nach Modem angezeigt werden:

- Hersteller und Modell
- Verbindungsart
- IP-Adresse
- Provider
- Netztyp
- Signalwerte
- LTE-Band

Nicht jedes Modem liefert alle Werte. Fehlende Signalwerte bedeuten daher nicht zwingend, dass die Verbindung defekt ist.

Ein Speedtest kann LTE-Datenvolumen verbrauchen und sollte nicht unnötig oft gestartet werden.

## 10. WireGuard

WireGuard stellt einen verschlüsselten Tunnel bereit. In der Oberfläche können Status, letzter Handshake sowie gesendete und empfangene Daten angezeigt werden.

Ein Peer gilt nicht automatisch als defekt, wenn aktuell kein Handshake sichtbar ist. Mobile oder ausgeschaltete Gegenstellen melden sich erst beim nächsten Verbindungsaufbau.

## 11. Energiehistorie

Die lokale Energiehistorie speichert Messwerte für Diagnose und Export. Umfangreiche Langzeitdiagramme, Energie-Dashboards und Automationen werden weiterhin bevorzugt in Home Assistant verwendet.

Bei einer Änderung des Zählerstands oder einem Zählerwechsel darf ein Basiswert nur bewusst und dokumentiert zurückgesetzt werden.

## 12. Export-Center

Im Export-Center können vorhandene Daten in unterstützten Formaten ausgegeben werden. Abhängig vom Softwarestand sind vorgesehen:

- CSV
- JSON
- XLSX
- PDF
- ZIP-Archiv

Vor dem Export Zeitraum und Inhalt prüfen. Exportdateien können detaillierte Verbrauchsdaten enthalten.

## 13. Backup

Ein manuelles Backup sollte erstellt werden:

- nach der vollständigen Ersteinrichtung
- vor Updates
- vor Änderungen an Netzwerk, MQTT oder WireGuard
- nach wichtigen Konfigurationsänderungen

Sicherungsdateien an einem zweiten Ort speichern. Eine Sicherung, die ausschließlich auf derselben SD-Karte liegt, schützt nicht vor einem Defekt der Karte.

## 14. Diagnose

Bei Problemen zuerst die Systemübersicht öffnen. Danach den betroffenen Bereich auswählen und Details beziehungsweise Protokolle anzeigen.

Typische erste Prüfungen:

- Stromzähler verbunden?
- Internet verfügbar?
- MQTT-Verbindung grün?
- Home Assistant erreichbar?
- genügend freier Speicher?
- PowerGateway-Dienste aktiv?

## 15. Sicherer Betrieb

- Zugangsdaten nicht weitergeben.
- Weboberfläche nicht ungeschützt ins Internet stellen.
- Fernzugriff bevorzugt über WireGuard verwenden.
- Backups regelmäßig extern speichern.
- Updates nur nach vorheriger Sicherung einspielen.
- Änderungen am Zähler oder Lesekopf dokumentieren.
