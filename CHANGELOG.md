# Änderungsprotokoll

## 0.9.19-dev – 2026-07-24

- No-IP um getrennt aktivierbare IPv4- und IPv6-Aktualisierung erweitert
- Dual-Stack-Updates senden IPv4 und IPv6 gemeinsam an No-IP
- öffentliche IPv6-Adresse wird über den No-IP-Erkennungsdienst ermittelt
- DNS-Diagnose prüft A- und AAAA-Records getrennt
- lokale No-IP-Historie mit den letzten 100 Prüfungen und Änderungen ergänzt
- WebGUI zeigt die letzten Update-Versuche mit Zeit, Status und Ergebnis
- optionaler Neustart von SSH-Tunnel und WireGuard bei geänderter öffentlicher IP ergänzt
- eng begrenzte sudo-Regel für den Neustart von `wg-quick@wg0.service` ergänzt
- verständliche Fehler für fehlende IPv4-/IPv6-Konnektivität und abgelehnte Update-Clients ergänzt

## 0.9.18-dev – 2026-07-24

- manuellen Internet-Speedtest in der Systemübersicht ergänzt
- Download, Upload, Ping, Jitter, Paketverlust, Testserver und Provider werden soweit verfügbar angezeigt
- die letzten 50 Speedtests werden lokal gespeichert und können in der WebGUI eingesehen werden
- Hinweis auf möglichen LTE-Datenverbrauch vor dem Speedtest ergänzt
- LTE-Empfangsdiagnose über ModemManager und die ZTE-Webschnittstelle ergänzt
- RSRP, RSRQ, SINR, RSSI, Provider, Netztyp, Funkzelle und LTE-Band werden soweit vom Stick geliefert ausgelesen
- Signalqualität wird als hervorragend, gut, ausreichend, schlecht oder kritisch bewertet
- ZTE MF833U1 im CDC-Ethernet-Modus wird über sein LTE-Gateway abgefragt
- Debian-Paket installiert `speedtest-cli` automatisch

## 0.9.17-dev – 2026-07-24

- LTE-Erkennung um USB-Ethernet-, CDC-Ethernet-, RNDIS-, NCM-, MBIM- und QMI-Geräte erweitert
- ZTE MF833U1 mit USB-ID `19d2:1706` wird als LTE-Stick erkannt
- LTE-Schnittstellen werden auch dann erkannt, wenn NetworkManager sie als Ethernet statt GSM meldet
- Hersteller, Modell, USB-ID, Treiber, Betriebsart, IP-Adresse und Gateway werden im Netzwerkstatus bereitgestellt
- Verbindungstest kann gezielt über die erkannte LTE-Schnittstelle durchgeführt werden
- USB-Ethernet-LTE-Sticks benötigen keinen APN in PowerGateway und werden über DHCP verbunden
- vorhandene LTE-Verbindung kann direkt aktiviert werden
- automatische Netzwerkpriorisierung berücksichtigt die tatsächlich erkannte LTE-Verbindung

## 0.9.16-dev – 2026-07-24

- zentrale Systemübersicht mit Ampelstatus ergänzt
- Internet, DNS, Stromzähler, MQTT, Home Assistant, WireGuard, SSH und No-IP werden gemeinsam geprüft
- Status der PowerGateway- und Weboberflächen-Dienste integriert
- ausführliche Gesamtdiagnose mit Arbeitsspeicher, Datenträger, Laufzeit und fehlgeschlagenen systemd-Diensten ergänzt
- optionale oder noch nicht konfigurierte Funktionen werden getrennt von echten Fehlern dargestellt
- Detailinformationen je Statuskachel ein- und ausblendbar gemacht
- Dashboard als eigenes Modul in die Plugin-Webanwendung eingebunden

## 0.9.15-dev – 2026-07-24

