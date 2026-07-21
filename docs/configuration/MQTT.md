# MQTT konfigurieren

## Brokerdaten

In der WebGUI unter **MQTT und Home Assistant** eintragen:

- Broker/IP-Adresse
- Port, normalerweise `1883`
- Benutzername und Passwort
- optional TLS und CA-Datei
- Topic-Präfix

## Verbindung testen

Die Schaltfläche **Broker-Verbindung testen** baut eine echte MQTT-Verbindung auf. Dabei werden Anmeldung und TLS geprüft.

## Tasmota oder Generic MQTT als Quelle

Unter **Stromzähler** die Quelle auswählen und danach:

1. Brokerdaten eintragen.
2. Verbindung testen.
3. Topics suchen.
4. passendes Topic auswählen.
5. Nachricht empfangen.
6. erkannte JSON-Felder übernehmen.
7. speichern und anwenden.

## Beispiel Tasmota

Topic:

```text
tele/Stromzaehler/SENSOR
```

Nachricht:

```json
{"Home":{"Power_curr":245,"total_in":41222.86,"total_out":123.45}}
```

Zuordnung:

- Leistung: `Home.Power_curr`
- Bezug: `Home.total_in`
- Einspeisung: `Home.total_out`

## Fehlersuche

```bash
sudo journalctl -u powergateway -n 100 --no-pager
```

Prüfen:
- Broker erreichbar
- Port korrekt
- Zugangsdaten korrekt
- Topic exakt geschrieben
- Firewall erlaubt die Verbindung
- TLS-Zertifikat ist vertrauenswürdig