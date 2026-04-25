"""API 12: GET /fapi/v1/openInterest

Función: get_open_interest(symbol, current_price)
Open Interest del par en futuros. Si se pasa el precio actual,
calcula el valor nocional total.

Lectura útil (sección 20.1 / 20.2 de la guía):
  - OI alto + funding muy positivo = riesgo de long squeeze.
  - OI alto + funding muy negativo = riesgo de short squeeze.
  - OI subiendo con precio subiendo = posiciones long agresivas.
"""
from __future__ import annotations

from ._client import futures_get


def get_open_interest(symbol: str, current_price: float | None = None) -> dict:
    raw = futures_get("/fapi/v1/openInterest", {"symbol": symbol.upper()})
    oi = float(raw["openInterest"])
    out = {
        "endpoint": "openInterest",
        "symbol": raw["symbol"],
        "openInterest": oi,
        "time": raw.get("time"),
    }
    if current_price:
        out["openInterestNotional"] = round(oi * current_price, 2)
    return out
