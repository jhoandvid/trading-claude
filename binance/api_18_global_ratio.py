"""API 18: GET /futures/data/globalLongShortAccountRatio

Ratio long/short de TODOS los traders (no solo top traders).

La masa retail suele estar en el lado equivocado en extremos:
  - Ratio muy alto (>2.0) → mayoría muy long → señal CONTRARIA bajista
  - Ratio muy bajo (<0.5) → mayoría muy short → señal CONTRARIA alcista

Combinado con top trader ratio:
  - Retail muy long + Top traders cortos = señal bajista fuerte
  - Retail muy short + Top traders largos = señal alcista fuerte (squeeze)
"""
from __future__ import annotations

from ._client import futures_get


def _contrarian_signal(ratio: float) -> str | None:
    if ratio >= 2.5:
        return "SEÑAL_CONTRARIA_BAJISTA_FUERTE — retail extremadamente long"
    if ratio >= 2.0:
        return "SEÑAL_CONTRARIA_BAJISTA — retail muy long"
    if ratio <= 0.4:
        return "SEÑAL_CONTRARIA_ALCISTA_FUERTE — retail extremadamente short"
    if ratio <= 0.5:
        return "SEÑAL_CONTRARIA_ALCISTA — retail muy short"
    return None


def _vs_top_traders(global_ratio: float, top_ratio: float | None) -> str | None:
    """Detecta divergencia entre lo que hace el retail y los top traders."""
    if top_ratio is None:
        return None
    if global_ratio > 1.5 and top_ratio < 0.9:
        return "DIVERGENCIA_BAJISTA — retail long, top traders cortos"
    if global_ratio < 0.7 and top_ratio > 1.3:
        return "DIVERGENCIA_ALCISTA — retail short, top traders largos (posible squeeze)"
    return None


def get_global_ratio(
    symbol: str,
    period: str = "1h",
    limit: int = 24,
    top_trader_ratio: float | None = None,
) -> dict:
    """Ratio long/short de todos los traders con señal contraria."""
    try:
        raw = futures_get(
            "/futures/data/globalLongShortAccountRatio",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
    except Exception as e:
        return {
            "endpoint": "globalLongShortRatio",
            "symbol": symbol.upper(),
            "available": False,
            "error": str(e),
        }

    if not raw or not isinstance(raw, list):
        return {
            "endpoint": "globalLongShortRatio",
            "symbol": symbol.upper(),
            "available": False,
            "error": "Sin datos",
        }

    latest = raw[-1]
    ratio = float(latest["longShortRatio"])
    long_pct = round(float(latest["longAccount"]) * 100, 2)
    short_pct = round(float(latest["shortAccount"]) * 100, 2)

    ratios = [float(r["longShortRatio"]) for r in raw]
    avg_ratio = round(sum(ratios) / len(ratios), 4)

    vs_top = _vs_top_traders(ratio, top_trader_ratio)

    return {
        "endpoint": "globalLongShortRatio",
        "symbol": symbol.upper(),
        "available": True,
        "period": period,
        "samples": len(raw),
        "ratio": round(ratio, 4),
        "longPct": long_pct,
        "shortPct": short_pct,
        "avgRatio": avg_ratio,
        "contrarianSignal": _contrarian_signal(ratio),
        "vsTopTraders": vs_top,
        "vsAvg": (
            "POR_ENCIMA" if ratio > avg_ratio * 1.1
            else "POR_DEBAJO" if ratio < avg_ratio * 0.9
            else "NORMAL"
        ),
    }
