"""API 5: GET /api/v3/ticker?symbol=...&windowSize=...

Función: get_ticker_window(symbol, window_size)
Estadísticas para una ventana arbitraria (1h, 4h, 1d, 7d, etc.).
Útil para confirmar momentum reciente vs el cambio 24h.
"""
from __future__ import annotations

from ._client import spot_get


def get_ticker_window(symbol: str, window_size: str = "1h") -> dict:
    raw = spot_get(
        "/api/v3/ticker",
        {"symbol": symbol.upper(), "windowSize": window_size},
    )
    last = float(raw["lastPrice"])
    open_p = float(raw["openPrice"])
    change_pct = float(raw["priceChangePercent"])
    return {
        "endpoint": "ticker/window",
        "symbol": raw["symbol"],
        "windowSize": window_size,
        "openPrice": open_p,
        "lastPrice": last,
        "highPrice": float(raw["highPrice"]),
        "lowPrice": float(raw["lowPrice"]),
        "priceChangePercent": change_pct,
        "weightedAvgPrice": float(raw["weightedAvgPrice"]),
        "volume": float(raw["volume"]),
        "quoteVolume": float(raw["quoteVolume"]),
        "trades": int(raw.get("count", 0)),
        "isAccelerating": abs(change_pct) > 1.0,
    }
