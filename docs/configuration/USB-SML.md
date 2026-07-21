# USB-SML konfigurieren

## Voraussetzungen

- kompatibler USB-Infrarot-Lesekopf
- Lesekopf korrekt am Stromzähler positioniert
- Zugriff auf die serielle Schnittstelle

## Einrichtung in der WebGUI

1. **Stromzähler** öffnen.
2. **USB-SML-Lesekopf** auswählen.
3. Gerät auf `auto` lassen oder einen Pfad aus `/dev/serial/by-id/` wählen.
4. Baudrate einstellen, üblicherweise `9600`.
5. speichern und anwenden.

Unter **Einrichtung** können erkannte serielle Geräte gesucht und direkt übernommen werden.

## Geräte auf der Konsole prüfen

```bash
ls -l /dev/serial/by-id/
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
```

## Dienstprotokoll

```bash
sudo journalctl -u powergateway -f
```

## Häufige Probleme

### Gerät wird nicht gefunden

- USB-Kabel und Lesekopf prüfen
- anderen USB-Port verwenden
- Gerät nach einem Neustart erneut prüfen
- Gruppenrechte für die serielle Schnittstelle kontrollieren

### Keine Telegramme

- Lesekopf neu ausrichten
- Baudrate prüfen
- prüfen, ob der Zähler SML oder ein anderes Protokoll ausgibt
- gegebenenfalls die Datenschnittstelle am Zähler freischalten

### Werte fehlen

Nicht jeder Zähler liefert dieselben OBIS-Kennzahlen. Unbekannte Kennzahlen sollen im Diagnosebereich sichtbar gemacht und später der OBIS-Registry hinzugefügt werden.