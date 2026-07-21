#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo ./install.sh" >&2
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/powergateway"
CONFIG_DIR="/etc/powergateway"
DATA_DIR="/var/lib/powergateway"
SERVICE_FILE="/etc/systemd/system/powergateway.service"

echo "Installiere Systempakete ..."
apt-get update
apt-get install -y python3 python3-venv usb-modeswitch modemmanager network-manager wireguard-tools

if ! id powergateway >/dev/null 2>&1; then
  useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin powergateway
fi

install -d -m 0755 "${INSTALL_DIR}" "${CONFIG_DIR}"
install -d -o powergateway -g powergateway -m 0750 "${DATA_DIR}"

rm -rf "${INSTALL_DIR}/src" "${INSTALL_DIR}/venv"
cp -a "${PROJECT_DIR}/src" "${INSTALL_DIR}/src"
python3 -m venv "${INSTALL_DIR}/venv"

if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
  install -m 0640 -o root -g powergateway \
    "${PROJECT_DIR}/config/config.example.toml" \
    "${CONFIG_DIR}/config.toml"
fi

install -m 0644 \
  "${PROJECT_DIR}/packaging/systemd/powergateway.service" \
  "${SERVICE_FILE}"

chown -R root:root "${INSTALL_DIR}"
chmod 0755 "${INSTALL_DIR}/src/powergateway.py"

systemctl daemon-reload
systemctl enable --now powergateway.service

echo
echo "PowerGateway wurde installiert."
echo "Konfiguration: ${CONFIG_DIR}/config.toml"
echo "Status: sudo systemctl status powergateway --no-pager"
echo "Log: sudo journalctl -u powergateway -f"
