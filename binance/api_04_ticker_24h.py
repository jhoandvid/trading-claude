"""API 4: GET /api/v3/ticker/24hr

Función: get_ticker_24h(symbol)
Estadísticas 24h. Calcula también:
  - Posición del precio dentro del rango high-low (regla de "no comprar en resistencia")
  - Etiqueta de momentum según cambio porcentual
"""
from __future__ import annotations

from ._client import spot_get
from ._indicators import position_in_range


def _momentum_label(change_pct: float) -> str:
    if change_pct >= 8:
        return "EXTREMO_ALCISTA"
    if change_pct >= 3:
        return "FUERTE_ALCISTA"
    if change_pct >= 1:
        return "ALCISTA"
    if change_pct <= -8:
        return "EXTREMO_BAJISTA"
    if change_pct <= -3:
        return "FUERTE_BAJISTA"
    if change_pct <= -1:
        return "BAJISTA"
    return "NEUTRAL"


def get_ticker_24h(symbol: str) -> dict:
    raw = spot_get("/api/v3/ticker/24hr", {"symbol": symbol.upper()})
    last = float(raw["lastPrice"])
    high = float(raw["highPrice"])
    low = float(raw["lowPrice"])
    change_pct = float(raw["priceChangePercent"])
    pos_range = position_in_range(last, low, high)
    return {
        "endpoint": "ticker/24hr",
        "symbol": raw["symbol"],
        "lastPrice": last,
        "openPrice": float(raw["openPrice"]),
        "highPrice": high,
        "lowPrice": low,
        "priceChange": float(raw["priceChange"]),
        "priceChangePercent": change_pct,
        "weightedAvgPrice": float(raw["weightedAvgPrice"]),
        "volume": float(raw["volume"]),
        "quoteVolume": float(raw["quoteVolume"]),
        "trades24h": int(raw.get("count", 0)),
        "positionInRangePct": round(pos_range, 2) if pos_range is not None else None,
        "momentumLabel": _momentum_label(change_pct),
        "rangePct": round((high - low) / low * 100, 2) if low > 0 else None,
        "nearHighWarning": pos_range is not None and pos_range >= 80,
        "nearLowOpportunity": pos_range is not None and pos_range <= 20,
    }
