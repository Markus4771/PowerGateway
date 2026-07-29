# PowerGateway – Entwicklerhandbuch

## 1. Entwicklungsmodell

PowerGateway wird modular entwickelt. GitHub ist die verbindliche Quelle. Änderungen erfolgen auf einem eigenen Entwicklungszweig und werden erst nach Prüfung in einen stabilen Zweig übernommen.

Verbindliche Grundsätze:

- Konfiguration statt fest codierter Sonderfälle
- genau eine aktive Zählerquelle
- Trennung von Erfassungsdienst und Weboberfläche
- Fehler eines optionalen Moduls dürfen den Kern nicht stoppen
- neue Funktionen benötigen Tests, Dokumentation und Changelog
- Raspberry Pi 3B+ bleibt ein relevantes Leistungsziel

## 2. Repository-Struktur

Typische Bereiche:

```text
src/                 Python-Anwendung und Module
plugins/             optionale Erweiterungen, soweit ausgelagert
tests/               automatisierte Tests
packaging/            Debian-Paketbau und systemd-Dateien
scripts/              Diagnose- und Hilfswerkzeuge
docs/                 Projektdokumentation
install.sh            Installation aus dem Repository
uninstall.sh          Deinstallation
version.txt           verbindliche Anwendungsversion
```

Die tatsächlich vorhandene Struktur im jeweiligen Branch ist maßgeblich.

## 3. Lokale Entwicklungsumgebung

Empfohlen:

