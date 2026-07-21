# Debian-Paket bauen und installieren

## Voraussetzungen

Der Paketbau erfolgt auf Debian oder Raspberry Pi OS mit installiertem `dpkg-deb`.

```bash
sudo apt update
sudo apt install dpkg-dev
```

## Paket bauen

Im Repository:

```bash
chmod +x packaging/build_deb.sh
./packaging/build_deb.sh
```

Das Paket wird unter `dist/` erzeugt, beispielsweise:

```text
dist/powergateway_0.9.9~dev_all.deb
```

## Paket installieren

```bash
sudo apt install ./dist/powergateway_0.9.9~dev_all.deb
```

Während der Installation werden der Systembenutzer, die Python-Umgebung, die Konfiguration und die systemd-Dienste eingerichtet.

## Update

Ein neueres Paket kann direkt darüber installiert werden:

```bash
sudo apt install ./dist/powergateway_NEUE_VERSION_all.deb
```

Die Datei `/etc/powergateway/config.toml` bleibt als Konfigurationsdatei erhalten.

## Deinstallation über APT

Programm entfernen und Einstellungen behalten:

```bash
sudo apt remove powergateway
```

Programm einschließlich Paketkonfiguration entfernen:

```bash
sudo apt purge powergateway
```

## Deinstallation einer Installation mit install.sh

Programm entfernen, Konfiguration und Daten behalten:

```bash
sudo bash uninstall.sh
```

Vollständige Entfernung:

```bash
sudo bash uninstall.sh --purge
```

`--purge` entfernt zusätzlich `/etc/powergateway`, `/var/lib/powergateway` und den Systembenutzer `powergateway`. Vorher sollten benötigte Konfigurationsdateien gesichert werden.

## Kontrolle

```bash
sudo systemctl status powergateway powergateway-web powergateway-network --no-pager
journalctl -u powergateway -u powergateway-web -n 100 --no-pager
```
