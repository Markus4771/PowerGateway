# Messwert-Rohdatenexport

Ab Version `0.9.33-dev` zeichnet die Weboberfläche einen begrenzten Diagnoseverlauf der empfangenen Messwerte auf. Der Verlauf dient dazu, Einheiten, Zeitstempel, OBIS-Kennzahlen und die Darstellung in Home Assistant zu überprüfen.

## Download

1. Weboberfläche öffnen und anmelden.
2. Im Dashboard den Bereich **Rohmesswerte herunterladen** öffnen.
3. Einen einzelnen Messwert oder **Alle Messwerte** auswählen.
4. Zeitraum zwischen einer Stunde und sieben Tagen auswählen.
5. **CSV herunterladen** anklicken.

Die CSV-Datei enthält:

- Empfangszeitpunkt des Messwerts
- lokalen Aufzeichnungszeitpunkt
- aktive Datenquelle
- internen Messwertschlüssel
- Bezeichnung
- Rohwert nach der PowerGateway-OBIS-Dekodierung
- Einheit
- OBIS-Kennzahl
- SHA-256-Kennung des SML-Telegramms, soweit vorhanden

## Begrenzung

PowerGateway führt weiterhin keine Langzeitstatistik und keine eigenen historischen Diagramme. Standardmäßig werden höchstens 10.000 unterschiedliche Messwert-Snapshots gespeichert und maximal sieben Tage exportiert. Die dauerhafte Speicherung und Diagrammdarstellung bleibt Aufgabe von Home Assistant.

Die Ablage befindet sich standardmäßig unter:

```text
/var/lib/powergateway/measurement_history.jsonl
```

## Konfiguration über Umgebungsvariablen

- `POWERGATEWAY_MEASUREMENT_HISTORY_LIMIT`: maximale Anzahl gespeicherter Snapshots, Standard `10000`
- `POWERGATEWAY_MEASUREMENT_POLL_SECONDS`: Prüfintervall der letzten Messwertdatei, Standard `2`
- `POWERGATEWAY_MEASUREMENT_HISTORY`: alternativer Pfad der Diagnosehistorie

## Diagramm prüfen

Für die Fehlersuche sollten insbesondere folgende Spalten verglichen werden:

- Zeitstempel
- Messwertschlüssel und OBIS-Kennzahl
- Rohwert
- Einheit

Bei Energiezählern muss außerdem unterschieden werden, ob Home Assistant einen fortlaufenden Zählerstand oder eine momentane Leistung darstellt. Energie wird typischerweise in `kWh`, Leistung in `W` geführt.
