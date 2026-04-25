"""API 13: GET /fapi/v1/fundingRate

Función: get_funding_rate(symbol, limit)
Histórico de funding rate. Calcula promedio y aplica la lectura de la
sección 20.2 de la guía:
  - Muy positivo (>0.05% / 8h) -> riesgo de long squeeze.
  - Muy negativo (<-0.05% / 8h) -> riesgo de short squeeze.
"""
from __future__ import annotations

from ._client import futures_get


def _bias_label(rate_pct: float) -> str:
    if rate_pct >= 0.05:
        return "MUY_POSITIVO_RIESGO_LONG_SQUEEZE"
    if rate_pct >= 0.02:
        return "POSITIVO"
    if rate_pct <= -0.05:
        return "MUY_NEGATIVO_RIESGO_SHORT_SQUEEZE"
    if rate_pct <= -0.02:
        return "NEGATIVO"
    return "NEUTRAL"


def get_funding_rate(symbol: str, limit: int = 100) -> dict:
    raw = futures_get(
        "/fapi/v1/fundingRate", {"symbol": symbol.upper(), "limit": limit}
    )
    if not raw:
        return {
            "endpoint": "fundingRate",
            "symbol": symbol.upper(),
            "error": "Sin histórico de funding",
        }

    rates = [float(r["fundingRate"]) for r in raw]
    latest = rates[-1] * 100
    avg = sum(rates) / len(rates) * 100
    last_8 = rates[-8:] if len(rates) >= 8 else rates
    avg_24h_pct = sum(last_8) / len(last_8) * 100

    return {
        "endpoint": "fundingRate",
        "symbol": symbol.upper(),
        "samples": len(rates),
        "latestFundingPct": round(latest, 5),
        "avgFundingHistoricalPct": round(avg, 5),
        "avgFunding24hPct": round(avg_24h_pct, 5),
        "biasLabel": _bias_label(latest),
        "annualizedPct": round(latest * 3 * 365, 2),  # 3 fundings por día
        "lastFundingTime": raw[-1].get("fundingTime"),
    }
