"""API 10: GET /api/v3/ticker/bookTicker

Función: get_book_ticker(symbol)
Mejor bid/ask sin profundidad. Devuelve mid-price y spread inmediato.
Es la fuente más rápida para spread; útil cuando depth es lento.
"""
from __future__ import annotations

from ._client import spot_get


def get_book_ticker(symbol: str) -> dict:
    raw = spot_get("/api/v3/ticker/bookTicker", {"symbol": symbol.upper()})
    bid = float(raw["bidPrice"])
    ask = float(raw["askPrice"])
    bid_qty = float(raw["bidQty"])
    ask_qty = float(raw["askQty"])
    spread = ask - bid
    mid = (ask + bid) / 2
    return {
        "endpoint": "bookTicker",
        "symbol": raw["symbol"],
        "bidPrice": bid,
        "bidQty": bid_qty,
        "askPrice": ask,
        "askQty": ask_qty,
        "midPrice": mid,
        "spreadAbs": spread,
        "spreadPct": round(spread / bid * 100, 4) if bid > 0 else None,
        "topLevelImbalancePct": round(
            bid_qty / (bid_qty + ask_qty) * 100, 2
        )
        if (bid_qty + ask_qty) > 0
        else None,
    }
