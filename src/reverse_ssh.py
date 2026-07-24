#!/usr/bin/env python3
"""Dauerhafter Reverse-SSH-Tunnel für den Fernzugriff auf PowerGateway."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.environ.get("POWERGATEWAY_DATA_DIR", "/var/lib/powergateway"))
CONFIG_PATH = DATA_DIR / "reverse_ssh.json"
STATUS_PATH = DATA_DIR / "reverse_ssh_status.json"
KEY_PATH = DATA_DIR / ".ssh" / "reverse_ssh_ed25519"

DEFAULTS: dict[str, Any] = {
    "enabled": False,
    "server": "",
    "server_port": 22,
    "username": "powergateway",
    "remote_bind_address": "127.0.0.1",
    "remote_port": 2222,
    "local_host": "127.0.0.1",
    "local_port": 22,
    "keepalive_interval": 30,
    "keepalive_count_max": 3,
}


def load_config() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        raw = {}
    return {**DEFAULTS, **(raw if isinstance(raw, dict) else {})}


def write_status(**values: Any) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    current: dict[str, Any] = {}
    try:
        current = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    current.update(values)
    current["updated_at"] = int(time.time())
    STATUS_PATH.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")


def validate(config: dict[str, Any]) -> dict[str, Any]:
    cfg = {**DEFAULTS, **config}
    if not cfg.get("enabled"):
        raise ValueError("Reverse-SSH ist nicht aktiviert.")
    if not str(cfg.get("server", "")).strip():
        raise ValueError("Der SSH-Server fehlt.")
    if not str(cfg.get("username", "")).strip():
        raise ValueError("Der SSH-Benutzer fehlt.")
    for key, low, high in (("server_port", 1, 65535), ("remote_port", 1, 65535), ("local_port", 1, 65535)):
        try:
            cfg[key] = int(cfg[key])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Ungültiger Wert für {key}.") from exc
        if not low <= cfg[key] <= high:
            raise ValueError(f"{key} liegt außerhalb des gültigen Bereichs.")
    return cfg


def command(config: dict[str, Any]) -> list[str]:
    cfg = validate(config)
    return [
        "/usr/bin/ssh", "-NT",
        "-i", str(KEY_PATH),
        "-p", str(cfg["server_port"]),
        "-o", "BatchMode=yes",
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ServerAliveInterval={int(cfg.get('keepalive_interval', 30))}",
        "-o", f"ServerAliveCountMax={int(cfg.get('keepalive_count_max', 3))}",
        "-o", "ConnectTimeout=15",
        "-R", f"{cfg['remote_bind_address']}:{cfg['remote_port']}:{cfg['local_host']}:{cfg['local_port']}",
        f"{cfg['username']}@{cfg['server']}",
    ]


def main() -> int:
    try:
        cfg = validate(load_config())
        if not KEY_PATH.exists():
            raise ValueError("SSH-Schlüssel fehlt. Bitte in der WebGUI erzeugen.")
        cmd = command(cfg)
        write_status(state="starting", ok=False, command=" ".join(shlex.quote(v) for v in cmd), error="")
        process = subprocess.Popen(cmd)
        write_status(state="running", ok=True, pid=process.pid, started_at=int(time.time()))
        rc = process.wait()
        write_status(state="stopped", ok=False, returncode=rc, error=f"SSH wurde mit Code {rc} beendet.")
        return rc
    except Exception as exc:
        write_status(state="error", ok=False, error=str(exc))
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