```bash
git clone https://github.com/Markus4771/PowerGateway.git
cd PowerGateway
git checkout feature/ui-redesign-1.0
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Abhängigkeiten sind aus den im Repository vorhandenen Requirements- beziehungsweise Paketdateien zu installieren.

## 4. Anwendungskomponenten

### Hauptdienst

Der Hauptdienst liest die aktive Quelle, normiert Werte und veröffentlicht diese per MQTT. Er muss unabhängig von der Weboberfläche stabil weiterlaufen.

### Webdienst

Die Webanwendung wird über gunicorn gestartet und intern gewöhnlich auf Port `8080` bereitgestellt. nginx kann davor auf Port `80` und `443` arbeiten.

### Netzwerkcontroller

Der Netzwerkcontroller setzt die vorgesehene Priorität LAN → WLAN → LTE → Hotspot um. Änderungen an diesem Bereich müssen auf realer Hardware geprüft werden, da NetworkManager, ModemManager, Routing und USB-Geräte voneinander abhängen.

### Plugin- und Modulsystem

Optionale Module sollen über klar definierte Registrierungs- beziehungsweise Initialisierungspunkte eingebunden werden. Ein Import- oder Laufzeitfehler eines optionalen Moduls darf die Webanwendung oder den Hauptdienst nicht vollständig unbrauchbar machen.

## 5. Konfiguration

Produktive Konfiguration:

```text
/etc/powergateway/config.toml
```

Regeln:

- neue Optionen mit sinnvollen Standardwerten versehen
- bestehende Konfigurationen bei Updates kompatibel halten
- Geheimnisse nicht protokollieren
- unbekannte Schlüssel möglichst tolerieren
- Migrationen ausdrücklich versionieren

## 6. Laufzeitdaten

Persistente Daten liegen unter:

```text
/var/lib/powergateway
```

Dazu können gehören:

- Statusdateien
- SQLite-Datenbanken
- Energiehistorie
- MQTT-Puffer
- Exporte
- Backups
- SSH-Schlüssel

Schreibzugriffe müssen atomar oder transaktional erfolgen. Dateirechte sind so restriktiv wie möglich zu setzen.

## 7. Datenquellen

Eine Datenquelle liefert normierte Messwerte an den Kern. Eine Implementierung sollte mindestens bieten:

- eindeutigen Typnamen
- Konfigurationsvalidierung
- Verbindungs- beziehungsweise Lesetest
- Start und Stop
- Status und Diagnose
- verständliche Fehler
- normierte Messwertstruktur

Bei SML sind unbekannte OBIS-Kennzahlen nicht zu verwerfen, sondern für Diagnosezwecke sichtbar zu machen.

## 8. MQTT und Home Assistant

MQTT-Code muss folgende Fälle behandeln:

- Broker vorübergehend nicht erreichbar
- fehlerhafte Zugangsdaten
- TLS- und Zertifikatsfehler
- Wiederverbindung
- lokaler Puffer
- geordnete Nachsendung
- Availability

Home-Assistant-Discovery darf nur gültige Sensorbeschreibungen erzeugen. Eindeutige IDs müssen über Updates stabil bleiben.

## 9. Weboberfläche und interne Endpunkte

Interne Endpunkte sind nicht automatisch eine öffentliche API. Änderungen dürfen bestehende Webfunktionen nicht stillschweigend brechen.

Für schreibende Aktionen gelten:

- Eingaben serverseitig validieren
- keine beliebigen Dateipfade akzeptieren
- keine Shell-Befehle aus Benutzereingaben zusammensetzen
- Fehlermeldungen verständlich, aber ohne Geheimnisse ausgeben
- sicherheitskritische Aktionen protokollieren

## 10. Backup und Restore

Backup-Dateien benötigen:

- Formatversion
- Erstellungszeit
- PowerGateway-Version
- Inhaltsverzeichnis oder Manifest
- Prüfsumme

Restore muss nach Möglichkeit in einem Staging-Verzeichnis erfolgen. Vor dem produktiven Ersetzen sind Format, Pfade und Prüfsummen zu validieren. Ein Rollback-Pfad ist vorzusehen.

## 11. Tests

Gesamte Testsuite:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Für neue Funktionen sind mindestens vorzusehen:

- Positivtest
- Validierungsfehler
- fehlende Abhängigkeit
- beschädigte oder unvollständige Eingabe
- Update-Kompatibilität, falls Konfiguration oder Daten geändert werden

Hardwareabhängige Funktionen zusätzlich auf realer Hardware testen.

## 12. Debian-Paket

Paketbau:

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Vor Freigabe prüfen:

- Paketversion stimmt mit `version.txt` überein
- systemd-Dateien enthalten korrekte Pfade
- Dienste werden nur sinnvoll aktiviert
- Konfiguration bleibt bei Update erhalten
- Deinstallation ohne `--purge` behält Nutzdaten
- Paket lässt sich auf einem sauberen Debian-System installieren

## 13. Versionierung

Entwicklungsstände verwenden das Suffix `-dev`. Vor einer Versionsänderung müssen mindestens aktualisiert werden:

- `version.txt`
- `CHANGELOG.md`
- betroffene Dokumentation
- Paketmetadaten, soweit nicht automatisch erzeugt

Eine stabile Version darf erst erstellt werden, wenn Installations-, Update-, Backup-, Restore- und Hardwaretests dokumentiert bestanden sind.

## 14. Pull-Request-Checkliste

- [ ] Funktion entspricht dem festgelegten Projektumfang
- [ ] keine Zugangsdaten oder Schlüssel enthalten
- [ ] Tests ergänzt und erfolgreich
- [ ] Fehlerfälle behandelt
- [ ] Dokumentation aktualisiert
- [ ] Changelog ergänzt
- [ ] Installation und Paketbau geprüft
- [ ] Raspberry-Pi-Ressourcen berücksichtigt
- [ ] Rückwärtskompatibilität bewertet

## 15. Einstieg in einen neuen Entwicklungs-Chat

Vor jeder Weiterentwicklung:

1. `NEUER_CHAT.md` lesen
2. `CHATGPT_PROJEKTKONTEXT.md` lesen
3. `version.txt`, `README.md`, `CHANGELOG.md` und Roadmap prüfen
4. aktuellen Branch und die letzten Commits kontrollieren
5. erst danach Änderungen vornehmen
