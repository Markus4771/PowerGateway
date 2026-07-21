#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT}/version.txt")"
PACKAGE_VERSION="${VERSION%-dev}"
BUILD="${ROOT}/build/powergateway_${PACKAGE_VERSION}_all"
OUTPUT="${ROOT}/dist"

rm -rf "${BUILD}"
mkdir -p "${BUILD}/DEBIAN" "${BUILD}/opt/powergateway/src" \
  "${BUILD}/etc/powergateway" "${BUILD}/var/lib/powergateway" \
  "${BUILD}/lib/systemd/system" "${OUTPUT}"

cp -a "${ROOT}/src/." "${BUILD}/opt/powergateway/src/"
cp "${ROOT}/version.txt" "${BUILD}/opt/powergateway/version.txt"
cp "${ROOT}/config/config.example.toml" "${BUILD}/etc/powergateway/config.toml"
cp "${ROOT}/packaging/systemd/powergateway.service" "${BUILD}/lib/systemd/system/"
cp "${ROOT}/packaging/systemd/powergateway-web.service" "${BUILD}/lib/systemd/system/"

cat > "${BUILD}/DEBIAN/control" <<EOF
Package: powergateway
Version: ${PACKAGE_VERSION}
Section: utils
Priority: optional
Architecture: all
Maintainer: PowerGateway Project
Depends: python3 (>= 3.11), python3-flask, python3-serial, python3-paho-mqtt, gunicorn, modemmanager, network-manager, usb-modeswitch, wireguard-tools, sqlite3
Description: Raspberry-Pi Stromzaehler-Gateway mit LTE, MQTT und Weboberflaeche
 Liest SML-Stromzaehler ueber einen USB-IR-Lesekopf aus und uebertraegt
 Messwerte per MQTT an Home Assistant.
EOF

cat > "${BUILD}/DEBIAN/conffiles" <<EOF
/etc/powergateway/config.toml
EOF

cat > "${BUILD}/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
if ! getent group powergateway >/dev/null; then addgroup --system powergateway; fi
if ! getent passwd powergateway >/dev/null; then
  adduser --system --ingroup powergateway --home /var/lib/powergateway --no-create-home --disabled-login powergateway
fi
adduser powergateway dialout >/dev/null 2>&1 || true
adduser powergateway plugdev >/dev/null 2>&1 || true
chown -R powergateway:powergateway /var/lib/powergateway
chmod 0750 /var/lib/powergateway
systemctl daemon-reload || true
systemctl enable powergateway.service powergateway-web.service || true
systemctl restart powergateway.service powergateway-web.service || true
EOF
chmod 0755 "${BUILD}/DEBIAN/postinst"

cat > "${BUILD}/DEBIAN/prerm" <<'EOF'
#!/bin/sh
set -e
if [ "$1" = remove ]; then
  systemctl stop powergateway-web.service powergateway.service || true
fi
EOF
chmod 0755 "${BUILD}/DEBIAN/prerm"

chmod 0755 "${BUILD}/opt/powergateway/src/service.py" "${BUILD}/opt/powergateway/src/webapp.py"
chmod 0640 "${BUILD}/etc/powergateway/config.toml"
dpkg-deb --build --root-owner-group "${BUILD}" "${OUTPUT}/powergateway_${PACKAGE_VERSION}_all.deb"
echo "Erstellt: ${OUTPUT}/powergateway_${PACKAGE_VERSION}_all.deb"