- öffentliche IPv4 wird automatisch ermittelt und mit dem letzten Stand verglichen
- No-IP wird nur bei fälligem Intervall oder geänderter IP aktualisiert
- letzter Versuch, letzter Erfolg und nächster Prüftermin werden gespeichert
- Status `unchanged` und `not_due` verhindern unnötige DDNS-Anfragen
- No-IP-Diagnose für öffentliche IP, DNS-Auflösung und letzten Updatezustand ergänzt
- WebGUI zeigt den vollständigen No-IP-Status mit lesbaren Zeitangaben
- manueller Sofortabgleich und eigene Diagnose-Schaltfläche ergänzt
- optionaler Neustart des aktiven SSH-Tunnels nach erfolgreicher IP-Änderung umgesetzt
- No-IP-Prüftimer auf fünf Minuten gesetzt; das konfigurierte Intervall wird intern berücksichtigt

## 0.9.14-dev – 2026-07-24

- SSH-Tunnel-WebGUI vollständig in die Plugin-Webanwendung eingebunden
- Start, Neustart und Stopp über eine eng begrenzte sudo-Regel ermöglicht
- SSH-Konfiguration wird vor dem Dienststart geprüft
- verständliche Fehler bei deaktivierter Verbindung oder falscher Verbindungsart ergänzt
- Dienststatus, Autostart, Laufzeitstatus und Journal-Protokolle verbessert
- Speichern der Home-Assistant-Konfiguration startet oder stoppt den Tunnel passend zur Auswahl
- systemd-Neustart auf echte Fehler begrenzt; deaktivierte Tunnel erzeugen keine Neustartschleife mehr
- Installer und Debian-Paket installieren und prüfen die benötigte sudo-Regel
- SSH-Tunneldienst wird nur automatisch aktiviert, wenn ein SSH-Modus tatsächlich konfiguriert ist

## 0.9.13-dev – 2026-07-24

- produktiven SSH- und Reverse-SSH-Tunnelprozess ergänzt
- automatische Wiederverbindung über systemd umgesetzt
- Keepalive, Verbindungs-Timeout und Prüfung der Portweiterleitung ergänzt
- sichere ED25519-Schlüssel- und Known-Hosts-Nutzung vorbereitet
- Statusdatei für Start, Laufzeit und Fehler ergänzt
- Starten, Stoppen und Neustarten des Tunnels in der WebGUI ergänzt
- Dienststatus und Journal-Protokolle in der WebGUI ergänzt
- Installer und Debian-Paket um den SSH-Tunneldienst erweitert

## 0.9.11-dev – 2026-07-22

- WireGuard-Zentrale mit Server- und Client-Modus vervollständigt
- mehrere Peers mit Aktivieren, Deaktivieren, Bearbeiten und Löschen
- automatische freie IPv4-Adresse für neue Clients
- Peer-Gruppen, Beschreibungen und optionale Ablaufdaten ergänzt
- abgelaufene Peers werden nicht mehr in die aktive Serverkonfiguration übernommen
- doppelte öffentliche Schlüssel werden verhindert
- fertige Client-Konfigurationen und QR-Codes erzeugbar
- Live-Status je Peer mit Online/Offline, letztem Handshake sowie RX/TX ergänzt
- lokale Diagnose für Werkzeuge, Schlüssel, Tunnelstatus, Routing, IP-Forwarding, DNS, Systemdienst und Handshake ergänzt
- Versionsstand auf 0.9.11-dev erhöht

## 0.9.10-dev – 2026-07-21

- internes thread-sicheres Ereignissystem ergänzt
- konfigurationsbasierte Plugin-Grundlage mit Lebenszyklus, Status und Diagnose ergänzt
- Pluginfehler werden vom Kern isoliert und stoppen den Hauptdienst nicht
- modularen Einrichtungsassistenten mit fester Schrittfolge ergänzt
- Fortschritt, aktueller Schritt, Pflicht- und optionale Schritte werden maschinenlesbar geliefert
- Versionsanzeige des Einrichtungsassistenten wird zentral aus `version.txt` gelesen
- bestehender Einrichtungsstatus liefert zusätzlich den neuen Wizard-Zustand

## 0.9.9-dev – 2026-07-21

