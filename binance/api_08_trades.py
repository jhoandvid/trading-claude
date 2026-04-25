"""API 8: GET /api/v3/trades

Función: get_recent_trades(symbol, limit)
Trades recientes para detectar agresividad. `isBuyerMaker=true` significa
que la ejecución la inició el vendedor (taker sell). Lo usamos para medir
presión de mercado en tiempo casi-real.
"""
from __future__ import annotations

from ._client import spot_get


def get_recent_trades(symbol: str, limit: int = 100) -> dict:
    raw = spot_get("/api/v3/trades", {"symbol": symbol.upper(), "limit": limit})
    if not raw:
        return {"endpoint": "trades", "symbol": symbol.upper(), "error": "Sin trades"}

    buy_qty = 0.0  # taker buy
    sell_qty = 0.0  # taker sell
    buy_quote = 0.0
    sell_quote = 0.0
    for t in raw:
        qty = float(t["qty"])
        quote = float(t["quoteQty"])
        # isBuyerMaker=True => el comprador estaba en el book => taker fue el vendedor
        if t.get("isBuyerMaker"):
            sell_qty += qty
            sell_quote += quote
        else:
            buy_qty += qty
            buy_quote += quote

    total_quote = buy_quote + sell_quote
    buyer_aggression_pct = (
        buy_quote / total_quote * 100 if total_quote > 0 else 0.0
    )

    if buyer_aggression_pct >= 60:
        flow = "AGRESIVO_COMPRADOR"
    elif buyer_aggression_pct <= 40:
        flow = "AGRESIVO_VENDEDOR"
    else:
        flow = "EQUILIBRADO"

    first_t = raw[0]["time"]
    last_t = raw[-1]["time"]
    duration_s = (last_t - first_t) / 1000 if last_t > first_t else None

    return {
        "endpoint": "trades",
        "symbol": symbol.upper(),
        "tradesAnalyzed": len(raw),
        "windowSeconds": duration_s,
        "takerBuyQty": round(buy_qty, 8),
        "takerSellQty": round(sell_qty, 8),
        "takerBuyQuote": round(buy_quote, 2),
        "takerSellQuote": round(sell_quote, 2),
        "buyerAggressionPct": round(buyer_aggression_pct, 2),
        "flow": flow,
        "lastPrice": float(raw[-1]["price"]),
    }
