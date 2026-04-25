"""API 11: GET /fapi/v1/ticker/24hr

Función: get_futures_ticker_24h(symbol)
Stats 24h del mercado de futuros USD-M. Comparable con spot 24h para
detectar divergencias spot-perpetual (sección 14 del contrato).
"""
from __future__ import annotations

from ._client import futures_get


def get_futures_ticker_24h(symbol: str) -> dict:
    raw = futures_get("/fapi/v1/ticker/24hr", {"symbol": symbol.upper()})
    last = float(raw["lastPrice"])
    return {
        "endpoint": "futures/ticker/24hr",
        "symbol": raw["symbol"],
        "lastPrice": last,
        "priceChange": float(raw["priceChange"]),
        "priceChangePercent": float(raw["priceChangePercent"]),
        "weightedAvgPrice": float(raw["weightedAvgPrice"]),
        "highPrice": float(raw["highPrice"]),
        "lowPrice": float(raw["lowPrice"]),
        "volume": float(raw["volume"]),
        "quoteVolume": float(raw["quoteVolume"]),
        "trades24h": int(raw.get("count", 0)),
    }
