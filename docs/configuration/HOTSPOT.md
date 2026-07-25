# PowerGateway-Setup-Hotspot

## Version 0.9.30-dev

Der Setup-Hotspot wird durch ein eigenständiges PowerGateway-Modul verwaltet. Das Modul verwendet weiterhin NetworkManager, legt das WLAN-Profil aber bei jedem Neuaufbau vollständig neu an. Dadurch werden alte oder unvollständige Sicherheitseinstellungen zuverlässig entfernt.

## Standardwerte

- SSID: `PowerGateway-Setup`
- Passwort: `powergateway`
- Adresse: `192.168.50.1/24`
- Frequenzband: 2,4 GHz
- Kanal: 6
- Verschlüsselung: WPA2-Personal (RSN) mit AES/CCMP
- PMF: optional
- WPS-PIN: nicht verwendet

## Windows 11

Windows 11 soll direkt die Eingabe des Netzwerksicherheitsschlüssels anbieten. Bei einem bereits gespeicherten alten WLAN-Profil muss dieses unter **Einstellungen → Netzwerk und Internet → WLAN → Bekannte Netzwerke verwalten** entfernt und anschließend neu verbunden werden.

## Aktualisierung eines vorhandenen Systems

Nach Installation von 0.9.30-dev den Netzwerkcontroller neu starten:

```bash
sudo systemctl restart powergateway-network.service
```

Der Controller löscht das alte Profil `PowerGateway-Setup` und erstellt es mit den gehärteten Einstellungen neu.

## Diagnose

```bash
nmcli connection show PowerGateway-Setup
nmcli -f 802-11-wireless,802-11-wireless-security connection show PowerGateway-Setup
journalctl -u powergateway-network.service -n 100 --no-pager
```

Erwartete Kerneinstellungen:

```text
802-11-wireless.mode: ap
802-11-wireless.band: bg
802-11-wireless.channel: 6
802-11-wireless-security.key-mgmt: wpa-psk
802-11-wireless-security.proto: rsn
802-11-wireless-security.pairwise: ccmp
802-11-wireless-security.group: ccmp
```
