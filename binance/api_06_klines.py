"""API 6: GET /api/v3/klines

Función: get_klines_analysis(symbol, interval, limit)
Es el endpoint más importante para análisis técnico (sección 8 del contrato).
Calcula y devuelve:
  - Últimas N velas normalizadas
  - EMA 20 / 50 / 200
  - RSI 14
  - MACD (12, 26, 9)
  - ATR 14
  - Bollinger Bands (20, 2)
  - Soportes y resistencias por pivots
  - Estructura de mercado (HH/HL/LH/LL)
  - Tendencia desde EMAs
  - Volumen relativo
  - Stop sugerido por ATR
"""
from __future__ import annotations

from ._client import spot_get
from ._indicators import (
    atr,
    bollinger,
    ema,
    macd,
    market_structure,
    relative_volume,
    rsi,
    support_resistance_levels,
    trend_from_emas,
)


def _parse_klines(raw: list) -> list[dict]:
    out = []
    for k in raw:
        out.append(
            {
                "openTime": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "closeTime": k[6],
                "quoteVolume": float(k[7]),
                "trades": int(k[8]),
                "takerBuyBaseVolume": float(k[9]),
                "takerBuyQuoteVolume": float(k[10]),
            }
        )
    return out


def _last_valid(series: list) -> float | None:
    for v in reversed(series):
        if v is not None:
            return v
    return None


def _rsi_label(value: float | None) -> str:
    if value is None:
        return "N/A"
    if value >= 70:
        return "SOBRECOMPRA"
    if value >= 60:
        return "FUERTE"
    if value <= 30:
        return "SOBREVENTA"
    if value <= 40:
        return "DEBIL"
    return "NEUTRAL"


def _macd_label(macd_v: float | None, sig_v: float | None, hist: float | None) -> str:
    if macd_v is None or sig_v is None or hist is None:
        return "N/A"
    if macd_v > sig_v and hist > 0:
        return "CRUCE_ALCISTA"
    if macd_v < sig_v and hist < 0:
        return "CRUCE_BAJISTA"
    return "TRANSICION"


def get_klines_analysis(
    symbol: str, interval: str = "1h", limit: int = 500
) -> dict:
    raw = spot_get(
        "/api/v3/klines",
        {"symbol": symbol.upper(), "interval": interval, "limit": limit},
    )
    candles = _parse_klines(raw)
    if not candles:
        return {
            "endpoint": "klines",
            "symbol": symbol.upper(),
            "interval": interval,
            "error": "Sin velas",
        }

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    volumes = [c["volume"] for c in candles]

    ema20_series = ema(closes, 20)
    ema50_series = ema(closes, 50)
    ema200_series = ema(closes, 200)
    rsi_series = rsi(closes, 14)
    macd_data = macd(closes)
    atr_series = atr(highs, lows, closes, 14)
    bb_data = bollinger(closes, 20, 2.0)
    sr = support_resistance_levels(highs, lows, closes)
    structure = market_structure(highs, lows)

    last_close = closes[-1]
    last_ema20 = _last_valid(ema20_series)
    last_ema50 = _last_valid(ema50_series)
    last_ema200 = _last_valid(ema200_series)
    last_rsi = _last_valid(rsi_series)
    last_macd = _last_valid(macd_data["macd"])
    last_signal = _last_valid(macd_data["signal"])
    last_hist = _last_valid(macd_data["histogram"])
    last_atr = _last_valid(atr_series)
    last_bb_upper = _last_valid(bb_data["upper"])
    last_bb_middle = _last_valid(bb_data["middle"])
    last_bb_lower = _last_valid(bb_data["lower"])
    rel_vol = relative_volume(volumes, 20)

    trend = trend_from_emas(last_close, last_ema20, last_ema50, last_ema200)
    rsi_lbl = _rsi_label(last_rsi)
    macd_lbl = _macd_label(last_macd, last_signal, last_hist)

    suggested_stop = None
    if last_atr is not None:
        suggested_stop = round(last_close - 1.5 * last_atr, 8)

    return {
        "endpoint": "klines",
        "symbol": symbol.upper(),
        "interval": interval,
        "candleCount": len(candles),
        "lastCandle": candles[-1],
        "lastCandles": candles[-5:],
        "allCandles": candles,
        "indicators": {
            "ema20": last_ema20,
            "ema50": last_ema50,
            "ema200": last_ema200,
            "rsi14": last_rsi,
            "rsiLabel": rsi_lbl,
            "macd": last_macd,
            "macdSignal": last_signal,
            "macdHistogram": last_hist,
            "macdLabel": macd_lbl,
            "atr14": last_atr,
            "bbUpper": last_bb_upper,
            "bbMiddle": last_bb_middle,
            "bbLower": last_bb_lower,
            "relativeVolume": rel_vol,
        },
        "trend": trend,
        "structure": structure,
        "supports": sr["supports"],
        "resistances": sr["resistances"],
        "suggestedStopByAtr": suggested_stop,
        "priceVsEma50Pct": (
            round((last_close - last_ema50) / last_ema50 * 100, 2)
            if last_ema50
            else None
        ),
        "priceVsEma200Pct": (
            round((last_close - last_ema200) / last_ema200 * 100, 2)
            if last_ema200
            else None
        ),
    }
