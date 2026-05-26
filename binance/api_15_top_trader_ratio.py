"""API 15: GET /futures/data/topLongShortAccountRatio
           GET /futures/data/topLongShortPositionRatio

Proxy más directo del posicionamiento institucional en Binance Futures.

Lectura:
  - ratio > 1.5  → longs dominan entre top traders (trade muy concurrido)
  - ratio < 0.7  → shorts dominan → posible short squeeze
  - ratio CRECIENDO mientras precio sube = confirma tendencia
  - ratio DECRECIENDO mientras precio sube = distribución (señal de alerta)
"""
from __future__ import annotations

from ._client import futures_get


def _classify_ratio(ratio: float) -> str:
    if ratio >= 2.5:
        return "LONGS_EXTREMO"
    if ratio >= 1.5:
        return "LONGS_DOMINA"
    if ratio >= 1.1:
        return "LEVE_LONG"
    if ratio <= 0.4:
        return "SHORTS_EXTREMO"
    if ratio <= 0.7:
        return "SHORTS_DOMINA"
    if ratio <= 0.9:
        return "LEVE_SHORT"
    return "EQUILIBRADO"


def _ratio_trend(ratios: list[float]) -> str:
    if len(ratios) < 3:
        return "INSUFICIENTE"
    recent = ratios[-6:] if len(ratios) >= 6 else ratios
    change = (recent[-1] - recent[0]) / recent[0] * 100 if recent[0] > 0 else 0
    if change > 5:
        return "CRECIENDO"
    if change < -5:
        return "DECRECIENDO"
    return "ESTABLE"


def _parse_series(raw: list) -> dict:
    if not raw:
        return {"available": False}
    latest = raw[-1]
    ratios = [float(r["longShortRatio"]) for r in raw]
    cur_ratio = float(latest["longShortRatio"])
    cur_long_pct = round(float(latest["longAccount"]) * 100, 2)
    cur_short_pct = round(float(latest["shortAccount"]) * 100, 2)
    return {
        "available": True,
        "ratio": round(cur_ratio, 4),
        "longPct": cur_long_pct,
        "shortPct": cur_short_pct,
        "label": _classify_ratio(cur_ratio),
        "trend": _ratio_trend(ratios),
        "samples": len(raw),
    }


def get_top_trader_ratio(symbol: str, period: str = "1h", limit: int = 30) -> dict:
    """Ratio long/short de TOP TRADERS por cuenta y por posición."""
    params = {"symbol": symbol.upper(), "period": period, "limit": limit}

    try:
        acct_raw = futures_get("/futures/data/topLongShortAccountRatio", params)
    except Exception:
        acct_raw = []

    try:
        pos_raw = futures_get("/futures/data/topLongShortPositionRatio", params)
    except Exception:
        pos_raw = []

    acct = _parse_series(acct_raw if isinstance(acct_raw, list) else [])
    pos = _parse_series(pos_raw if isinstance(pos_raw, list) else [])

    alert = None
    if acct.get("available"):
        ratio = acct["ratio"]
        if ratio >= 2.5:
            alert = "LONGS_MUY_CONCURRIDOS — trade saturado, riesgo de long squeeze si cae"
        elif ratio <= 0.4:
            alert = "SHORTS_MUY_CONCURRIDOS — riesgo de short squeeze si sube"

    # Divergencia: cuentas vs posiciones indica si los grandes concentran más
    divergence = None
    if acct.get("available") and pos.get("available"):
        diff = abs(acct["ratio"] - pos["ratio"])
        if diff > 0.5:
            divergence = (
                "POSICIONES_MAS_LARGAS" if pos["ratio"] > acct["ratio"]
                else "CUENTAS_MAS_LARGAS"
            )

    return {
        "endpoint": "topTraderRatio",
        "symbol": symbol.upper(),
        "period": period,
        "byAccount": acct,
        "byPosition": pos,
        "alert": alert,
        "divergence": divergence,
    }
