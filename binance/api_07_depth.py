"""API 7: GET /api/v3/depth

Función: get_order_book_analysis(symbol, limit)
Analiza el libro de órdenes:
  - Spread absoluto y porcentual
  - Profundidad bid/ask en USDT
  - Imbalance comprador/vendedor
  - Detección de muros (>3x el tamaño promedio)
  - Score de liquidez (sección 17 de la guía)
"""
from __future__ import annotations

from ._client import spot_get


def _detect_walls(levels: list[tuple[float, float]], threshold_mult: float = 3.0):
    if not levels:
        return []
    qtys = [q for _, q in levels]
    avg = sum(qtys) / len(qtys)
    walls = [
        {"price": p, "qty": q, "notional": round(p * q, 2)}
        for p, q in levels
        if q >= avg * threshold_mult
    ]
    return sorted(walls, key=lambda x: x["notional"], reverse=True)[:3]


def get_order_book_analysis(symbol: str, limit: int = 100) -> dict:
    raw = spot_get("/api/v3/depth", {"symbol": symbol.upper(), "limit": limit})
    bids = [(float(p), float(q)) for p, q in raw.get("bids", [])]
    asks = [(float(p), float(q)) for p, q in raw.get("asks", [])]

    if not bids or not asks:
        return {
            "endpoint": "depth",
            "symbol": symbol.upper(),
            "error": "Order book vacío",
        }

    best_bid = bids[0][0]
    best_ask = asks[0][0]
    spread_abs = best_ask - best_bid
    spread_pct = spread_abs / best_bid * 100

    bid_notional = sum(p * q for p, q in bids)
    ask_notional = sum(p * q for p, q in asks)
    total = bid_notional + ask_notional
    buy_pressure_pct = bid_notional / total * 100 if total > 0 else 0

    if spread_pct < 0.05:
        liquidity_score = "ALTA"
    elif spread_pct < 0.2:
        liquidity_score = "MEDIA"
    else:
        liquidity_score = "BAJA"

    if buy_pressure_pct >= 60:
        imbalance = "COMPRADOR_DOMINA"
    elif buy_pressure_pct <= 40:
        imbalance = "VENDEDOR_DOMINA"
    else:
        imbalance = "EQUILIBRADO"

    return {
        "endpoint": "depth",
        "symbol": symbol.upper(),
        "lastUpdateId": raw.get("lastUpdateId"),
        "bestBid": best_bid,
        "bestAsk": best_ask,
        "spreadAbs": spread_abs,
        "spreadPct": round(spread_pct, 4),
        "bidNotionalTotal": round(bid_notional, 2),
        "askNotionalTotal": round(ask_notional, 2),
        "buyPressurePct": round(buy_pressure_pct, 2),
        "imbalance": imbalance,
        "liquidityScore": liquidity_score,
        "topBidWalls": _detect_walls(bids),
        "topAskWalls": _detect_walls(asks),
        "wideSpreadWarning": spread_pct >= 0.2,
        "levelsAnalyzed": {"bids": len(bids), "asks": len(asks)},
    }
