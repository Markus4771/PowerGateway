#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo bash install.sh" >&2
  exit 1
fi

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/powergateway"
CONFIG_DIR="/etc/powergateway"
DATA_DIR="/var/lib/powergateway"
SERVICE_FILE="/etc/systemd/system/powergateway.service"
WEB_SERVICE_FILE="/etc/systemd/system/powergateway-web.service"
NETWORK_SERVICE_FILE="/etc/systemd/system/powergateway-network.service"

echo "Installiere Systempakete ..."
apt-get update
apt-get install -y python3 python3-venv python3-pip usb-modeswitch modemmanager network-manager wireguard-tools sqlite3

if ! id powergateway >/dev/null 2>&1; then
  useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin powergateway
fi
usermod -a -G dialout,plugdev powergateway

install -d -m 0755 "${INSTALL_DIR}" "${CONFIG_DIR}"
install -d -o powergateway -g powergateway -m 0750 "${DATA_DIR}"

rm -rf "${INSTALL_DIR}/src" "${INSTALL_DIR}/venv"
cp -a "${PROJECT_DIR}/src" "${INSTALL_DIR}/src"
cp "${PROJECT_DIR}/version.txt" "${INSTALL_DIR}/version.txt"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip wheel
"${INSTALL_DIR}/venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"

if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then
  install -m 0640 -o root -g powergateway \
    "${PROJECT_DIR}/config/config.example.toml" \
    "${CONFIG_DIR}/config.toml"
else
  echo "Vorhandene Konfiguration bleibt erhalten."
  install -m 0640 -o root -g powergateway \
    "${PROJECT_DIR}/config/config.example.toml" \
    "${CONFIG_DIR}/config.example.toml"
fi

install -m 0644 "${PROJECT_DIR}/packaging/systemd/powergateway.service" "${SERVICE_FILE}"
install -m 0644 "${PROJECT_DIR}/packaging/systemd/powergateway-web.service" "${WEB_SERVICE_FILE}"
install -m 0644 "${PROJECT_DIR}/packaging/systemd/powergateway-network.service" "${NETWORK_SERVICE_FILE}"

chown -R root:root "${INSTALL_DIR}"
chmod 0755 "${INSTALL_DIR}/src/powergateway.py" "${INSTALL_DIR}/src/service.py" "${INSTALL_DIR}/src/webapp.py" "${INSTALL_DIR}/src/networkctl.py"
chown powergateway:powergateway "${DATA_DIR}"

systemctl daemon-reload
systemctl enable powergateway-network.service powergateway.service powergateway-web.service
systemctl restart powergateway-network.service
systemctl restart powergateway.service powergateway-web.service

echo
echo "PowerGateway wurde installiert/aktualisiert."
echo "Konfiguration: ${CONFIG_DIR}/config.toml"
echo "Statusdatei: ${DATA_DIR}/status.json"
echo "Netzwerkstatus: ${DATA_DIR}/network_status.json"
echo "Dienststatus: sudo systemctl status powergateway-network powergateway powergateway-web --no-pager"
echo "Log: sudo journalctl -u powergateway-network -u powergateway -u powergateway-web -f"
echo "Weboberfläche: http://$(hostname -I | awk '{print $1}'):8080"
echo "Netzwerk: nmcli device status"
echo "LTE: mmcli -L"
