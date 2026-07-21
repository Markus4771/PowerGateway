#!/usr/bin/env bash
set -u

echo "=== PowerGateway Diagnose ==="
echo "Zeit: $(date --iso-8601=seconds)"
echo

echo "--- System ---"
uname -a
if command -v vcgencmd >/dev/null 2>&1; then
  echo "Raspberry-Pi-Drosselstatus: $(vcgencmd get_throttled 2>/dev/null || true)"
fi

echo
echo "--- USB-Geräte ---"
lsusb 2>/dev/null || true

echo
echo "--- Serielle Geräte ---"
ls -l /dev/serial/by-id /dev/ttyUSB* /dev/ttyACM* 2>/dev/null || echo "Keine seriellen Geräte gefunden"

echo
echo "--- ModemManager ---"
systemctl is-active ModemManager 2>/dev/null || true
mmcli -L 2>/dev/null || true

echo
echo "--- Netzwerk ---"
ip -brief address 2>/dev/null || true
ip route 2>/dev/null || true

echo
echo "--- WireGuard ---"
wg show 2>/dev/null || true

echo
echo "--- PowerGateway ---"
systemctl status powergateway --no-pager -l 2>/dev/null || true

echo
echo "--- Statusdatei ---"
cat /var/lib/powergateway/status.json 2>/dev/null || echo "Noch keine Statusdatei"

echo
echo "--- Letzte Protokollzeilen ---"
journalctl -u powergateway -n 100 --no-pager 2>/dev/null || true
