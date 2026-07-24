#!/usr/bin/env python3
"""Root-Helfer zum Anwenden des optionalen SSH-/Reverse-SSH-Tunnels."""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from homeassistant_connector import load_config

UNIT_PATH = Path("/etc/systemd/system/powergateway-ha-tunnel.service")


def _run(*args: str) -> None:
    subprocess.run(list(args), check=False, timeout=30)


def _unit(config: dict) -> str:
    mode = config.get("mode")
    binary = shutil.which("autossh") or shutil.which("ssh") or "/usr/bin/ssh"
    base = [binary]
    if Path(binary).name == "autossh":
        base += ["-M", "0"]
    base += [
        "-N", "-T",
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={config['known_hosts_file']}",
        "-i", config["identity_file"],
        "-p", str(config["ssh_port"]),
    ]
    if mode == "ssh_mqtt":
        base += ["-L", f"127.0.0.1:{config['local_mqtt_port']}:{config['remote_mqtt_host']}:{config['remote_mqtt_port']}"]
    elif mode == "reverse_ssh_mqtt":
        base += ["-R", f"{config['reverse_bind_host']}:{config['reverse_bind_port']}:{config['mqtt_host']}:{config['mqtt_port']}"]
    base += [f"{config['ssh_user']}@{config['ssh_host']}"]
    command = " ".join(subprocess.list2cmdline([part]) for part in base)
    return f"""[Unit]
Description=PowerGateway Home Assistant SSH Tunnel
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=powergateway
Group=powergateway
Environment=AUTOSSH_GATETIME=0
ExecStart={command}
Restart=always
RestartSec=10
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/powergateway

[Install]
WantedBy=multi-user.target
"""


def apply() -> None:
    config = load_config()
    enabled = bool(config.get("enabled")) and config.get("mode") in {"ssh_mqtt", "reverse_ssh_mqtt"}
    if not enabled:
        _run("systemctl", "disable", "--now", "powergateway-ha-tunnel.service")
        try:
            UNIT_PATH.unlink()
        except FileNotFoundError:
            pass
        _run("systemctl", "daemon-reload")
        return
    UNIT_PATH.write_text(_unit(config), encoding="utf-8")
    os.chmod(UNIT_PATH, 0o644)
    _run("systemctl", "daemon-reload")
    _run("systemctl", "enable", "--now", "powergateway-ha-tunnel.service")
    _run("systemctl", "restart", "powergateway-ha-tunnel.service")


if __name__ == "__main__":
    apply()