- Entwicklungsversion auf 0.9.9-dev erhöht
- sicheres Deinstallationsskript ergänzt
- Standard-Deinstallation behält Konfiguration und Betriebsdaten
- vollständige Entfernung über `uninstall.sh --purge` ergänzt
- Debian-Paketbau über `packaging/build_deb.sh` vorbereitet
- Paket-Metadaten, Abhängigkeiten und Maintainer-Skripte ergänzt
- bestehende Konfiguration wird bei Paketupdates erhalten
- systemd-Dienste werden durch das Debian-Paket eingerichtet und verwaltet
- Anleitung für Paketbau, Installation, Update und Deinstallation ergänzt

## 0.9.8-dev – 2026-07-21

- USB-SML-Verbindungstest in der WebGUI ergänzt
- automatische Prüfung üblicher Baudratenprofile vorbereitet
- vollständige SML-Frames werden erkannt und ausgewertet
- erkannte Messwerte und unbekannte OBIS-Kennzahlen werden im Test angezeigt
- verständliche Fehlermeldungen für fehlende Geräte, Rechte und Telegramme ergänzt
- Home-Assistant-Discovery-Vorschau ergänzt
- Discovery kann manuell veröffentlicht oder gelöscht werden
- Availability wird beim manuellen Veröffentlichen gesetzt
- Status der PowerGateway-Dienste wird in der WebGUI angezeigt
- Journal-Protokolle können über die Diagnoseoberfläche gelesen werden
- Installer ergänzt den Dienstbenutzer um Journal-Leserechte, sofern verfügbar

## 0.9.7-dev – 2026-07-21

- MQTT-Assistent ergänzt
- echte MQTT-Anmeldung mit Benutzername und Passwort
- TLS- und CA-Unterstützung
- Topic-Erkennung über abonnierte MQTT-Nachrichten
- Live-Nachrichten und JSON-Vorschau
- automatische Vorschläge für Leistung, Bezug und Einspeisung
- vollständige GitHub-Dokumentationsstruktur begonnen
- README, Roadmap, Installations- und Konfigurationsanleitungen aktualisiert
- Projektkontext und Einstieg für neue Chats ergänzt
- festgelegt, dass Diagramme und Langzeitauswertungen in Home Assistant erfolgen

## 0.9.6-dev – 2026-07-21

- Einrichtungsstatus in der WebGUI ergänzt
- USB-SML-Geräteerkennung ergänzt
- Hardware- und Systemdiagnose ergänzt
- Einrichtungs- und Diagnosemodule in Installer und WebGUI eingebunden

## 0.9.5-dev – 2026-07-21

- WireGuard-Konfiguration, Anwendung und Statusdienst ergänzt
- WireGuard-Weboberfläche eingebunden
- systemd-Dienste und Installer erweitert

## 0.8.0-dev – 2026-07-21

- modulares Datenquellen-Framework
- USB-SML, Simulation und Tasmota MQTT als Quellen
- Laufzeitkonfiguration und WebGUI erweitert
- Netzwerkverwaltung für LAN, WLAN, LTE und Hotspot
- einfache Benutzerverwaltung und Ersteinrichtung

## 0.3.0-dev – 2026-07-21

- modulare SML-/OBIS-Auswertung ergänzt
- bekannte OBIS-Kennzahlen für Bezug, Einspeisung, Leistung, Spannung, Strom und Frequenz definiert
- Skalierung und Einheiten der Messwerte normiert
- Energieangaben für Home Assistant von Wh nach kWh umgerechnet
- Home-Assistant-Discovery für Zähler- und Phasensensoren ergänzt
- Werkzeug `scripts/decode_sml.py` zum Prüfen aufgezeichneter Telegramme ergänzt
- automatisierte Tests für bekannte und unbekannte OBIS-Werte ergänzt

## 0.2.0-dev – 2026-07-21

- serielle SML-Rahmenerkennung implementiert
- MQTT-Publisher und Home-Assistant-Discovery ergänzt
- Offline-Pufferung mit SQLite und automatisches Nachsenden umgesetzt
- LTE- und WireGuard-Statusprüfung ergänzt
- maschinenlesbare Statusdatei und Diagnoseskript ergänzt
- automatisierte Tests und GitHub-Actions-Workflow ergänzt
