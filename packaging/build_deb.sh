#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="$(tr -d '[:space:]' < "${ROOT_DIR}/version.txt")"
DEB_VERSION="${VERSION%-dev}~dev"
ARCH="all"
PKG="powergateway"
BUILD_ROOT="${ROOT_DIR}/dist/${PKG}_${DEB_VERSION}_${ARCH}"
OUTPUT="${ROOT_DIR}/dist/${PKG}_${DEB_VERSION}_${ARCH}.deb"

rm -rf "${BUILD_ROOT}"
mkdir -p \
  "${BUILD_ROOT}/DEBIAN" \
  "${BUILD_ROOT}/opt/powergateway" \
  "${BUILD_ROOT}/etc/powergateway" \
  "${BUILD_ROOT}/etc/systemd/system" \
  "${BUILD_ROOT}/usr/share/doc/powergateway"

cp -a "${ROOT_DIR}/src" "${BUILD_ROOT}/opt/powergateway/src"
cp -a "${ROOT_DIR}/requirements.txt" "${ROOT_DIR}/version.txt" "${BUILD_ROOT}/opt/powergateway/"

install -m 0640 "${ROOT_DIR}/config/config.example.toml" \
  "${BUILD_ROOT}/etc/powergateway/config.toml"
install -m 0644 "${ROOT_DIR}/config/config.example.toml" \
  "${BUILD_ROOT}/etc/powergateway/config.example.toml"

cp -a "${ROOT_DIR}/packaging/systemd/." "${BUILD_ROOT}/etc/systemd/system/"
cp -a "${ROOT_DIR}/README.md" "${ROOT_DIR}/CHANGELOG.md" "${BUILD_ROOT}/usr/share/doc/powergateway/"

cat > "${BUILD_ROOT}/DEBIAN/control" <<EOF
Package: ${PKG}
Version: ${DEB_VERSION}
Section: net
Priority: optional
Architecture: ${ARCH}
Maintainer: PowerGateway Project
Depends: python3, python3-venv, python3-pip, network-manager, modemmanager, wireguard-tools, qrencode, sqlite3
Description: Modulares Stromzaehler-Gateway fuer Raspberry Pi und Debian
 Liest USB-SML- und MQTT-Stromzaehler und uebertraegt Messwerte per MQTT
 inklusive Home-Assistant-Discovery.
EOF

cat > "${BUILD_ROOT}/DEBIAN/conffiles" <<'EOF'
/etc/powergateway/config.toml
EOF

cat > "${BUILD_ROOT}/DEBIAN/postinst" <<'EOF'
#!/usr/bin/env bash
set -e
if ! id powergateway >/dev/null 2>&1; then
  useradd --system --home /var/lib/powergateway --shell /usr/sbin/nologin powergateway
fi
usermod -a -G dialout,plugdev powergateway || true
getent group systemd-journal >/dev/null && usermod -a -G systemd-journal powergateway || true
install -d -o powergateway -g powergateway -m 0750 /var/lib/powergateway
install -d -m 0750 -o root -g powergateway /etc/powergateway
chown root:powergateway /etc/powergateway/config.toml /etc/powergateway/config.example.toml 2>/dev/null || true
chmod 0640 /etc/powergateway/config.toml 2>/dev/null || true
python3 -m venv /opt/powergateway/venv
/opt/powergateway/venv/bin/pip install --disable-pip-version-check --no-cache-dir -r /opt/powergateway/requirements.txt
chown -R root:root /opt/powergateway
chmod 0755 /opt/powergateway/src/*.py
systemctl daemon-reload
systemctl enable powergateway-network.service powergateway.service powergateway-web.service \
  powergateway-config-reload.path powergateway-wireguard-apply.path \
  powergateway-wireguard-status.timer
systemctl restart powergateway-network.service || true
systemctl restart powergateway.service powergateway-web.service || true
systemctl restart powergateway-config-reload.path powergateway-wireguard-apply.path \
  powergateway-wireguard-status.timer || true
EOF
chmod 0755 "${BUILD_ROOT}/DEBIAN/postinst"

cat > "${BUILD_ROOT}/DEBIAN/prerm" <<'EOF'
#!/usr/bin/env bash
set -e
for unit in powergateway.service powergateway-web.service powergateway-network.service \
  powergateway-config-reload.path powergateway-wireguard-apply.path \
  powergateway-wireguard-status.timer; do
  systemctl disable --now "$unit" >/dev/null 2>&1 || true
done
EOF
chmod 0755 "${BUILD_ROOT}/DEBIAN/prerm"

cat > "${BUILD_ROOT}/DEBIAN/postrm" <<'EOF'
#!/usr/bin/env bash
set -e
systemctl daemon-reload || true
if [[ ${1:-} == purge ]]; then
  rm -rf /var/lib/powergateway
  userdel powergateway >/dev/null 2>&1 || true
fi
EOF
chmod 0755 "${BUILD_ROOT}/DEBIAN/postrm"

mkdir -p "$(dirname "${OUTPUT}")"
dpkg-deb --root-owner-group --build "${BUILD_ROOT}" "${OUTPUT}"
echo "Debian-Paket erstellt: ${OUTPUT}"
