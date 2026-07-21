# Home Assistant anbinden

PowerGateway veröffentlicht Messwerte über MQTT und kann passende Sensoren per MQTT Discovery anlegen.

## Voraussetzungen

- MQTT-Broker erreichbar
- Home Assistant mit eingerichteter MQTT-Integration
- PowerGateway und Home Assistant verwenden denselben Broker

## Einrichtung

1. In PowerGateway **MQTT und Home Assistant** öffnen.
2. Brokerdaten eintragen und Verbindung testen.
3. **MQTT Discovery aktivieren** einschalten.
4. Discovery-Präfix normalerweise auf `homeassistant` lassen.
5. Gerätenamen festlegen.
6. speichern und anwenden.

## Erwartetes Ergebnis

In Home Assistant erscheint ein Gerät **PowerGateway** mit Sensoren für die vom Zähler gelieferten Messwerte, zum Beispiel:

- aktuelle Leistung
- Energiebezug
- Einspeisung
- Spannung je Phase
- Strom je Phase
- Frequenz

## Energie-Dashboard

Langzeitstatistiken, Diagramme sowie Tages-, Monats- und Jahresauswertungen werden in Home Assistant erstellt. PowerGateway selbst enthält dafür bewusst keine eigene Diagramm- oder Statistikoberfläche.

## Fehlersuche

- MQTT-Verbindung in PowerGateway testen
- MQTT-Integration in Home Assistant prüfen
- Discovery-Präfix vergleichen
- PowerGateway-Dienst neu starten
- Protokolle prüfen:

```bash
sudo journalctl -u powergateway -n 100 --no-pager
```

Entitäten können erst erscheinen, nachdem der Zähler mindestens einen gültigen Messwert geliefert hat.