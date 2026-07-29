#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID} -ne 0 ]]; then echo "Bitte mit sudo ausführen: sudo bash install.sh" >&2; exit 1; fi
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/powergateway"; CONFIG_DIR="/etc/powergateway"; DATA_DIR="/var/lib/powergateway"; SYSTEMD_DIR="/etc/systemd/system"
TLS_DIR="${CONFIG_DIR}/tls"; ACME_DIR="${DATA_DIR}/acme"
echo "Installiere Systempakete ..."
apt-get update
apt-get install -y python3 python3-venv python3-pip usb-modeswitch modemmanager network-manager wireguard-tools sqlite3 openssh-client sudo nginx openssl certbot
if ! id powergateway >/dev/null 2>&1; then useradd --system --home "${DATA_DIR}" --shell /usr/sbin/nologin powergateway; fi
usermod -a -G dialout,plugdev powergateway
if getent group systemd-journal >/dev/null 2>&1; then usermod -a -G systemd-journal powergateway; fi
if id www-data >/dev/null 2>&1; then usermod -a -G powergateway www-data; fi
install -d -m 0755 "${INSTALL_DIR}" "${CONFIG_DIR}" /etc/wireguard
install -d -o powergateway -g powergateway -m 0750 "${DATA_DIR}"
install -d -o powergateway -g powergateway -m 0700 "${DATA_DIR}/.ssh"
install -d -o root -g powergateway -m 0755 "${ACME_DIR}"
install -d -o root -g powergateway -m 0755 "${ACME_DIR}/.well-known"
install -d -o root -g powergateway -m 0755 "${ACME_DIR}/.well-known/acme-challenge"
install -d -o root -g powergateway -m 0750 "${TLS_DIR}"
rm -rf "${INSTALL_DIR}/src" "${INSTALL_DIR}/venv"
cp -a "${PROJECT_DIR}/src" "${INSTALL_DIR}/src"
cp "${PROJECT_DIR}/version.txt" "${INSTALL_DIR}/version.txt"
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade pip wheel
"${INSTALL_DIR}/venv/bin/pip" install -r "${PROJECT_DIR}/requirements.txt"
if [[ ! -f "${CONFIG_DIR}/config.toml" ]]; then install -m 0640 -o root -g powergateway "${PROJECT_DIR}/config/config.example.toml" "${CONFIG_DIR}/config.toml"; else echo "Vorhandene Konfiguration bleibt erhalten."; install -m 0640 -o root -g powergateway "${PROJECT_DIR}/config/config.example.toml" "${CONFIG_DIR}/config.example.toml"; fi
for unit in powergateway.service powergateway-web.service powergateway-network.service powergateway-lte-proxy-address.service powergateway-lte-proxy.service powergateway-config-reload.service powergateway-config-reload.path powergateway-wireguard-apply.service powergateway-wireguard-apply.path powergateway-wireguard-status.service powergateway-wireguard-status.timer powergateway-ha-tunnel.service powergateway-noip.service powergateway-noip.timer; do install -m 0644 "${PROJECT_DIR}/packaging/systemd/${unit}" "${SYSTEMD_DIR}/${unit}"; done
install -d -m 0750 /etc/sudoers.d
install -m 0440 "${PROJECT_DIR}/packaging/sudoers/powergateway-ha-tunnel" /etc/sudoers.d/powergateway-ha-tunnel
install -m 0440 "${PROJECT_DIR}/packaging/sudoers/powergateway-certbot" /etc/sudoers.d/powergateway-certbot
install -m 0755 "${PROJECT_DIR}/packaging/scripts/powergateway-certbot" /usr/local/sbin/powergateway-certbot
visudo -cf /etc/sudoers.d/powergateway-ha-tunnel
visudo -cf /etc/sudoers.d/powergateway-certbot

# Lokales HTTPS-Zertifikat nur beim ersten Installieren erzeugen.
if [[ ! -s "${TLS_DIR}/powergateway.key" || ! -s "${TLS_DIR}/powergateway.crt" ]]; then
  HOSTNAME_FQDN="$(hostname -f 2>/dev/null || hostname)"
  HOSTNAME_SHORT="$(hostname)"
  PRIMARY_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
  SAN="DNS:${HOSTNAME_SHORT},DNS:${HOSTNAME_FQDN},DNS:powergateway.local"
  if [[ -n "${PRIMARY_IP}" ]]; then SAN="${SAN},IP:${PRIMARY_IP}"; fi
  rm -f "${TLS_DIR}/powergateway.key" "${TLS_DIR}/powergateway.crt"
  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
    -keyout "${TLS_DIR}/powergateway.key" \
    -out "${TLS_DIR}/powergateway.crt" \
    -subj "/CN=${HOSTNAME_SHORT}" \
    -addext "subjectAltName=${SAN}"
