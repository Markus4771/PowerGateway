# PowerGateway Phase 4 – Adaptive Diagrammauflösung

Versionsstand: **1.4.4-dev**

## Ziel

Die Energiegraphik soll unabhängig vom ausgewählten Zeitraum und von der Bildschirmbreite flüssig bleiben, ohne vorhandene Rohdaten unnötig zu verwerfen.

## Umsetzung

- neue API `/_internal/energy/adaptive-history`
- automatische Zielgröße zwischen 300 und 2.000 Diagrammpunkten
- Standardwert etwa 1,35 Punkte je sichtbarem Pixel der Diagrammbreite
- serverseitige Wahl eines gut lesbaren Zeitintervalls
- erneute Datenabfrage nach Zoom, Zoom-Reset und Größenänderung des Browserfensters
- Speicherung der Rohmesswerte bleibt unverändert
- Antwort enthält Durchschnitt, Minimum und Maximum der Leistung je Intervall
- Anzeige von Punktzahl, gewählter Auflösung und Anzahl zugrunde liegender Rohwerte
- Schutz vor ungültigen oder extrem großen Abfragen

## Adaptive Intervalle

Unterstützte Verdichtungsstufen reichen von 5 Sekunden bis zu einer Woche. Das kleinste mögliche Intervall wird zusätzlich durch das konfigurierte Erfassungsintervall begrenzt.

## Prüfung

1. Energiegraphik öffnen.
2. Zeitraum „Heute“ und anschließend „Dieses Jahr“ auswählen.
3. In beiden Ansichten die angezeigte Punktzahl und Auflösung prüfen.
4. Mehrfach hineinzoomen. Die angezeigte Auflösung muss feiner werden.
5. Browserfenster vergrößern und verkleinern. Die Punktzahl soll sich anpassen.
6. Zoom zurücksetzen und prüfen, ob der vollständige Zeitraum erneut geladen wird.

Die praktische Laufzeitprüfung erfolgt auf dem PowerGateway-Gerät.
