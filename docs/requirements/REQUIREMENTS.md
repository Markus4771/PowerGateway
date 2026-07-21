# Anforderungen – PowerGateway

## Funktionale Anforderungen

### FR-001 Geräteerkennung
PowerGateway muss verfügbare serielle USB-Geräte erkennen und den konfigurierten IR-Lesekopf eindeutig auswählen können.

### FR-002 Zählerprotokolle
PowerGateway soll SML unterstützen. IEC 62056-21/D0 wird als weiteres Modul vorgesehen.

### FR-003 Messwerte
Mindestens Energiebezug, Energieeinspeisung und aktuelle Leistung sollen über konfigurierbare OBIS-Kennzahlen verarbeitet werden können.

### FR-004 MQTT
Messwerte müssen über MQTT mit TLS- und Zugangsdaten-Unterstützung an einen zentralen Broker gesendet werden können.

### FR-005 Home Assistant
Die spätere Produktivversion soll MQTT Discovery für Home Assistant bereitstellen.

### FR-006 Offline-Puffer
Bei fehlender Verbindung müssen Messwerte lokal zwischengespeichert und später übertragen werden können.

### FR-007 LTE
Das ZTE MF833 muss unabhängig von seiner Betriebsart als Netzwerkschnittstelle oder Modem diagnostiziert werden können.

### FR-008 WireGuard
WireGuard muss optional aktivierbar sein und darf den lokalen Messbetrieb nicht blockieren.

### FR-009 Betrieb
PowerGateway muss als systemd-Dienst automatisch starten und nach Fehlern neu gestartet werden.

### FR-010 Diagnose
Gerätezustand, letzter Messwert, MQTT-Verbindung, Netzverbindung und Fehler müssen nachvollziehbar angezeigt oder protokolliert werden.

## Nichtfunktionale Anforderungen

- Raspberry Pi 3B+ und Raspberry Pi OS Lite 64 Bit
- geringer Arbeitsspeicher- und CPU-Verbrauch
- keine Protokollierung von Kennwörtern oder privaten Schlüsseln
- robuste Wiederanläufe nach Strom- oder Netzausfall
- modulare Treiber für Zähler und Übertragungswege
- Konfiguration unter `/etc/powergateway`
- Laufzeitdaten unter `/var/lib/powergateway`
