#!/usr/bin/env python3
"""Wendet die WebGUI-WireGuard-Konfiguration als root an."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from wireguard_manager import CONFIG_PATH, STATUS_PATH, export_conf, load_config, validate_config

WG_DIR = Path("/etc/wireguard")


def run(command: list[str], timeout: float = 20.0) -> tuple[bool, str]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        output = (result.stdout or result.stderr).strip()
        return result.returncode == 0, output
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)


def atomic_text(path: Path, text: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def write_status(value: dict[str, Any]) -> None:
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATUS_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(temporary, 0o640)
    try:
        import pwd
        account = pwd.getpwnam("powergateway")
        os.chown(temporary, account.pw_uid, account.pw_gid)
    except (KeyError, PermissionError):
        pass
    os.replace(temporary, STATUS_PATH)


def collect_status(interface: str, message: str = "") -> dict[str, Any]:
    ok, output = run(["wg", "show", interface, "dump"])
    status: dict[str, Any] = {
        "interface": interface,
        "active": ok,
        "state": "verbunden" if ok else "getrennt",
        "message": message or ("Tunnel aktiv" if ok else output or "Tunnel nicht aktiv"),
        "latest_handshake": 0,
        "received_bytes": 0,
        "sent_bytes": 0,
        "endpoint": "",
        "updated_at": int(time.time()),
    }
    if ok:
        rows = output.splitlines()
        if len(rows) > 1:
            columns = rows[1].split("\t")
            if len(columns) >= 8:
                status.update({
                    "endpoint": columns[2],
                    "latest_handshake": int(columns[4] or 0),
                    "received_bytes": int(columns[5] or 0),
                    "sent_bytes": int(columns[6] or 0),
                })
    return status


def apply() -> int:
    try:
        config = validate_config(load_config())
    except Exception as exc:
        write_status({"active": False, "state": "fehler", "message": str(exc), "updated_at": int(time.time())})
        return 1
    interface = config["interface"]
    conf_path = WG_DIR / f"{interface}.conf"
    service = f"wg-quick@{interface}.service"
    if not config["enabled"]:
        run(["systemctl", "disable", "--now", service])
        write_status(collect_status(interface, "WireGuard ist deaktiviert"))
        return 0
    atomic_text(conf_path, export_conf(config), 0o600)
    if config.get("autostart", True):
        run(["systemctl", "enable", service])
    else:
        run(["systemctl", "disable", service])
    ok, output = run(["systemctl", "restart", service], 30)
    status = collect_status(interface, output)
    if not ok:
        status.update({"active": False, "state": "fehler", "message": output or "Tunnelstart fehlgeschlagen"})
    write_status(status)
    return 0 if ok else 1


def status_only() -> int:
    config = load_config()
    interface = str(config.get("interface", "wg0"))
    write_status(collect_status(interface))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(status_only() if "--status" in sys.argv else apply())
