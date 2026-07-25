#!/usr/bin/env python3
"""Dedizierter Reverse Proxy für die Weboberfläche des LTE-Modems.

Der Dienst wird ausschließlich auf der sekundären Hotspot-Adresse
192.168.50.254:80 veröffentlicht und leitet zum Modem im Uplink-Netz weiter.
"""
from __future__ import annotations

import os
from http.client import HTTPResponse
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler

from flask import Flask, Response, request

app = Flask(__name__)
TARGET = os.environ.get("POWERGATEWAY_LTE_PROXY_TARGET", "http://192.168.0.1/").rstrip("/") + "/"
PUBLIC_ORIGIN = os.environ.get("POWERGATEWAY_LTE_PROXY_PUBLIC_ORIGIN", "http://192.168.50.254").rstrip("/")
TIMEOUT = float(os.environ.get("POWERGATEWAY_LTE_PROXY_TIMEOUT", "15"))

HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


OPENER = build_opener(_NoRedirect())


def _target_url(path: str) -> str:
    suffix = path.lstrip("/")
    url = urljoin(TARGET, suffix)
    if request.query_string:
        url += "?" + request.query_string.decode("latin-1")
    return url


def _request_headers() -> dict[str, str]:
    headers: dict[str, str] = {}
    target_host = urlparse(TARGET).netloc
    for name, value in request.headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP or lower in {"host", "content-length"}:
            continue
        headers[name] = value
    headers["Host"] = target_host
    headers["X-Forwarded-For"] = request.remote_addr or ""
    headers["X-Forwarded-Host"] = request.host
    headers["X-Forwarded-Proto"] = request.scheme
    return headers


def _response(upstream: HTTPResponse | HTTPError) -> Response:
    body = upstream.read()
    headers: list[tuple[str, str]] = []
    target_origin = TARGET.rstrip("/")
    for name, value in upstream.headers.items():
        lower = name.lower()
        if lower in HOP_BY_HOP or lower == "content-length":
            continue
        if lower == "location":
            absolute = urljoin(TARGET, value)
            if absolute.startswith(target_origin):
                value = PUBLIC_ORIGIN + absolute[len(target_origin):]
        elif lower == "set-cookie":
            # Eine Modem-IP darf nicht als Cookie-Domain beim Hotspot-Client landen.
            parts = [part for part in value.split(";") if not part.strip().lower().startswith("domain=")]
            value = ";".join(parts)
        headers.append((name, value))
    return Response(body, status=upstream.status, headers=headers)


@app.route("/", defaults={"path": ""}, methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
@app.route("/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def proxy(path: str) -> Response:
    data = request.get_data(cache=False) if request.method not in {"GET", "HEAD"} else None
    upstream_request = Request(
        _target_url(path),
        data=data,
        headers=_request_headers(),
        method=request.method,
    )
    try:
        upstream = OPENER.open(upstream_request, timeout=TIMEOUT)
        return _response(upstream)
    except HTTPError as exc:
        return _response(exc)
    except URLError as exc:
        return Response(
            f"LTE-Modem unter {TARGET} nicht erreichbar: {exc.reason}\n",
            status=502,
            content_type="text/plain; charset=utf-8",
        )
