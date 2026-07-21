#!/usr/bin/env python3
"""Lokale Benutzerverwaltung für die PowerGateway-WebGUI."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path
from typing import Any

ITERATIONS = 310_000


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    os.chmod(temporary, 0o600)
    temporary.replace(path)


def load_users(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {"users": {}}
    except (OSError, ValueError, json.JSONDecodeError):
        return {"users": {}}


def has_users(path: Path) -> bool:
    return bool(load_users(path).get("users"))


def _derive(password: str, salt: bytes, iterations: int = ITERATIONS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)


def validate_password(password: str) -> str | None:
    if len(password) < 10:
        return "Das Passwort muss mindestens 10 Zeichen lang sein."
    if password.lower() == password or password.upper() == password:
        return "Das Passwort muss Groß- und Kleinbuchstaben enthalten."
    if not any(character.isdigit() for character in password):
        return "Das Passwort muss mindestens eine Zahl enthalten."
    return None


def create_user(path: Path, username: str, password: str, role: str = "admin") -> None:
    username = username.strip().lower()
    if not username or not all(character.isalnum() or character in "._-" for character in username):
        raise ValueError("Ungültiger Benutzername.")
    error = validate_password(password)
    if error:
        raise ValueError(error)
    data = load_users(path)
    users = data.setdefault("users", {})
    if username in users:
        raise ValueError("Der Benutzer existiert bereits.")
    salt = secrets.token_bytes(16)
    users[username] = {
        "salt": salt.hex(),
        "hash": _derive(password, salt).hex(),
        "iterations": ITERATIONS,
        "role": role,
        "enabled": True,
        "must_change_password": False,
    }
    _atomic_write(path, data)


def verify_user(path: Path, username: str, password: str) -> dict[str, Any] | None:
    record = load_users(path).get("users", {}).get(username.strip().lower())
    if not isinstance(record, dict) or not record.get("enabled", False):
        return None
    try:
        salt = bytes.fromhex(str(record["salt"]))
        expected = bytes.fromhex(str(record["hash"]))
        actual = _derive(password, salt, int(record.get("iterations", ITERATIONS)))
    except (KeyError, TypeError, ValueError):
        return None
    return record if hmac.compare_digest(expected, actual) else None


def change_password(path: Path, username: str, new_password: str) -> None:
    error = validate_password(new_password)
    if error:
        raise ValueError(error)
    data = load_users(path)
    record = data.get("users", {}).get(username.strip().lower())
    if not isinstance(record, dict):
        raise ValueError("Benutzer nicht gefunden.")
    salt = secrets.token_bytes(16)
    record.update({
        "salt": salt.hex(),
        "hash": _derive(new_password, salt).hex(),
        "iterations": ITERATIONS,
        "must_change_password": False,
    })
    _atomic_write(path, data)


def list_users(path: Path) -> list[dict[str, Any]]:
    result = []
    for username, record in sorted(load_users(path).get("users", {}).items()):
        if isinstance(record, dict):
            result.append({
                "username": username,
                "role": record.get("role", "user"),
                "enabled": bool(record.get("enabled", False)),
            })
    return result
