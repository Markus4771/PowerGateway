#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Bitte mit sudo ausführen: sudo bash install.sh" >&2; exit 1; fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/powergateway"; CONFIG_DIR="/etc/powergateway"; DATA_DIR="/var/lib/powergateway"; SYSTEMD_DIR="/etc/systemd/system"
echo "Installiere Systempakete ..."
apt-get update
apt-get install -y python3 python3-venv python3-pip usb-modeswitch modemmanager network-manager wireguard-tools sqlite3 openssh-client sudo
if ! id powergateway >/dev/null 2>&1; then useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin powergateway; fi
usermod -a -G dialout,plugdev powergateway
if getent group systemd-journal >/dev/null 2>&1; then usermod -a -G systemd-journal powergateway; fi
install -d -m 0755 "${INSTALL_DIR}" "${CONFIG_DIR}" /etc/wireguard
install -d -o powergateway -g powergateway -m 0750 "${DATA_DIR}"
install -d -o powergateway -g powergateway -m 0700 "${DATA_DIR}/.ssh"
rm -rf "${INSTALL_DIR}/src" "${INSTALL_DIR}/venv"
cp -a "${PROJECT_DIR}/src" "${INSTALL_DIR}/src"
cp "${PROJECT_DIR}/version.txt" "${INSTALL_DIR}/version.txt"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip wheel
"${INSTALL_DIR}/venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"
if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then install -m 0640 -o root -g powergateway "${PROJECT_DIR}/config/config.example.toml" "${CONFIG_DIR}/config.toml"; else echo "Vorhandene Konfiguration bleibt erhalten."; install -m 0640 -o root -g powergateway "${PROJECT_DIR}/config/config.example.toml" "${CONFIG_DIR}/config.example.toml"; fi
for unit in powergateway.service powergateway-web.service powergateway-network.service powergateway-config-reload.service powergateway-config-reload.path powergateway-wireguard-apply.service powergateway-wireguard-apply.path powergateway-wireguard-status.service powergateway-wireguard-status.timer powergateway-ha-tunnel.service powergateway-noip.service powergateway-noip.timer; do install -m 0644 "${PROJECT_DIR}/packaging/systemd/${unit}" "${SYSTEMD_DIR}/${unit}"; done
install -d -m 0750 /etc/sudoers.d
install -m 0440 "${PROJECT_DIR}/packaging/sudoers/powergateway-ha-tunnel" /etc/sudoers.d/powergateway-ha-tunnel
visudo -cf /etc/sudoers.d/powergateway-ha-tunnel
chown -R root:root "${INSTALL_DIR}"
chmod 0755 "${INSTALL_DIR}"/src/*.py
chown -R powergateway:powergateway "${DATA_DIR}"
systemctl daemon-reload
systemctl enable powergateway-network.service powergateway.service powergateway-web.service powergateway-config-reload.path powergateway-wireguard-apply.path powergateway-wireguard-status.timer powergateway-noip.timer
systemctl restart powergateway-network.service || true
systemctl restart powergateway.service powergateway-web.service || true
systemctl restart powergateway-config-reload.path powergateway-wireguard-apply.path powergateway-wireguard-status.timer powergateway-noip.timer || true
if [[ -f "${DATA_DIR}/homeassistant_connector.json" ]] && grep -Eq '"mode"[[:space:]]*:[[:space:]]*"(ssh_mqtt|reverse_ssh_mqtt)"' "${DATA_DIR}/homeassistant_connector.json" && grep -Eq '"enabled"[[:space:]]*:[[:space:]]*true' "${DATA_DIR}/homeassistant_connector.json"; then
  systemctl enable --now powergateway-ha-tunnel.service || true
else
  systemctl disable --now powergateway-ha-tunnel.service >/dev/null 2>&1 || true
fi
if [[ -f "${DATA_DIR}/wireguard.json" ]]; then systemctl start powergateway-wireguard-apply.service || true; fi
echo
echo "PowerGateway wurde installiert/aktualisiert."
echo "Weboberfläche: http://$(hostname -I | awk '{print $1}'):8080"
echo "SSH-Tunnel: sudo systemctl status powergateway-ha-tunnel --no-pager -l"
echo "SSH-Logs: sudo journalctl -u powergateway-ha-tunnel -f"
