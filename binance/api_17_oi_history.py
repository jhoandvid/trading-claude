"""API 17: GET /futures/data/openInterestHist

Historia de Open Interest — detecta si el dinero institucional está
entrando o saliendo del mercado de futuros.

Lectura combinada precio + OI:
  - Precio ↑ + OI ↑ = tendencia fuerte, dinero nuevo entrando (BULLISH)
  - Precio ↑ + OI ↓ = short covering, subida débil, posible reversal
  - Precio ↓ + OI ↑ = shorts nuevos, tendencia bajista con convicción
  - Precio ↓ + OI ↓ = long liquidation, posible final de caída (CAPITULACIÓN)
"""
from __future__ import annotations

from ._client import futures_get


def _oi_trend(values: list[float]) -> str:
    if len(values) < 3:
        return "INSUFICIENTE"
    window = values[-6:] if len(values) >= 6 else values
    change = (window[-1] - window[0]) / window[0] * 100 if window[0] > 0 else 0
    if change > 3:
        return "CRECIENDO_FUERTE"
    if change > 1:
        return "CRECIENDO"
    if change < -3:
        return "CAYENDO_FUERTE"
    if change < -1:
        return "CAYENDO"
    return "ESTABLE"


def interpret_oi_price(oi_trend: str, price_change_pct: float | None) -> str:
    """Interpretación combinada OI + movimiento de precio."""
    if price_change_pct is None:
        return "SIN_DATOS_PRECIO"
    price_up = price_change_pct > 0.3
    price_down = price_change_pct < -0.3
    oi_up = oi_trend in ("CRECIENDO", "CRECIENDO_FUERTE")
    oi_down = oi_trend in ("CAYENDO", "CAYENDO_FUERTE")

    if price_up and oi_up:
        return "TENDENCIA_FUERTE_ALCISTA"
    if price_up and oi_down:
        return "SHORT_COVERING_SUBIDA_DEBIL"
    if price_down and oi_up:
        return "TENDENCIA_BAJISTA_CON_CONVICCION"
    if price_down and oi_down:
        return "CAPITULACION_LONG_POSIBLE_SUELO"
    return "NEUTRO"


def get_oi_history(
    symbol: str,
    period: str = "1h",
    limit: int = 24,
    price_change_pct: float | None = None,
) -> dict:
    """Historia de open interest con tendencia y cambio porcentual."""
    try:
        raw = futures_get(
            "/futures/data/openInterestHist",
            {"symbol": symbol.upper(), "period": period, "limit": limit},
        )
    except Exception as e:
        return {
            "endpoint": "openInterestHist",
            "symbol": symbol.upper(),
            "available": False,
            "error": str(e),
        }

    if not raw or not isinstance(raw, list):
        return {
            "endpoint": "openInterestHist",
            "symbol": symbol.upper(),
            "available": False,
            "error": "Sin datos",
        }

    oi_values = [float(r["sumOpenInterest"]) for r in raw]
    notional_values = [float(r["sumOpenInterestValue"]) for r in raw]
    latest_oi = oi_values[-1]
    oldest_oi = oi_values[0]
    change_pct = round((latest_oi - oldest_oi) / oldest_oi * 100, 3) if oldest_oi > 0 else 0

    short_change = None
    if len(oi_values) >= 2:
        short_change = round(
            (oi_values[-1] - oi_values[-2]) / oi_values[-2] * 100, 3
        )

    trend = _oi_trend(oi_values)
    interpretation = interpret_oi_price(trend, price_change_pct)

    return {
        "endpoint": "openInterestHist",
        "symbol": symbol.upper(),
        "available": True,
        "period": period,
        "samples": len(raw),
        "latestOI": round(latest_oi, 4),
        "latestNotionalUSDT": round(notional_values[-1], 2),
        "changePct": change_pct,
        "shortTermChangePct": short_change,
        "trend": trend,
        "interpretation": interpretation,
        "maxOI": round(max(oi_values), 4),
        "minOI": round(min(oi_values), 4),
    }
