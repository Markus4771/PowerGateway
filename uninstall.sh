#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Bitte mit sudo ausführen: sudo bash uninstall.sh" >&2
  exit 1
fi

PURGE=false
if [[ ${1:-} == "--purge" ]]; then
  PURGE=true
elif [[ -n ${1:-} ]]; then
  echo "Verwendung: sudo bash uninstall.sh [--purge]" >&2
  exit 2
fi

UNITS=(
  powergateway.service
  powergateway-web.service
  powergateway-network.service
  powergateway-config-reload.path
  powergateway-config-reload.service
  powergateway-wireguard-apply.path
  powergateway-wireguard-apply.service
  powergateway-wireguard-status.timer
  powergateway-wireguard-status.service
)

for unit in "${UNITS[@]}"; do
  systemctl disable --now "${unit}" >/dev/null 2>&1 || true
  rm -f "/etc/systemd/system/${unit}"
done

systemctl daemon-reload
systemctl reset-failed >/dev/null 2>&1 || true
rm -rf /opt/powergateway

if ${PURGE}; then
  rm -rf /etc/powergateway /var/lib/powergateway
  rm -f /etc/wireguard/powergateway-*.conf
  if id powergateway >/dev/null 2>&1; then
    userdel powergateway || true
  fi
  echo "PowerGateway wurde einschließlich Konfiguration und Daten entfernt."
else
  echo "PowerGateway wurde entfernt. Konfiguration und Daten bleiben erhalten:"
  echo "  /etc/powergateway"
  echo "  /var/lib/powergateway"
  echo "Für vollständiges Löschen: sudo bash uninstall.sh --purge"
fi
