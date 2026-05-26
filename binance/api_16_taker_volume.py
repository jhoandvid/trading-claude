"""API 16: CVD de futuros calculado desde /fapi/v1/klines

Las klines de futuros incluyen takerBuyBaseAssetVolume (campo 9), igual que
las klines de spot. Calculamos CVD real del mercado de derivados.

Lectura:
  - cvdFuturesBuyPct > 52%  → compradores agresivos dominan en futuros
  - cvdFuturesBuyPct < 48%  → vendedores agresivos dominan en futuros
  - Divergencia spot vs futuros → señal de distribución o acumulación oculta
"""
from __future__ import annotations

from ._client import futures_get


def _cvd_label(buy_pct: float) -> str:
    if buy_pct >= 57:
        return "COMPRADOR_FUERTE"
    if buy_pct >= 52:
        return "COMPRADOR_LEVE"
    if buy_pct <= 43:
        return "VENDEDOR_FUERTE"
    if buy_pct <= 48:
        return "VENDEDOR_LEVE"
    return "EQUILIBRADO"


def _cvd_trend(buy_pcts: list[float]) -> str:
    """Tendencia del CVD en los últimos períodos."""
    if len(buy_pcts) < 3:
        return "INSUFICIENTE"
    window = buy_pcts[-6:] if len(buy_pcts) >= 6 else buy_pcts
    buyers_dom = sum(1 for p in window if p >= 52)
    sellers_dom = sum(1 for p in window if p <= 48)
    if buyers_dom >= 5:
        return "COMPRADOR_SOSTENIDO"
    if sellers_dom >= 5:
        return "VENDEDOR_SOSTENIDO"
    if buy_pcts[-1] > buy_pcts[-3] + 2:
        return "AUMENTANDO_COMPRAS"
    if buy_pcts[-1] < buy_pcts[-3] - 2:
        return "AUMENTANDO_VENTAS"
    return "MIXTO"


def get_taker_volume(
    symbol: str, interval: str = "1h", limit: int = 24
) -> dict:
    """CVD de futuros calculado desde klines de /fapi/v1/klines."""
    try:
        raw = futures_get(
            "/fapi/v1/klines",
            {"symbol": symbol.upper(), "interval": interval, "limit": limit},
        )
    except Exception as e:
        return {
            "endpoint": "takerVolume",
            "symbol": symbol.upper(),
            "available": False,
            "error": str(e),
        }

    if not raw or not isinstance(raw, list):
        return {
            "endpoint": "takerVolume",
            "symbol": symbol.upper(),
            "available": False,
            "error": "Sin datos",
        }

    taker_buy = [float(k[9]) for k in raw]
    total_vol = [float(k[5]) for k in raw]
    taker_sell = [tv - tb for tv, tb in zip(total_vol, taker_buy)]

    total_buy_all = sum(taker_buy)
    total_sell_all = sum(taker_sell)
    total_all = total_buy_all + total_sell_all
    buy_pct_all = round(total_buy_all / total_all * 100, 2) if total_all > 0 else 50.0

    # CVD por vela para detectar tendencia
    buy_pcts_per_candle = []
    for tb, ts in zip(taker_buy, taker_sell):
        t = tb + ts
        buy_pcts_per_candle.append(round(tb / t * 100, 2) if t > 0 else 50.0)

    # Comparar última mitad vs primera mitad (aceleración/desaceleración)
    mid = len(buy_pcts_per_candle) // 2
    recent_avg = sum(buy_pcts_per_candle[mid:]) / len(buy_pcts_per_candle[mid:]) if mid < len(buy_pcts_per_candle) else buy_pct_all
    older_avg = sum(buy_pcts_per_candle[:mid]) / len(buy_pcts_per_candle[:mid]) if mid > 0 else buy_pct_all

    return {
        "endpoint": "takerVolume",
        "symbol": symbol.upper(),
        "available": True,
        "source": "futures_klines",
        "interval": interval,
        "samples": len(raw),
        "cvdBuyPct": buy_pct_all,
        "cvdSellPct": round(100 - buy_pct_all, 2),
        "cvdLabel": _cvd_label(buy_pct_all),
        "cvdTrend": _cvd_trend(buy_pcts_per_candle),
        "cvdBias": "COMPRADOR" if buy_pct_all >= 50 else "VENDEDOR",
        "recentBuyPct": round(recent_avg, 2),
        "olderBuyPct": round(older_avg, 2),
        "acceleration": "CRECIENDO" if recent_avg > older_avg + 1 else "DECRECIENDO" if recent_avg < older_avg - 1 else "ESTABLE",
    }
