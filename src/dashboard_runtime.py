#!/usr/bin/env python3
"""Zentrales Status-Dashboard und zusammengefasste PowerGateway-Diagnose."""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from flask import Response, jsonify

import plugin_webapp_base as _unused  # type: ignore[import-not-found]  # Dokumentiert den Ladepunkt; Fallback unten.
