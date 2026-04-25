"""Indicadores y herramientas técnicas implementadas en Python puro.

Cubre lo que necesita la guía senior:
  - EMA / SMA
  - RSI (Wilder)
  - MACD (12/26/9)
  - ATR (Wilder)
  - Bollinger Bands (20, 2)
  - Detección de soportes / resistencias por pivots
  - Estructura de mercado (HH/HL/LH/LL)
  - Tendencia desde EMAs
  - Volumen relativo
"""
from __future__ import annotations

from statistics import mean, pstdev
from typing import Sequence


def sma(values: Sequence[float], period: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(values)):
        if i + 1 < period:
            out.append(None)
        else:
            window = values[i + 1 - period : i + 1]
            out.append(sum(window) / period)
    return out


def ema(values: Sequence[float], period: int) -> list[float | None]:
    if not values:
        return []
    k = 2 / (period + 1)
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    seed = sum(values[:period]) / period
    out[period - 1] = seed
    prev = seed
    for i in range(period, len(values)):
        cur = values[i] * k + prev * (1 - k)
        out[i] = cur
        prev = cur
    return out


def rsi(closes: Sequence[float], period: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    if len(closes) <= period:
        return out
    gains = 0.0
    losses = 0.0
    for i in range(1, period + 1):
        change = closes[i] - closes[i - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    rs = (avg_gain / avg_loss) if avg_loss != 0 else float("inf")
    out[period] = 100 - 100 / (1 + rs) if avg_loss != 0 else 100.0
    for i in range(period + 1, len(closes)):
        change = closes[i] - closes[i - 1]
        gain = max(change, 0.0)
        loss = max(-change, 0.0)
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - 100 / (1 + rs)
    return out


def macd(
    closes: Sequence[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> dict[str, list[float | None]]:
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line: list[float | None] = []
    for f, s in zip(ema_fast, ema_slow):
        macd_line.append(f - s if f is not None and s is not None else None)
    valid = [v for v in macd_line if v is not None]
    sig_full = ema(valid, signal)
    signal_line: list[float | None] = [None] * (len(macd_line) - len(valid)) + sig_full
    histogram: list[float | None] = []
    for m, s in zip(macd_line, signal_line):
        histogram.append(m - s if m is not None and s is not None else None)
    return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


def atr(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    period: int = 14,
) -> list[float | None]:
    n = len(closes)
    out: list[float | None] = [None] * n
    if n < period + 1:
        return out
    trs: list[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    seed = sum(trs[1 : period + 1]) / period
    out[period] = seed
    prev = seed
    for i in range(period + 1, n):
        cur = (prev * (period - 1) + trs[i]) / period
        out[i] = cur
        prev = cur
    return out


def bollinger(
    closes: Sequence[float], period: int = 20, std_mult: float = 2.0
) -> dict[str, list[float | None]]:
    upper: list[float | None] = []
    middle = sma(closes, period)
    lower: list[float | None] = []
    for i in range(len(closes)):
        if i + 1 < period:
            upper.append(None)
            lower.append(None)
            continue
        window = closes[i + 1 - period : i + 1]
        m = mean(window)
        sd = pstdev(window)
        upper.append(m + std_mult * sd)
        lower.append(m - std_mult * sd)
    return {"upper": upper, "middle": middle, "lower": lower}


def find_pivots(
    highs: Sequence[float], lows: Sequence[float], left: int = 3, right: int = 3
) -> tuple[list[int], list[int]]:
    """Devuelve índices de pivot highs y pivot lows."""
    pivot_highs: list[int] = []
    pivot_lows: list[int] = []
    n = len(highs)
    for i in range(left, n - right):
        h_window = highs[i - left : i + right + 1]
        l_window = lows[i - left : i + right + 1]
        if highs[i] == max(h_window):
            pivot_highs.append(i)
        if lows[i] == min(l_window):
            pivot_lows.append(i)
    return pivot_highs, pivot_lows


def support_resistance_levels(
    highs: Sequence[float],
    lows: Sequence[float],
    closes: Sequence[float],
    left: int = 3,
    right: int = 3,
    cluster_pct: float = 0.5,
    max_levels: int = 5,
) -> dict[str, list[float]]:
    """Detecta soportes y resistencias por pivots y los agrupa por cercanía."""
    if not closes:
        return {"supports": [], "resistances": []}
    pivot_highs, pivot_lows = find_pivots(highs, lows, left, right)
    last_close = closes[-1]
    raw_resistances = sorted({highs[i] for i in pivot_highs if highs[i] > last_close})
    raw_supports = sorted(
        {lows[i] for i in pivot_lows if lows[i] < last_close}, reverse=True
    )

    def cluster(levels: list[float]) -> list[float]:
        clustered: list[float] = []
        for lvl in levels:
            if not clustered:
                clustered.append(lvl)
                continue
            if abs(lvl - clustered[-1]) / clustered[-1] * 100 <= cluster_pct:
                clustered[-1] = (clustered[-1] + lvl) / 2
            else:
                clustered.append(lvl)
        return clustered

    return {
        "supports": cluster(raw_supports)[:max_levels],
        "resistances": cluster(raw_resistances)[:max_levels],
    }


def market_structure(
    highs: Sequence[float], lows: Sequence[float], left: int = 3, right: int = 3
) -> dict[str, str | int | None]:
    """Clasifica la estructura como ALCISTA, BAJISTA, LATERAL o INDEFINIDA.

    Reglas (sección 4 de la guía):
      - Alcista: últimos pivot highs y pivot lows ascendentes (HH + HL).
      - Bajista: últimos pivot highs y pivot lows descendentes (LH + LL).
      - Lateral: combinación mixta o pivots planos.
    """
    pivot_highs, pivot_lows = find_pivots(highs, lows, left, right)
    if len(pivot_highs) < 2 or len(pivot_lows) < 2:
        return {"structure": "INDEFINIDA", "pivot_highs": len(pivot_highs), "pivot_lows": len(pivot_lows)}
    h_last, h_prev = highs[pivot_highs[-1]], highs[pivot_highs[-2]]
    l_last, l_prev = lows[pivot_lows[-1]], lows[pivot_lows[-2]]
    higher_high = h_last > h_prev
    higher_low = l_last > l_prev
    lower_high = h_last < h_prev
    lower_low = l_last < l_prev
    if higher_high and higher_low:
        structure = "ALCISTA"
    elif lower_high and lower_low:
        structure = "BAJISTA"
    else:
        structure = "LATERAL"
    return {
        "structure": structure,
        "last_pivot_high": h_last,
        "prev_pivot_high": h_prev,
        "last_pivot_low": l_last,
        "prev_pivot_low": l_prev,
    }


def trend_from_emas(
    close: float,
    ema20: float | None,
    ema50: float | None,
    ema200: float | None,
) -> str:
    """Clasifica la tendencia comparando precio vs EMAs."""
    if None in (ema20, ema50, ema200):
        return "DATOS_INSUFICIENTES"
    if close > ema20 > ema50 > ema200:
        return "ALCISTA_FUERTE"
    if close > ema50 > ema200:
        return "ALCISTA"
    if close < ema20 < ema50 < ema200:
        return "BAJISTA_FUERTE"
    if close < ema50 < ema200:
        return "BAJISTA"
    return "LATERAL"


def relative_volume(volumes: Sequence[float], period: int = 20) -> float | None:
    """Volumen actual vs promedio. >1 = mayor participación."""
    if len(volumes) < period + 1:
        return None
    avg = sum(volumes[-period - 1 : -1]) / period
    if avg == 0:
        return None
    return volumes[-1] / avg


def position_in_range(price: float, low: float, high: float) -> float | None:
    """Devuelve % del rango high-low donde está el precio (0=low, 100=high)."""
    if high == low:
        return None
    return (price - low) / (high - low) * 100


def candle_metrics(candle: dict, prev_candle: dict | None = None) -> dict:
    """Métricas accionables de una vela individual.

    No clasifica patrones formales (HAMMER, ENGULFING) porque son
    subjetivos. En su lugar mide:
      - Dónde cerró dentro de su rango (0% = mínimo, 100% = máximo)
      - Tamaño relativo del cuerpo y de las mechas
      - Si cerró arriba del máximo de la vela previa (señal de fuerza)
    """
    o, h, l, c = candle["open"], candle["high"], candle["low"], candle["close"]
    rng = h - l
    if rng == 0:
        return {"closePositionInRangePct": None}
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    return {
        "closePositionInRangePct": round((c - l) / rng * 100, 2),
        "bodyPctOfRange": round(body / rng * 100, 2),
        "upperWickPct": round(upper_wick / rng * 100, 2),
        "lowerWickPct": round(lower_wick / rng * 100, 2),
        "isBullish": c > o,
        "closedAbovePrevHigh": (
            prev_candle is not None and c > prev_candle["high"]
        ),
        "closedBelowPrevLow": (
            prev_candle is not None and c < prev_candle["low"]
        ),
    }


def micro_structure(
    highs: Sequence[float],
    lows: Sequence[float],
    lookback: int = 20,
    left: int = 2,
    right: int = 2,
) -> dict:
    """Estructura de las últimas `lookback` velas (microtendencia)."""
    if len(highs) < lookback:
        return {"structure": "INSUFICIENTE", "lookback": lookback}
    recent_highs = highs[-lookback:]
    recent_lows = lows[-lookback:]
    pivot_h, pivot_l = find_pivots(recent_highs, recent_lows, left, right)
    if len(pivot_h) < 2 or len(pivot_l) < 2:
        return {"structure": "INDEFINIDA", "lookback": lookback, "swingHighs": len(pivot_h), "swingLows": len(pivot_l)}
    h_last, h_prev = recent_highs[pivot_h[-1]], recent_highs[pivot_h[-2]]
    l_last, l_prev = recent_lows[pivot_l[-1]], recent_lows[pivot_l[-2]]
    higher_high = h_last > h_prev
    higher_low = l_last > l_prev
    if higher_high and higher_low:
        label = "BULLISH"
    elif not higher_high and not higher_low:
        label = "BEARISH"
    else:
        label = "MIXED"
    return {
        "structure": label,
        "lookback": lookback,
        "lastSwingHighs": "HIGHER_HIGHS" if higher_high else "LOWER_HIGHS",
        "lastSwingLows": "HIGHER_LOWS" if higher_low else "LOWER_LOWS",
    }


def level_strength(
    level: float,
    candles: list[dict],
    atr_value: float | None,
    tolerance_atr: float = 0.5,
) -> dict:
    """Mide cuántas veces el precio reaccionó cerca de un nivel y cuán reciente
    fue la última reacción.

    Solo cuenta como **touch** un rechazo real:
      - Para soporte: low entra a la zona [level - tol, level + tol]
        Y close termina al menos `0.25 * ATR` arriba del nivel.
      - Para resistencia: high entra a la zona Y close al menos
        `0.25 * ATR` abajo del nivel.
    Esto evita inflar el conteo en períodos de consolidación lateral.
    """
    if not candles or atr_value is None or atr_value <= 0:
        return {"touches": 0, "lastTouchedHoursAgo": None, "strengthScore": 0}
    tol = tolerance_atr * atr_value
    rejection_dist = 0.25 * atr_value
    touches = 0
    last_touch_ms = None
    last_close = candles[-1]["close"]
    is_support = level < last_close
    for c in candles:
        if is_support:
            touched = (level - tol) <= c["low"] <= (level + tol)
            rejected = c["close"] >= level + rejection_dist
        else:
            touched = (level - tol) <= c["high"] <= (level + tol)
            rejected = c["close"] <= level - rejection_dist
        if touched and rejected:
            touches += 1
            last_touch_ms = c["closeTime"]
    last_hours = None
    if last_touch_ms:
        now_ms = candles[-1]["closeTime"]
        last_hours = round((now_ms - last_touch_ms) / 3_600_000, 1)
    base = min(touches * 18, 90)
    recency_bonus = 10 if last_hours is not None and last_hours < 24 else 0
    return {
        "touches": touches,
        "lastTouchedHoursAgo": last_hours,
        "strengthScore": min(base + recency_bonus, 100),
    }
