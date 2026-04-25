"""API 1: GET /api/v3/exchangeInfo

Función: get_exchange_info(symbol)
Valida que el símbolo exista, esté en TRADING y devuelve precisión y filtros.
Es el primer paso obligatorio (sección 22, regla 9 de la guía de contratos).
"""
from __future__ import annotations

from ._client import spot_get


def get_exchange_info(symbol: str) -> dict:
    raw = spot_get("/api/v3/exchangeInfo", {"symbol": symbol.upper()})
    symbols = raw.get("symbols", [])
    if not symbols:
        return {
            "endpoint": "exchangeInfo",
            "symbol": symbol.upper(),
            "valid": False,
            "reason": "Símbolo no encontrado en Binance Spot",
        }

    info = symbols[0]
    filters = {f["filterType"]: f for f in info.get("filters", [])}
    price_filter = filters.get("PRICE_FILTER", {})
    lot_filter = filters.get("LOT_SIZE", {})
    notional = filters.get("NOTIONAL", filters.get("MIN_NOTIONAL", {}))

    return {
        "endpoint": "exchangeInfo",
        "symbol": info["symbol"],
        "valid": info.get("status") == "TRADING",
        "status": info.get("status"),
        "baseAsset": info.get("baseAsset"),
        "quoteAsset": info.get("quoteAsset"),
        "isSpotTradingAllowed": info.get("isSpotTradingAllowed"),
        "isMarginTradingAllowed": info.get("isMarginTradingAllowed"),
        "orderTypes": info.get("orderTypes", []),
        "supports_oco": "OCO" in info.get("orderTypes", [])
        or info.get("ocoAllowed", False),
        "tickSize": price_filter.get("tickSize"),
        "stepSize": lot_filter.get("stepSize"),
        "minQty": lot_filter.get("minQty"),
        "minNotional": notional.get("minNotional"),
        "serverTime": raw.get("serverTime"),
    }


if __name__ == "__main__":
    print(get_exchange_info("BTCUSDT"))