"""API 3: GET /api/v3/avgPrice

Función: get_avg_price(symbol)
Precio promedio ponderado de los últimos 5 minutos. Compara contra el precio
actual para detectar si el spot reciente está estirado o dentro del promedio.
"""
from __future__ import annotations

from ._client import spot_get


def get_avg_price(symbol: str, current_price: float | None = None) -> dict:
    raw = spot_get("/api/v3/avgPrice", {"symbol": symbol.upper()})
    avg = float(raw["price"])
    out = {
        "endpoint": "avgPrice",
        "symbol": symbol.upper(),
        "avgPrice": avg,
        "windowMins": raw.get("mins"),
        "closeTime": raw.get("closeTime"),
    }
    if current_price is not None and avg > 0:
        deviation_pct = (current_price - avg) / avg * 100
        out["deviationPct"] = round(deviation_pct, 4)
        if abs(deviation_pct) < 0.1:
            label = "EN_PROMEDIO"
        elif deviation_pct > 0.5:
            label = "POR_ENCIMA"
        elif deviation_pct < -0.5:
            label = "POR_DEBAJO"
        else:
            label = "CERCANO"
        out["deviationLabel"] = label
    return out
