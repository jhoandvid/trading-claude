"""API 2: GET /api/v3/ticker/price

Función: get_ticker_price(symbol)
Devuelve el último precio negociado. Base para todos los cálculos posteriores.
"""
from __future__ import annotations

from ._client import spot_get


def get_ticker_price(symbol: str) -> dict:
    raw = spot_get("/api/v3/ticker/price", {"symbol": symbol.upper()})
    return {
        "endpoint": "ticker/price",
        "symbol": raw["symbol"],
        "price": float(raw["price"]),
    }


if __name__ == "__main__":
    print(get_ticker_price("BTCUSDT"))