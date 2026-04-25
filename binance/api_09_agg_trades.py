"""API 9: GET /api/v3/aggTrades

Función: get_agg_trades(symbol, limit)
Aggregate trades (mismo precio, mismo lado, mismo timestamp se agrupan).
Útil para detectar barridos grandes. Reportamos el trade más grande
encontrado en la ventana.
"""
from __future__ import annotations

from ._client import spot_get


def get_agg_trades(symbol: str, limit: int = 500) -> dict:
    raw = spot_get(
        "/api/v3/aggTrades", {"symbol": symbol.upper(), "limit": limit}
    )
    if not raw:
        return {
            "endpoint": "aggTrades",
            "symbol": symbol.upper(),
            "error": "Sin aggTrades",
        }

    buy_quote = 0.0
    sell_quote = 0.0
    largest = {"qty": 0.0, "price": 0.0, "side": None, "quote": 0.0}
    for t in raw:
        price = float(t["p"])
        qty = float(t["q"])
        quote = price * qty
        # m=True => buyer was maker => taker fue el vendedor
        if t.get("m"):
            sell_quote += quote
            side = "SELL"
        else:
            buy_quote += quote
            side = "BUY"
        if quote > largest["quote"]:
            largest = {"qty": qty, "price": price, "side": side, "quote": quote}

    total = buy_quote + sell_quote
    buy_pct = buy_quote / total * 100 if total > 0 else 0.0
    sweep = largest["quote"] / total * 100 if total > 0 else 0.0

    return {
        "endpoint": "aggTrades",
        "symbol": symbol.upper(),
        "aggTradesAnalyzed": len(raw),
        "buyQuote": round(buy_quote, 2),
        "sellQuote": round(sell_quote, 2),
        "buyAggressionPct": round(buy_pct, 2),
        "largestTrade": {
            "qty": largest["qty"],
            "price": largest["price"],
            "side": largest["side"],
            "quote": round(largest["quote"], 2),
            "shareOfWindowPct": round(sweep, 2),
        },
        "windowStart": raw[0].get("T"),
        "windowEnd": raw[-1].get("T"),
    }
