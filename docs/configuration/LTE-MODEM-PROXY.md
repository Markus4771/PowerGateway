# LTE-Modem-Weboberfläche im Hotspot

PowerGateway stellt die Weboberfläche eines LTE-Router-Sticks über eine feste Adresse im Setup-Hotspot bereit.

## Standardadressen

- Hotspot-Gateway: `192.168.50.1`
- LTE-Modem-Proxy: `192.168.50.254`
- internes LTE-Modem: `192.168.0.1`

Ein mit dem Hotspot verbundenes Gerät öffnet:

```text
http://192.168.50.254/
```

Der Dienst leitet HTTP-Anfragen intern an folgende Adresse weiter:

```text
http://192.168.0.1/
```

Dadurch muss der Client keine zusätzliche Route in das Modemnetz erhalten.

## Technische Umsetzung

- NetworkManager weist `wlan0` neben der Gateway-Adresse eine sekundäre Adresse zu.
- `powergateway-lte-proxy.service` lauscht ausschließlich auf `192.168.50.254:80`.
- Der Proxy unterstützt GET, POST, PUT, PATCH, DELETE, OPTIONS und HEAD.
- Weiterleitungen und Cookie-Domains des Modems werden für den Zugriff über die Proxy-Adresse angepasst.

## Status prüfen

```bash
ip address show wlan0
sudo systemctl status powergateway-lte-proxy --no-pager -l
curl -I http://192.168.50.254/
```

Auf `wlan0` sollten sowohl `192.168.50.1/24` als auch `192.168.50.254/24` vorhanden sein.

## Protokoll anzeigen

```bash
sudo journalctl -u powergateway-lte-proxy -f
```

## Sicherheit

Die Modemoberfläche wird nur an die dedizierte Hotspot-Adresse gebunden. Sie wird nicht auf LAN-, WireGuard- oder LTE-Uplink-Adressen veröffentlicht. Der Setup-Hotspot muss deshalb mit einem ausreichend starken WPA2-Passwort geschützt werden.
