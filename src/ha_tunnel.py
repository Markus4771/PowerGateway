#!/usr/bin/env python3
"""Startet den konfigurierten SSH- oder Reverse-SSH-MQTT-Tunnel."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from homeassistant_connector import load_config, validate_config

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
STATUS_PATH = DATA_DIR / "ha_tunnel_status.json"
_process: subprocess.Popen[str] | None = None


def _atomic(value: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{STATUS_PATH.name}.", dir=STATUS_PATH.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.chmod(temporary, 0o640)
        os.replace(temporary, STATUS_PATH)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def command(config: dict[str, Any]) -> list[str]:
    config = validate_config(config)
    mode = config["mode"]
    if mode not in {"ssh_mqtt", "reverse_ssh_mqtt"}:
        raise ValueError("Für die gewählte Verbindungsart wird kein SSH-Tunnel benötigt")
    ssh = shutil.which("ssh")
    if not ssh:
        raise ValueError("OpenSSH-Client ist nicht installiert")
    identity = Path(config["identity_file"])
    if not identity.is_file():
        raise ValueError(f"SSH-Schlüssel fehlt: {identity}")
    known_hosts = Path(config["known_hosts_file"])
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    known_hosts.touch(mode=0o600, exist_ok=True)
    common = [
        ssh, "-N", "-T",
        "-p", str(config["ssh_port"]),
        "-i", str(identity),
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", "ConnectTimeout=15",
        "-o", "TCPKeepAlive=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"UserKnownHostsFile={known_hosts}",
    ]
    if mode == "ssh_mqtt":
        forward = f"127.0.0.1:{config['local_mqtt_port']}:{config['remote_mqtt_host']}:{config['remote_mqtt_port']}"
        common += ["-L", forward]
    else:
        forward = f"{config['reverse_bind_host']}:{config['reverse_bind_port']}:{config['remote_mqtt_host']}:{config['remote_mqtt_port']}"
        common += ["-R", forward]
    common.append(f"{config['ssh_user']}@{config['ssh_host']}")
    return common


def stop(_signum: int, _frame: object) -> None:
    global _process
    if _process and _process.poll() is None:
        _process.terminate()
        try:
            _process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            _process.kill()
    raise SystemExit(0)


def main() -> int:
    global _process
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    config = load_config()
    if not config.get("enabled") or config.get("mode") not in {"ssh_mqtt", "reverse_ssh_mqtt"}:
        _atomic({"active": False, "state": "disabled", "message": "SSH-Tunnel ist nicht aktiviert", "updated_at": int(time.time())})
        return 0
    try:
        cmd = command(config)
    except ValueError as exc:
        _atomic({"active": False, "state": "configuration_error", "message": str(exc), "updated_at": int(time.time())})
        print(str(exc), file=sys.stderr)
        return 2
    _atomic({"active": False, "state": "starting", "mode": config["mode"], "host": config["ssh_host"], "updated_at": int(time.time())})
    _process = subprocess.Popen(cmd, text=True)
    _atomic({"active": True, "state": "running", "mode": config["mode"], "host": config["ssh_host"], "pid": _process.pid, "updated_at": int(time.time())})
    code = _process.wait()
    _atomic({"active": False, "state": "stopped", "mode": config["mode"], "host": config["ssh_host"], "exit_code": code, "updated_at": int(time.time())})
    return code


if __name__ == "__main__":
    raise SystemExit(main())
