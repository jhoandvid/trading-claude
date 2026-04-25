"""Cliente HTTP minimalista para las APIs públicas de Binance.

Usa solo la librería estándar (urllib) para evitar dependencias externas.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

SPOT_BASE = "https://data-api.binance.vision"
FUTURES_BASE = "https://fapi.binance.com"
DEFAULT_TIMEOUT = 15


class BinanceAPIError(RuntimeError):
    def __init__(self, status: int, url: str, body: str) -> None:
        super().__init__(f"HTTP {status} al consultar {url}: {body[:300]}")
        self.status = status
        self.url = url
        self.body = body


def _build_url(base: str, path: str, params: dict[str, Any] | None) -> str:
    url = f"{base}{path}"
    if params:
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            url = f"{url}?{urllib.parse.urlencode(clean)}"
    return url


def get_json(base: str, path: str, params: dict[str, Any] | None = None) -> Any:
    url = _build_url(base, path, params)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "trading-analyzer/1.0", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=DEFAULT_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise BinanceAPIError(e.code, url, body) from e


def spot_get(path: str, params: dict[str, Any] | None = None) -> Any:
    return get_json(SPOT_BASE, path, params)


def futures_get(path: str, params: dict[str, Any] | None = None) -> Any:
    return get_json(FUTURES_BASE, path, params)
