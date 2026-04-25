"""API 14: GET /fapi/v1/premiumIndex

Función: get_premium_index(symbol)
Mark price, index price y premium del perpetual sobre el spot.
La diferencia mark vs index es señal de sesgo apalancado.
"""
from __future__ import annotations

from ._client import futures_get


def get_premium_index(symbol: str) -> dict:
    raw = futures_get("/fapi/v1/premiumIndex", {"symbol": symbol.upper()})
    mark = float(raw["markPrice"])
    index = float(raw["indexPrice"])
    last_funding = float(raw.get("lastFundingRate", 0)) * 100
    premium_pct = (mark - index) / index * 100 if index > 0 else None

    if premium_pct is None:
        bias = "DESCONOCIDO"
    elif premium_pct >= 0.1:
        bias = "PERPETUAL_PREMIUM_LONGS_DOMINAN"
    elif premium_pct <= -0.1:
        bias = "PERPETUAL_DESCUENTO_SHORTS_DOMINAN"
    else:
        bias = "EN_LINEA_CON_SPOT"

    return {
        "endpoint": "premiumIndex",
        "symbol": raw["symbol"],
        "markPrice": mark,
        "indexPrice": index,
        "premiumPct": round(premium_pct, 4) if premium_pct is not None else None,
        "lastFundingRatePct": round(last_funding, 5),
        "nextFundingTime": raw.get("nextFundingTime"),
        "interestRatePct": round(float(raw.get("interestRate", 0)) * 100, 5),
        "bias": bias,
    }
