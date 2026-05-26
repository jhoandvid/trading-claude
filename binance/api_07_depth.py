"""API 7: GET /api/v3/depth

Función: get_order_book_analysis(symbol, limit)
Analiza el libro de órdenes:
  - Spread bid/ask
  - Profundidad bid/ask en USDT
  - Imbalance comprador/vendedor
  - Detección de muros por multiplicador relativo Y por notional absoluto
  - Score de liquidez (sección 17 de la guía)
  - Top 5 muros de compra y venta (posibles stops/targets institucionales)
"""
from __future__ import annotations

from ._client import spot_get


def _detect_walls(
    levels: list[tuple[float, float]],
    threshold_mult: float = 3.0,
    min_notional: float = 0,
) -> list[dict]:
    """Detecta muros por tamaño relativo Y por notional mínimo absoluto."""
    if not levels:
        return []
    qtys = [q for _, q in levels]
    avg = sum(qtys) / len(qtys) if qtys else 0
    walls = []
    for p, q in levels:
        notional = p * q
        is_wall = (avg > 0 and q >= avg * threshold_mult) or (
            min_notional > 0 and notional >= min_notional
        )
        if is_wall:
            walls.append({
                "price": p,
                "qty": q,
                "notional": round(notional, 2),
                "xAvg": round(q / avg, 1) if avg > 0 else None,
            })
    return sorted(walls, key=lambda x: x["notional"], reverse=True)[:5]


def _concentration_pct(levels: list[tuple[float, float]], top_n: int = 5) -> float:
    """% del total que concentran los top N niveles (detecta si hay muros dominantes)."""
    if not levels:
        return 0.0
    notionals = sorted([p * q for p, q in levels], reverse=True)
    total = sum(notionals)
    return round(sum(notionals[:top_n]) / total * 100, 1) if total > 0 else 0.0


def get_order_book_analysis(symbol: str, limit: int = 500) -> dict:
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

    # Umbral de muro: 100k USDT para detección absoluta
    min_wall_notional = 100_000

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
        "topBidWalls": _detect_walls(bids, min_notional=min_wall_notional),
        "topAskWalls": _detect_walls(asks, min_notional=min_wall_notional),
        "bidConcentrationPct": _concentration_pct(bids),
        "askConcentrationPct": _concentration_pct(asks),
        "wideSpreadWarning": spread_pct >= 0.2,
        "levelsAnalyzed": {"bids": len(bids), "asks": len(asks)},
    }