fi
chown root:powergateway "${TLS_DIR}/powergateway.key" "${TLS_DIR}/powergateway.crt"
chmod 0640 "${TLS_DIR}/powergateway.key"
chmod 0644 "${TLS_DIR}/powergateway.crt"

# Bestehende Let's-Encrypt-Installationen reparieren. Ältere Versionen legten
# Symlinks in geschützte /etc/letsencrypt-Verzeichnisse an, die der Webdienst
# nicht lesen konnte.
if [[ -f "${CONFIG_DIR}/letsencrypt.conf" ]]; then
  if ! /usr/local/sbin/powergateway-certbot deploy; then
    echo "Warnung: Vorhandenes Let's-Encrypt-Zertifikat konnte nicht neu bereitgestellt werden." >&2
  fi
fi

install -m 0644 "${PROJECT_DIR}/packaging/nginx/powergateway.conf" /etc/nginx/sites-available/powergateway
ln -sfn /etc/nginx/sites-available/powergateway /etc/nginx/sites-enabled/powergateway
rm -f /etc/nginx/sites-enabled/default
nginx -t

chown -R root:root "${INSTALL_DIR}"
chmod 0755 "${INSTALL_DIR}"/src/*.py
chown -R powergateway:powergateway "${DATA_DIR}"
chown root:powergateway "${ACME_DIR}" "${ACME_DIR}/.well-known" "${ACME_DIR}/.well-known/acme-challenge"
chmod 0750 "${DATA_DIR}"
chmod 0755 "${ACME_DIR}" "${ACME_DIR}/.well-known" "${ACME_DIR}/.well-known/acme-challenge"
chown root:powergateway "${CONFIG_DIR}" "${TLS_DIR}"
chmod 0755 "${CONFIG_DIR}"
chmod 0750 "${TLS_DIR}"
systemctl daemon-reload
systemctl enable powergateway-network.service powergateway.service powergateway-web.service powergateway-lte-proxy-address.service powergateway-lte-proxy.service powergateway-config-reload.path powergateway-wireguard-apply.path powergateway-wireguard-status.timer powergateway-noip.timer nginx certbot.timer
systemctl restart powergateway-network.service || true
systemctl restart powergateway-lte-proxy-address.service || true
systemctl restart powergateway.service powergateway-web.service powergateway-lte-proxy.service || true
systemctl restart powergateway-config-reload.path powergateway-wireguard-apply.path powergateway-wireguard-status.timer powergateway-noip.timer || true
systemctl restart nginx
systemctl start certbot.timer || true
if [[ -f "${DATA_DIR}/homeassistant_connector.json" ]] && grep -Eq '"mode"[[:space:]]*:[[:space:]]*"(ssh_mqtt|reverse_ssh_mqtt)"' "${DATA_DIR}/homeassistant_connector.json" && grep -Eq '"enabled"[[:space:]]*:[[:space:]]*true' "${DATA_DIR}/homeassistant_connector.json"; then
  systemctl enable --now powergateway-ha-tunnel.service || true
else
  systemctl disable --now powergateway-ha-tunnel.service >/dev/null 2>&1 || true
fi
if [[ -f "${DATA_DIR}/wireguard.json" ]]; then systemctl start powergateway-wireguard-apply.service || true; fi
PRIMARY_IP="$(hostname -I | awk '{print $1}')"
echo
echo "PowerGateway wurde installiert/aktualisiert."
echo "HTTPS-Weboberfläche: https://${PRIMARY_IP}/"
echo "Let's Encrypt: in der Weboberfläche unter HTTPS einrichten."
echo "Für HTTP-01 müssen Port 80 und 443 von außen erreichbar sein."
echo "Interner Webdienst: http://${PRIMARY_IP}:8080"
echo "LTE-Modem im Hotspot: http://192.168.50.254/"
echo "SSH-Tunnel: sudo systemctl status powergateway-ha-tunnel --no-pager -l"
echo "SSH-Logs: sudo journalctl -u powergateway-ha-tunnel -f"
