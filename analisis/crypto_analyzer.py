"""Orquestador principal de análisis (v3).

Diferencia clave respecto a v2:
  * **`setupScore`** (¿hay oportunidad técnica?) y **`executionScore`**
    (¿se puede entrar AHORA?) se calculan por separado.
  * Sección formal de **`blockingRules`** con severity y razón.
  * **`candleStatus`** indica si la vela del timeframe operado está
    cerrada o no (penaliza señales sobre velas abiertas).
  * **`candleConfirmation`** mide rechazo, mecha inferior, cierre
    relativo y cierre arriba del máximo previo.
  * **`higherTimeframes`** lee tendencia 4h y 1d para evitar entrar
    contra una resistencia mayor.
  * **`marketRegime`** clasifica el entorno en LOW_VOL_RANGE /
    TRENDING_UP / TRENDING_DOWN / VOL_EXPANSION / CHOP_EXTREME.
  * **`costAdjustedRR`** descuenta comisiones round-trip y slippage.
  * **`tradePlan`** entrega escenarios A/B condicionales en lugar de
    una sola entrada.
  * **`supports` / `resistances`** ahora incluyen `strengthScore`.

Uso:
    python -m analisis.crypto_analyzer BTC --interval 1h --pretty
    python -m analisis.crypto_analyzer SOL --quote USDT --interval 4h --out sol.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from binance._client import BinanceAPIError  # noqa: E402
from binance._indicators import (  # noqa: E402
    candle_metrics,
    level_strength,
    micro_structure,
)
from binance.api_01_exchange_info import get_exchange_info  # noqa: E402
from binance.api_02_ticker_price import get_ticker_price  # noqa: E402
from binance.api_03_avg_price import get_avg_price  # noqa: E402
from binance.api_04_ticker_24h import get_ticker_24h  # noqa: E402
from binance.api_05_ticker_window import get_ticker_window  # noqa: E402
from binance.api_06_klines import get_klines_analysis  # noqa: E402
from binance.api_07_depth import get_order_book_analysis  # noqa: E402
from binance.api_08_trades import get_recent_trades  # noqa: E402
from binance.api_09_agg_trades import get_agg_trades  # noqa: E402
from binance.api_10_book_ticker import get_book_ticker  # noqa: E402
from binance.api_11_futures_24h import get_futures_ticker_24h  # noqa: E402
from binance.api_12_open_interest import get_open_interest  # noqa: E402
from binance.api_13_funding_rate import get_funding_rate  # noqa: E402
from binance.api_14_premium_index import get_premium_index  # noqa: E402

DEFAULT_FEE_PCT_ROUND_TRIP = 0.2  # 0.1% maker/taker x 2 lados
DEFAULT_SLIPPAGE_PCT = 0.03

# Aproximación de minutos por intervalo (para candleStatus).
_INTERVAL_MINUTES = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except BinanceAPIError as e:
        return {"error": True, "status": e.status, "message": str(e)}
    except Exception as e:  # noqa: BLE001
        return {"error": True, "message": f"{type(e).__name__}: {e}"}


# Cache simple con TTL para exchangeInfo: el símbolo no cambia entre
# llamadas seguidas (p.ej. cuando analizas varios tokens en lote).
_INFO_CACHE: dict[str, tuple[float, dict]] = {}
_INFO_TTL_SECONDS = 300.0  # 5 min


def _cached_exchange_info(symbol: str) -> dict:
    now = time.time()
    cached = _INFO_CACHE.get(symbol)
    if cached and now - cached[0] < _INFO_TTL_SECONDS:
        return cached[1]
    data = _safe(get_exchange_info, symbol)
    if _is_ok(data):
        _INFO_CACHE[symbol] = (now, data)
    return data


def _run_parallel(tasks: dict[str, tuple], max_workers: int = 12) -> dict:
    """Ejecuta `_safe(fn, *args)` para cada (name -> (fn, args)) en paralelo.

    Las llamadas HTTP son I/O bound, así que threading sirve perfectamente
    sin tener que migrar a async.
    """
    results: dict[str, object] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            name: ex.submit(_safe, fn, *args) for name, (fn, args) in tasks.items()
        }
        for name, fut in futures.items():
            results[name] = fut.result()
    return results


def _is_ok(payload) -> bool:
    return isinstance(payload, dict) and not payload.get("error")


def _pct_distance(a: float, b: float) -> float:
    if not a:
        return float("inf")
    return abs(a - b) / a * 100


def _downgrade(action: str) -> str:
    chain = {
        "STRONG_BUY": "BUY_PARTIAL",
        "BUY_PARTIAL": "WAIT",
        "WAIT": "AVOID",
        "AVOID": "AVOID",
    }
    return chain[action]


def _label_from_score(score: float) -> str:
    if score >= 80:
        return "HIGH"
    if score >= 60:
        return "MEDIUM"
    if score >= 40:
        return "LOW"
    return "VERY_LOW"


# ---------------------------------------------------------------------------
# 1. clasificador de setup (igual a v2)
# ---------------------------------------------------------------------------


def classify_setup(klines: dict, ticker24: dict) -> dict:
    if not _is_ok(klines) or not _is_ok(ticker24):
        return {"type": "NO_SETUP", "confidence": "LOW", "reasons": ["Datos insuficientes"]}

    indicators = klines.get("indicators", {})
    trend = klines.get("trend")
    structure = klines.get("structure", {}).get("structure")
    rsi = indicators.get("rsi14")
    macd_label = indicators.get("macdLabel")
    macd_hist = indicators.get("macdHistogram")
    rel_vol = indicators.get("relativeVolume")
    ema20 = indicators.get("ema20")
    ema50 = indicators.get("ema50")
    ema200 = indicators.get("ema200")
    last_price = ticker24.get("lastPrice")
    pos_range = ticker24.get("positionInRangePct")
    supports = klines.get("supports", [])
    resistances = klines.get("resistances", [])

    near_support = bool(
        supports and last_price and _pct_distance(last_price, supports[0]) < 2.0
    )
    near_resistance = bool(
        resistances and last_price and _pct_distance(last_price, resistances[0]) < 1.0
    )
    above_resistance = bool(
        resistances and last_price and last_price > resistances[0]
    )

    reasons: list[str] = []

    if (
        above_resistance
        and rel_vol is not None and rel_vol >= 1.3
        and macd_label != "CRUCE_BAJISTA"
        and (macd_hist is None or macd_hist >= 0)
    ):
        reasons.append(f"Precio arriba de resistencia ({resistances[0]})")
        reasons.append(f"Volumen relativo {round(rel_vol, 2)}x")
        if rsi and rsi >= 55:
            reasons.append(f"RSI {round(rsi, 1)} confirmando momentum")
        return {
            "type": "BREAKOUT",
            "confidence": "HIGH" if rel_vol >= 1.7 else "MEDIUM",
            "reasons": reasons,
        }

    if (
        trend in ("ALCISTA", "ALCISTA_FUERTE")
        and ema20 and ema50 and last_price
        and last_price >= ema50 * 0.985
        and last_price <= ema20 * 1.02
    ):
        reasons.append(f"Tendencia {trend} en temporalidad operada")
        reasons.append("Precio retrocedió a zona EMA20-EMA50")
        if rsi and 40 <= rsi <= 60:
            reasons.append(f"RSI {round(rsi, 1)} en zona de retroceso saludable")
        return {
            "type": "PULLBACK_TREND",
            "confidence": "HIGH" if trend == "ALCISTA_FUERTE" else "MEDIUM",
            "reasons": reasons,
        }

    if (
        pos_range is not None and pos_range <= 30
        and rsi is not None and rsi <= 45
        and near_support and not above_resistance
    ):
        reasons.append(f"Posición {pos_range}% en rango 24h (parte baja)")
        reasons.append(f"RSI {round(rsi, 1)} en zona de sobreventa/débil")
        reasons.append(f"A {round(_pct_distance(last_price, supports[0]), 2)}% del soporte")
        if ema200 and last_price > ema200:
            reasons.append("Por encima de EMA200 (mean-reversion en tendencia mayor alcista)")
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
        return {"type": "MEAN_REVERSION", "confidence": confidence, "reasons": reasons}

    if (
        structure == "LATERAL"
        and near_support and not near_resistance
        and resistances
    ):
        reasons.append("Estructura lateral identificada")
        reasons.append(f"Cerca del soporte del rango ({supports[0]})")
        reasons.append(f"Resistencia clara en {resistances[0]}")
        return {"type": "RANGE_PLAY", "confidence": "MEDIUM", "reasons": reasons}

    if trend in ("BAJISTA", "BAJISTA_FUERTE"):
        reasons.append(f"Tendencia {trend} en contra")
    if near_resistance:
        reasons.append("Precio pegado a resistencia")
    if rsi is not None and rsi >= 75:
        reasons.append(f"RSI {round(rsi, 1)} en sobrecompra")
    if not reasons:
        reasons.append("No se identifica un setup limpio")
    return {"type": "NO_SETUP", "confidence": "LOW", "reasons": reasons}


# ---------------------------------------------------------------------------
# 2. checklist contextual → setupScore
# ---------------------------------------------------------------------------


def _eval_rsi_for_setup(setup_type: str, rsi):
    if rsi is None:
        return None, "N/A"
    if setup_type == "BREAKOUT":
        if 55 <= rsi <= 75:
            return True, f"RSI {round(rsi, 1)} válido para breakout"
        return False, f"RSI {round(rsi, 1)} no convincente para breakout"
    if setup_type == "PULLBACK_TREND":
        if 40 <= rsi <= 60:
            return True, f"RSI {round(rsi, 1)} en pullback saludable"
        if rsi < 40:
            return None, f"RSI {round(rsi, 1)} sugiere pullback profundo"
        return False, f"RSI {round(rsi, 1)} sin retroceso real"
    if setup_type == "MEAN_REVERSION":
        if rsi <= 35:
            return True, f"RSI {round(rsi, 1)} en sobreventa: ideal"
        if rsi <= 45:
            return True, f"RSI {round(rsi, 1)} débil: válido"
        return None, f"RSI {round(rsi, 1)} no es lo bastante bajo"
    if setup_type == "RANGE_PLAY":
        if 30 <= rsi <= 55:
            return True, f"RSI {round(rsi, 1)} compatible con piso de rango"
        if rsi > 65:
            return False, f"RSI {round(rsi, 1)} muy alto para piso"
        return None, f"RSI {round(rsi, 1)}"
    if 50 <= rsi <= 65:
        return True, f"RSI {round(rsi, 1)}"
    return False, f"RSI {round(rsi, 1)}"


def _eval_macd_for_setup(setup_type: str, label, hist):
    if label is None and hist is None:
        return None, "N/A"
    detail = f"label={label}, hist={hist}"
    if setup_type in ("BREAKOUT", "NO_SETUP"):
        if label == "CRUCE_ALCISTA" or (hist is not None and hist > 0):
            return True, detail
        return False, detail
    if setup_type in ("MEAN_REVERSION", "RANGE_PLAY"):
        return None, detail
    if setup_type == "PULLBACK_TREND":
        if label == "CRUCE_BAJISTA" and hist is not None and hist < 0:
            return False, detail
        return None, detail
    return None, detail


def _eval_ema_for_setup(setup_type: str, price, ema20, ema50, ema200):
    if not all([price, ema20, ema50, ema200]):
        return None, "EMAs incompletas"
    detail = f"price={round(price, 4)}, ema20={round(ema20, 4)}, ema50={round(ema50, 4)}, ema200={round(ema200, 4)}"
    if setup_type == "BREAKOUT":
        return (price > ema20 > ema50, detail)
    if setup_type == "PULLBACK_TREND":
        return (ema50 > ema200 and price > ema50 * 0.99, detail)
    if setup_type == "MEAN_REVERSION":
        if price >= ema200:
            return True, detail
        return False, detail + " (debajo EMA200)"
    if setup_type == "RANGE_PLAY":
        return None, detail
    return (price > ema20 > ema50 > ema200, detail)


def _eval_volume_for_setup(setup_type: str, rel_vol):
    if rel_vol is None:
        return None, "N/A"
    if setup_type == "BREAKOUT":
        if rel_vol >= 1.5:
            return True, f"relVol={round(rel_vol, 2)} confirma ruptura"
        return False, f"relVol={round(rel_vol, 2)} insuficiente"
    if setup_type == "MEAN_REVERSION":
        return None, f"relVol={round(rel_vol, 2)} (no crítico)"
    if setup_type in ("PULLBACK_TREND", "RANGE_PLAY"):
        if rel_vol >= 1.0:
            return True, f"relVol={round(rel_vol, 2)}"
        return None, f"relVol={round(rel_vol, 2)} débil"
    if rel_vol >= 1.5:
        return True, f"relVol={round(rel_vol, 2)}"
    return False, f"relVol={round(rel_vol, 2)}"


def evaluate_setup_checklist(
    setup_type, info, ticker24, klines, depth, risk
) -> dict:
    items: list[dict] = []
    warnings: list[str] = []

    def add(name, ok, detail="", weight=1.0):
        items.append({"check": name, "ok": ok, "detail": detail, "weight": weight})

    if _is_ok(info):
        add(
            "Símbolo válido y en TRADING",
            info.get("valid", False) and info.get("status") == "TRADING",
            f"status={info.get('status')}",
            weight=1.0,
        )

    indicators = klines.get("indicators", {}) if _is_ok(klines) else {}

    if _is_ok(ticker24):
        pos = ticker24.get("positionInRangePct")
        if pos is not None:
            if setup_type == "BREAKOUT":
                ok = pos >= 60
                detail = f"pos={pos}% (breakout requiere parte alta)"
            elif setup_type in ("MEAN_REVERSION", "RANGE_PLAY"):
                ok = pos <= 35
                detail = f"pos={pos}% (mean-reversion requiere parte baja)"
            else:
                ok = not ticker24.get("nearHighWarning")
                detail = f"pos={pos}%"
            add("Posición coherente con setup", ok, detail, weight=1.5)

        mom = ticker24.get("momentumLabel")
        if mom in ("EXTREMO_BAJISTA", "EXTREMO_ALCISTA"):
            warnings.append(f"Movimiento 24h extremo: {mom}")

    if _is_ok(klines):
        trend = klines.get("trend")
        structure = klines.get("structure", {}).get("structure")
        if setup_type == "MEAN_REVERSION":
            ok = trend != "BAJISTA_FUERTE"
            add("Tendencia compatible con mean-reversion", ok, f"trend={trend}", weight=1.5)
        elif setup_type == "BREAKOUT":
            ok = trend in ("ALCISTA", "ALCISTA_FUERTE", "LATERAL")
            add("Tendencia compatible con breakout", ok, f"trend={trend}", weight=2.0)
        elif setup_type == "PULLBACK_TREND":
            ok = trend in ("ALCISTA", "ALCISTA_FUERTE")
            add("Tendencia alcista confirmada", ok, f"trend={trend}", weight=2.0)
        elif setup_type == "RANGE_PLAY":
            ok = structure == "LATERAL"
            add("Estructura lateral confirmada", ok, f"structure={structure}", weight=1.5)
        else:
            ok = trend in ("ALCISTA", "ALCISTA_FUERTE")
            add("Tendencia favorable", ok, f"trend={trend}", weight=2.0)

        rsi_ok, rsi_detail = _eval_rsi_for_setup(setup_type, indicators.get("rsi14"))
        add("RSI según setup", rsi_ok, rsi_detail, weight=1.2)

        macd_ok, macd_detail = _eval_macd_for_setup(
            setup_type,
            indicators.get("macdLabel"),
            indicators.get("macdHistogram"),
        )
        add("MACD según setup", macd_ok, macd_detail, weight=1.2)

        ema_ok, ema_detail = _eval_ema_for_setup(
            setup_type,
            ticker24.get("lastPrice") if _is_ok(ticker24) else None,
            indicators.get("ema20"),
            indicators.get("ema50"),
            indicators.get("ema200"),
        )
        add("EMAs alineadas con setup", ema_ok, ema_detail, weight=1.5)

        vol_ok, vol_detail = _eval_volume_for_setup(setup_type, indicators.get("relativeVolume"))
        add("Volumen según setup", vol_ok, vol_detail, weight=1.5)

    if _is_ok(depth):
        add(
            "Liquidez suficiente",
            depth.get("liquidityScore") in ("ALTA", "MEDIA"),
            f"liquidityScore={depth.get('liquidityScore')}",
            weight=1.0,
        )

    earned = sum(i["weight"] for i in items if i["ok"] is True)
    possible = sum(i["weight"] for i in items if i["ok"] is not None)
    score_pct = round(earned / possible * 100, 1) if possible > 0 else 0.0
    failures = [i["check"] for i in items if i["ok"] is False]

    return {
        "scorePct": score_pct,
        "label": _label_from_score(score_pct),
        "earnedWeight": round(earned, 2),
        "possibleWeight": round(possible, 2),
        "failures": failures,
        "items": items,
        "warnings": warnings,
    }


# ---------------------------------------------------------------------------
# 3. risk management + cost-adjusted RR
# ---------------------------------------------------------------------------


def build_risk_management(spot_price, klines, setup_type) -> dict:
    if not spot_price:
        return {"available": False, "reason": "Sin precio spot"}
    if not _is_ok(klines):
        return {"available": False, "reason": "Sin análisis técnico"}
    indicators = klines.get("indicators", {})
    atr_v = indicators.get("atr14")
    supports = klines.get("supports", [])
    resistances = klines.get("resistances", [])
    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None
    second_resistance = resistances[1] if len(resistances) >= 2 else None

    if nearest_support and atr_v:
        stop_by_support = nearest_support - 0.25 * atr_v
        stop_by_atr = spot_price - 1.5 * atr_v
        stop = min(stop_by_support, stop_by_atr)
        method = "min(soporte - 0.25*ATR, spot - 1.5*ATR)"
    elif atr_v:
        stop = spot_price - 1.5 * atr_v
        method = "spot - 1.5*ATR"
    elif nearest_support:
        stop = nearest_support * 0.998
        method = "soporte - 0.2%"
    else:
        stop = spot_price * 0.97
        method = "fallback -3%"

    risk_per_unit = spot_price - stop
    if risk_per_unit <= 0:
        return {"available": False, "reason": "Stop por encima del precio"}

    tp1 = nearest_resistance or (spot_price + 2 * risk_per_unit)
    tp2 = second_resistance or (spot_price + 3 * risk_per_unit)
    rr_tp1 = round((tp1 - spot_price) / risk_per_unit, 2)
    rr_tp2 = round((tp2 - spot_price) / risk_per_unit, 2)

    return {
        "available": True,
        "entry": round(spot_price, 8),
        "stop": round(stop, 8),
        "stopMethod": method,
        "atr14": atr_v,
        "tp1": round(tp1, 8),
        "tp2": round(tp2, 8),
        "riskPerUnit": round(risk_per_unit, 8),
        "riskPct": round(risk_per_unit / spot_price * 100, 2),
        "rrTp1": rr_tp1,
        "rrTp2": rr_tp2,
        "rrTp1Acceptable": rr_tp1 >= 1.2,
        "rrTp2Acceptable": rr_tp2 >= 2.0,
        "setupTypeApplied": setup_type,
    }


def cost_adjust_rr(
    risk: dict,
    fee_pct_round_trip: float = DEFAULT_FEE_PCT_ROUND_TRIP,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> dict:
    """Recalcula R:B descontando comisiones y slippage."""
    if not risk.get("available"):
        return {"available": False}
    entry = risk["entry"]
    stop = risk["stop"]
    tp1 = risk["tp1"]
    tp2 = risk["tp2"]
    cost_pct = (fee_pct_round_trip + slippage_pct) / 100  # como fracción
    cost_per_unit = entry * cost_pct  # costo total redondeo en unidades de precio
    # Riesgo neto: distancia al stop + costo (ambos restan a tu cuenta)
    risk_net = (entry - stop) + cost_per_unit
    reward_tp1_net = (tp1 - entry) - cost_per_unit
    reward_tp2_net = (tp2 - entry) - cost_per_unit
    rr_tp1_net = round(reward_tp1_net / risk_net, 2) if risk_net > 0 else None
    rr_tp2_net = round(reward_tp2_net / risk_net, 2) if risk_net > 0 else None
    return {
        "available": True,
        "feePctRoundTrip": fee_pct_round_trip,
        "slippagePct": slippage_pct,
        "costPerUnit": round(cost_per_unit, 8),
        "rrTp1Raw": risk["rrTp1"],
        "rrTp1Net": rr_tp1_net,
        "rrTp2Raw": risk["rrTp2"],
        "rrTp2Net": rr_tp2_net,
        "rrTp1NetAcceptable": rr_tp1_net is not None and rr_tp1_net >= 1.0,
        "rrTp2NetAcceptable": rr_tp2_net is not None and rr_tp2_net >= 2.0,
    }


# ---------------------------------------------------------------------------
# 4. candle status (vela cerrada o no)
# ---------------------------------------------------------------------------


def analyze_candle_status(klines: dict, interval: str) -> dict:
    if not _is_ok(klines):
        return {"isClosed": None, "reason": "Sin klines"}
    last = klines.get("lastCandle")
    if not last:
        return {"isClosed": None, "reason": "Sin última vela"}
    close_time_ms = last.get("closeTime")
    now_ms = int(time.time() * 1000)
    is_closed = close_time_ms is not None and now_ms > close_time_ms
    minutes_to_close = (
        round(max(close_time_ms - now_ms, 0) / 60_000, 1)
        if close_time_ms
        else None
    )
    interval_min = _INTERVAL_MINUTES.get(interval, 60)
    elapsed_min = (
        round((interval_min - minutes_to_close), 1)
        if minutes_to_close is not None
        else None
    )
    return {
        "interval": interval,
        "isClosed": is_closed,
        "minutesToClose": minutes_to_close if not is_closed else 0,
        "candleProgressPct": round(elapsed_min / interval_min * 100, 1)
        if elapsed_min is not None and interval_min
        else None,
        "reliabilityPenalty": 0 if is_closed else 25,
    }


# ---------------------------------------------------------------------------
# 5. candle confirmation (métricas de la última vela)
# ---------------------------------------------------------------------------


def analyze_candle_confirmation(klines: dict, supports: list[float]) -> dict:
    if not _is_ok(klines):
        return {"available": False}
    candles = klines.get("lastCandles") or []
    if len(candles) < 2:
        return {"available": False, "reason": "Velas insuficientes"}
    last = candles[-1]
    prev = candles[-2]
    metrics = candle_metrics(last, prev)
    nearest_support = supports[0] if supports else None
    rejection_at_support = False
    if nearest_support and metrics.get("lowerWickPct") is not None:
        # rechazo: la mecha inferior llegó cerca del soporte y cerró arriba
        if (
            last["low"] <= nearest_support * 1.005
            and last["close"] > nearest_support
            and metrics.get("lowerWickPct", 0) >= 25
        ):
            rejection_at_support = True

    # score de confirmación 0-100
    score = 0
    reasons = []
    if metrics.get("isBullish"):
        score += 20; reasons.append("vela alcista")
    cp = metrics.get("closePositionInRangePct") or 0
    if cp >= 70:
        score += 25; reasons.append(f"cerró en {cp}% alto del rango")
    elif cp >= 55:
        score += 12; reasons.append(f"cerró en {cp}% del rango")
    if (metrics.get("lowerWickPct") or 0) >= 35:
        score += 20; reasons.append("mecha inferior fuerte")
    if metrics.get("closedAbovePrevHigh"):
        score += 25; reasons.append("cerró arriba del máximo previo")
    if rejection_at_support:
        score += 15; reasons.append("rechazo en soporte")
    if metrics.get("closedBelowPrevLow"):
        score -= 25; reasons.append("cerró debajo del mínimo previo (señal bajista)")

    return {
        "available": True,
        **metrics,
        "rejectionAtSupport": rejection_at_support,
        "confirmationScore": max(0, min(score, 100)),
        "signals": reasons,
    }


# ---------------------------------------------------------------------------
# 6. fuerza de soportes y resistencias
# ---------------------------------------------------------------------------


def score_levels_strength(klines: dict) -> dict:
    if not _is_ok(klines):
        return {"supports": [], "resistances": []}
    candles = klines.get("allCandles") or []
    atr_v = klines.get("indicators", {}).get("atr14")
    supports = klines.get("supports", [])
    resistances = klines.get("resistances", [])
    return {
        "supports": [
            {"price": p, **level_strength(p, candles, atr_v)} for p in supports
        ],
        "resistances": [
            {"price": p, **level_strength(p, candles, atr_v)} for p in resistances
        ],
    }


# ---------------------------------------------------------------------------
# 7. régimen de mercado
# ---------------------------------------------------------------------------


def detect_market_regime(klines: dict, ticker24: dict) -> dict:
    if not _is_ok(klines) or not _is_ok(ticker24):
        return {"regime": "UNKNOWN"}
    indicators = klines.get("indicators", {})
    atr_v = indicators.get("atr14")
    last_price = ticker24.get("lastPrice")
    rel_vol = indicators.get("relativeVolume")
    trend = klines.get("trend")
    structure = klines.get("structure", {}).get("structure")

    atr_pct = (atr_v / last_price * 100) if (atr_v and last_price) else None
    if atr_pct is None:
        volatility = "UNKNOWN"
    elif atr_pct < 0.5:
        volatility = "LOW"
    elif atr_pct < 2.0:
        volatility = "NORMAL"
    else:
        volatility = "HIGH"

    if trend in ("ALCISTA_FUERTE", "BAJISTA_FUERTE"):
        trend_strength = "STRONG"
    elif trend in ("ALCISTA", "BAJISTA"):
        trend_strength = "MODERATE"
    else:
        trend_strength = "WEAK"

    # Reglas
    if trend in ("BAJISTA", "BAJISTA_FUERTE"):
        regime = "TRENDING_DOWN"
    elif trend in ("ALCISTA", "ALCISTA_FUERTE"):
        regime = "TRENDING_UP"
    elif structure == "LATERAL" and volatility == "LOW":
        regime = "LOW_VOL_RANGE"
    elif structure == "LATERAL" and volatility == "HIGH":
        regime = "HIGH_VOL_RANGE"
    elif volatility == "HIGH" and trend == "LATERAL":
        regime = "VOL_EXPANSION"
    else:
        regime = "CHOP"

    return {
        "regime": regime,
        "volatility": volatility,
        "atrPctOfPrice": round(atr_pct, 3) if atr_pct else None,
        "trendStrength": trend_strength,
        "relativeVolume": rel_vol,
        "meanReversionFriendly": regime in ("LOW_VOL_RANGE", "HIGH_VOL_RANGE"),
        "breakoutFriendly": regime in ("VOL_EXPANSION", "TRENDING_UP"),
        "continuationFriendly": regime == "TRENDING_UP",
        "avoidLongs": regime == "TRENDING_DOWN",
    }


# ---------------------------------------------------------------------------
# 8. microestructura
# ---------------------------------------------------------------------------


def analyze_microstructure(trades, agg, depth) -> dict:
    out: dict = {
        "tradesBuyerAggPct": None,
        "aggBuyerAggPct": None,
        "depthImbalance": None,
        "divergence": False,
        "divergenceMagnitude": None,
        "consensusBias": "NEUTRAL",
        "notes": [],
    }
    if _is_ok(trades):
        out["tradesBuyerAggPct"] = trades.get("buyerAggressionPct")
    if _is_ok(agg):
        out["aggBuyerAggPct"] = agg.get("buyAggressionPct")
    if _is_ok(depth):
        out["depthImbalance"] = depth.get("imbalance")
    t, a = out["tradesBuyerAggPct"], out["aggBuyerAggPct"]
    if t is not None and a is not None:
        out["divergenceMagnitude"] = round(abs(t - a), 2)
        if (t > 55 and a < 45) or (t < 45 and a > 55):
            out["divergence"] = True
            recent = "compradora" if t > a else "vendedora"
            out["notes"].append(
                f"Divergencia: ventana corta {t}% vs ventana ancha {a}% "
                f"(la presión {recent} es la más reciente)"
            )
        if t < 40 and a < 40:
            out["consensusBias"] = "BEARISH"
        elif t > 60 and a > 60:
            out["consensusBias"] = "BULLISH"
        elif out["divergence"]:
            out["consensusBias"] = "MIXED"
    return out


# ---------------------------------------------------------------------------
# 10. entradas múltiples (con bug de breakout corregido)
# ---------------------------------------------------------------------------


def build_entries(spot_price, klines) -> dict:
    if not _is_ok(klines):
        return {"aggressive": spot_price}
    supports = klines.get("supports", [])
    resistances = klines.get("resistances", [])
    atr_v = klines.get("indicators", {}).get("atr14")
    nearest_support = supports[0] if supports else None
    nearest_resistance = resistances[0] if resistances else None
    breakout_entry = None
    if nearest_resistance and atr_v:
        breakout_entry = round(nearest_resistance + 0.5 * atr_v, 8)
    elif nearest_resistance:
        breakout_entry = round(nearest_resistance * 1.005, 8)
    return {
        "aggressive": round(spot_price, 8),
        "supportPullback": round(nearest_support, 8) if nearest_support else None,
        "breakoutConfirmation": breakout_entry,
    }


# ---------------------------------------------------------------------------
# 11. execution score (¿se puede entrar AHORA?)
# ---------------------------------------------------------------------------


def compute_execution_score(
    micro: dict,
    candle_conf: dict,
    candle_status: dict,
    klines: dict,
    risk: dict,
    cost_rr: dict,
    higher_tf: dict,
    setup_type: str,
    spot_price,
) -> dict:
    """Score 0-100 que NO mide el setup sino la ventana de entrada actual.

    Los pesos suman 100 cuando todos los componentes están disponibles.
    """
    components: list[dict] = []

    def add(name, points, max_points, detail):
        components.append({
            "name": name,
            "points": round(points, 1),
            "max": max_points,
            "detail": detail,
        })

    # Volumen relativo (max 20)
    rel_vol = klines.get("indicators", {}).get("relativeVolume") if _is_ok(klines) else None
    if rel_vol is None:
        add("volumeParticipation", 0, 20, "rel_vol N/A")
    elif rel_vol >= 1.5:
        add("volumeParticipation", 20, 20, f"relVol={round(rel_vol,2)}")
    elif rel_vol >= 1.0:
        add("volumeParticipation", 14, 20, f"relVol={round(rel_vol,2)}")
    elif rel_vol >= 0.7:
        add("volumeParticipation", 6, 20, f"relVol={round(rel_vol,2)} bajo")
    else:
        add("volumeParticipation", 0, 20, f"relVol={round(rel_vol,2)} ausente")

    # Microestructura (max 20)
    bias = micro.get("consensusBias")
    if bias == "BULLISH":
        add("microstructure", 20, 20, "consenso comprador")
    elif bias == "NEUTRAL":
        add("microstructure", 12, 20, "neutral")
    elif bias == "MIXED":
        add("microstructure", 6, 20, "divergente")
    else:
        add("microstructure", 0, 20, "consenso vendedor")

    # Confirmación de vela (max 20)
    if candle_conf.get("available"):
        cs = candle_conf.get("confirmationScore", 0)
        # Convertimos 0-100 a 0-20
        add("candleConfirmation", cs * 0.20, 20, f"score={cs}")
    else:
        add("candleConfirmation", 0, 20, "no disponible")

    # Cost-adjusted RR TP1 (max 15)
    if cost_rr.get("available"):
        rr1 = cost_rr.get("rrTp1Net")
        if rr1 is None:
            add("costAdjustedRR", 0, 15, "N/A")
        elif rr1 >= 1.2:
            add("costAdjustedRR", 15, 15, f"rrTp1Net={rr1}")
        elif rr1 >= 1.0:
            add("costAdjustedRR", 10, 15, f"rrTp1Net={rr1}")
        elif rr1 >= 0.7:
            add("costAdjustedRR", 4, 15, f"rrTp1Net={rr1} débil")
        else:
            add("costAdjustedRR", 0, 15, f"rrTp1Net={rr1} negativo o muy bajo")
    else:
        add("costAdjustedRR", 0, 15, "no calculado")

    # Vela cerrada (max 10)
    if candle_status.get("isClosed"):
        add("candleClosed", 10, 10, "vela cerrada")
    elif candle_status.get("candleProgressPct", 0) >= 80:
        add("candleClosed", 6, 10, "casi cerrada")
    else:
        add("candleClosed", 2, 10, "vela abierta")

    # Distancia al soporte (mean-reversion necesita estar muy cerca; otros no penalizan)
    supports = klines.get("supports", []) if _is_ok(klines) else []
    if setup_type in ("MEAN_REVERSION", "RANGE_PLAY") and supports and spot_price:
        dist = _pct_distance(spot_price, supports[0])
        if dist < 0.5:
            add("supportDistance", 10, 10, f"a {round(dist,2)}% del soporte")
        elif dist < 1.5:
            add("supportDistance", 6, 10, f"a {round(dist,2)}% del soporte")
        else:
            add("supportDistance", 0, 10, f"a {round(dist,2)}% del soporte (lejos)")
    else:
        add("supportDistance", 7, 10, "no aplica al setup")

    # Higher TF context (max 5)
    hi_score = 5
    hi_detail = "ok"
    for tf in ("4h", "1d"):
        ctx = higher_tf.get(tf, {})
        if ctx.get("nearMajorResistance"):
            hi_score -= 3
            hi_detail = f"cerca de resistencia mayor {tf}"
            break
        if ctx.get("trend") == "BAJISTA_FUERTE":
            hi_score -= 5
            hi_detail = f"{tf} en BAJISTA_FUERTE"
            break
    add("higherTimeframeAlignment", max(0, hi_score), 5, hi_detail)

    earned = sum(c["points"] for c in components)
    possible = sum(c["max"] for c in components)
    score_pct = round(earned / possible * 100, 1) if possible > 0 else 0.0

    weaknesses = [c["name"] for c in components if c["points"] < c["max"] * 0.4]

    return {
        "scorePct": score_pct,
        "label": _label_from_score(score_pct),
        "earnedPoints": round(earned, 1),
        "maxPoints": possible,
        "components": components,
        "mainWeaknesses": weaknesses,
    }


# ---------------------------------------------------------------------------
# 12. blocking rules formales
# ---------------------------------------------------------------------------


def evaluate_blocking_rules(
    klines, micro, risk, cost_rr, candle_status, higher_tf, setup_type, supports, spot_price
) -> list[dict]:
    rules: list[dict] = []

    rel_vol = klines.get("indicators", {}).get("relativeVolume") if _is_ok(klines) else None
    if (
        rel_vol is not None and rel_vol < 0.5
        and micro.get("consensusBias") in ("BEARISH", "MIXED")
    ):
        rules.append({
            "rule": "LOW_VOLUME_NO_BUYERS",
            "triggered": True,
            "severity": "HIGH",
            "reason": f"relVol={round(rel_vol,2)} + microestructura {micro.get('consensusBias')}",
        })

    if cost_rr.get("available"):
        rr1n = cost_rr.get("rrTp1Net")
        if rr1n is not None and rr1n < 1.0:
            rules.append({
                "rule": "BAD_TP1_RR_NET",
                "triggered": True,
                "severity": "HIGH",
                "reason": f"rrTp1Net={rr1n} < 1.0 (no compensa costos)",
            })

    if (
        micro.get("tradesBuyerAggPct") is not None
        and micro.get("aggBuyerAggPct") is not None
        and micro.get("tradesBuyerAggPct") < 40
        and micro.get("aggBuyerAggPct") < 40
        and micro.get("depthImbalance") == "VENDEDOR_DOMINA"
    ):
        rules.append({
            "rule": "BEARISH_MICROSTRUCTURE_TRIPLE",
            "triggered": True,
            "severity": "HIGH",
            "reason": "trades, aggTrades y depth todos vendedores",
        })

    if not candle_status.get("isClosed") and setup_type != "MEAN_REVERSION":
        # Mean-reversion en soporte se decide en tiempo real; los demás
        # setups dependen de cierre confirmado.
        rules.append({
            "rule": "UNCONFIRMED_CANDLE",
            "triggered": True,
            "severity": "MEDIUM",
            "reason": (
                f"Vela {candle_status.get('interval')} sin cerrar "
                f"({candle_status.get('minutesToClose')} min restantes)"
            ),
        })

    if setup_type == "MEAN_REVERSION" and supports and spot_price:
        dist = _pct_distance(spot_price, supports[0])
        atr_v = klines.get("indicators", {}).get("atr14") if _is_ok(klines) else None
        if dist > 1.5 or (atr_v and (spot_price - supports[0]) > atr_v):
            rules.append({
                "rule": "PRICE_TOO_FAR_FROM_SUPPORT",
                "triggered": True,
                "severity": "MEDIUM",
                "reason": f"Distancia al soporte {round(dist,2)}% > 1 ATR",
            })

    for tf in ("4h", "1d"):
        ctx = higher_tf.get(tf, {})
        if ctx.get("trend") == "BAJISTA_FUERTE" and setup_type != "MEAN_REVERSION":
            rules.append({
                "rule": f"BEARISH_HIGHER_TF_{tf}",
                "triggered": True,
                "severity": "HIGH",
                "reason": f"Marco {tf} en BAJISTA_FUERTE",
            })
        if ctx.get("nearMajorResistance"):
            rules.append({
                "rule": f"NEAR_MAJOR_RESISTANCE_{tf}",
                "triggered": True,
                "severity": "MEDIUM",
                "reason": f"Precio a <1% de resistencia {tf}",
            })

    return rules


# ---------------------------------------------------------------------------
# 13. plan condicional con escenarios
# ---------------------------------------------------------------------------


def build_trade_plan_conditional(
    setup, klines, risk, supports_strength, entries
) -> dict:
    if not risk.get("available"):
        return {"available": False}

    setup_type = setup.get("type", "NO_SETUP")
    scenarios: list[dict] = []

    nearest_support_data = (
        supports_strength.get("supports", [{}])[0]
        if supports_strength.get("supports")
        else {}
    )

    # Escenario A: pullback al soporte (válido para mean-reversion, range-play, pullback-trend)
    if setup_type in ("MEAN_REVERSION", "RANGE_PLAY", "PULLBACK_TREND"):
        s_price = nearest_support_data.get("price")
        if s_price:
            scenarios.append({
                "id": "A",
                "name": "Compra pullback al soporte",
                "entryZone": [
                    round(s_price * 0.999, 8),
                    round(s_price * 1.003, 8),
                ],
                "requires": [
                    f"Vela 1h cerrando arriba de {s_price}",
                    "candleConfirmation.confirmationScore >= 60",
                    "microstructure.consensusBias != BEARISH",
                    "relativeVolume >= 0.7",
                    f"supportStrength.strengthScore >= 60 (actual: {nearest_support_data.get('strengthScore')})",
                ],
                "stop": risk["stop"],
                "tp1": risk["tp1"],
                "tp2": risk["tp2"],
                "rrTp2": risk["rrTp2"],
                "invalidIf": (
                    f"Cierre {klines.get('interval', '1h')} debajo de "
                    f"{risk['stop']} con volumen"
                ),
            })

    # Escenario B: confirmación de breakout (para breakout o cuando hay resistencia clara)
    breakout_entry = entries.get("breakoutConfirmation")
    if breakout_entry:
        scenarios.append({
            "id": "B",
            "name": "Compra confirmación de breakout",
            "entryAbove": breakout_entry,
            "requires": [
                f"Cierre {klines.get('interval', '1h')} arriba de {breakout_entry}",
                "Expansión de volumen (relativeVolume >= 1.5)",
                "Retesteo exitoso del nivel roto",
                "microstructure.consensusBias = BULLISH o NEUTRAL",
            ],
            "stop": risk["tp1"],  # tras breakout, el viejo techo actúa como stop
            "tp1": round(breakout_entry * 1.02, 8),
            "tp2": round(breakout_entry * 1.04, 8),
            "invalidIf": f"Vuelve debajo de {risk['tp1']} en menos de 2 velas",
        })

    if not scenarios:
        return {
            "available": False,
            "reason": f"No hay escenarios accionables para setup {setup_type}",
        }

    # Recomendar el mejor escenario:
    if setup_type in ("MEAN_REVERSION", "RANGE_PLAY"):
        best = "A"
    elif setup_type == "BREAKOUT":
        best = "B"
    else:
        best = "WAIT_FOR_PULLBACK_OR_CONFIRMATION"

    return {
        "available": True,
        "bestEntryType": best,
        "scenarios": scenarios,
    }


# ---------------------------------------------------------------------------
# 14. recomendación final (combina ambos scores)
# ---------------------------------------------------------------------------


_POSITION_SIZE = {
    "STRONG_BUY": "70%-100% del tamaño normal",
    "BUY_PARTIAL": "30%-50% del tamaño normal",
    "WAIT": "0% — esperar confirmación",
    "AVOID": "0% — no operar",
}


def build_recommendation(
    setup: dict,
    setup_score: dict,
    exec_score: dict,
    blocking: list[dict],
    risk: dict,
    cost_rr: dict,
    klines: dict,
) -> dict:
    setup_type = setup.get("type", "NO_SETUP")
    setup_conf = setup.get("confidence", "LOW")
    s_pct = setup_score.get("scorePct", 0)
    e_pct = exec_score.get("scorePct", 0)
    rr_tp2_net_ok = bool(cost_rr.get("rrTp2NetAcceptable")) if cost_rr.get("available") else False

    reasons: list[str] = [
        f"Setup detectado: {setup_type} (confianza {setup_conf})",
        f"setupScore: {s_pct}% ({setup_score.get('label')})",
        f"executionScore: {e_pct}% ({exec_score.get('label')})",
    ]
    warnings: list[str] = list(setup_score.get("warnings", []))

    # 1) Reglas bloqueantes HIGH → AVOID directo.
    high_blocks = [r for r in blocking if r.get("severity") == "HIGH"]
    if high_blocks:
        reasons.append(f"{len(high_blocks)} regla(s) bloqueante(s) HIGH activadas")
        for r in high_blocks:
            warnings.append(f"[BLOQUEO HIGH] {r['rule']}: {r['reason']}")
        return {
            "action": "AVOID",
            "positionSizeSuggestion": _POSITION_SIZE["AVOID"],
            "reasonSummary": "Reglas bloqueantes críticas activadas",
            "reasons": reasons,
            "warnings": warnings,
            "nextAction": "Esperar a que las reglas bloqueantes desaparezcan",
        }

    # 2) Acción base por setup score y RR TP2 NETO.
    if s_pct >= 80 and rr_tp2_net_ok:
        action = "STRONG_BUY"
    elif s_pct >= 65 and rr_tp2_net_ok:
        action = "BUY_PARTIAL"
    elif s_pct >= 50:
        action = "WAIT"
    else:
        action = "AVOID"

    # 3) Cap por executionScore.
    if e_pct < 40:
        new_action = "AVOID" if action != "AVOID" else action
        if new_action != action:
            reasons.append(f"Degradado a AVOID: executionScore {e_pct}% < 40")
        action = new_action
    elif e_pct < 65:
        if action in ("STRONG_BUY", "BUY_PARTIAL"):
            reasons.append(f"Degradado a WAIT: executionScore {e_pct}% < 65")
            action = "WAIT"

    # 4) Cap por confianza del setup.
    if action == "STRONG_BUY" and setup_conf != "HIGH":
        action = "BUY_PARTIAL"
        reasons.append(f"Degradado a BUY_PARTIAL: confianza setup = {setup_conf} (HIGH requerido)")

    # 5) Reglas bloqueantes MEDIUM → degradan un nivel.
    medium_blocks = [r for r in blocking if r.get("severity") == "MEDIUM"]
    for r in medium_blocks:
        before = action
        action = _downgrade(action)
        if before != action:
            reasons.append(f"Degradado de {before} a {action}: {r['rule']}")
        warnings.append(f"[BLOQUEO MEDIUM] {r['rule']}: {r['reason']}")

    # 6) Failures del checklist como warnings.
    if setup_score.get("failures"):
        warnings.append("Checks fallidos: " + "; ".join(setup_score["failures"][:5]))

    # next action según resultado
    if action == "AVOID":
        next_action = "No operar. Reevaluar cuando cambie el contexto."
    elif action == "WAIT":
        next_action = "Monitorear escenarios A/B del tradePlan; entrar solo si se cumplen requires."
    elif action == "BUY_PARTIAL":
        next_action = "Entrar parcial siguiendo el escenario sugerido en tradePlan.bestEntryType."
    else:
        next_action = "Entrada agresiva permitida; respetar stop e invalidación."

    summary = (
        f"setupScore {s_pct}% / executionScore {e_pct}%. "
        f"Setup {setup_type} con {len(blocking)} regla(s) bloqueante(s). "
        f"Acción: {action}."
    )

    return {
        "action": action,
        "positionSizeSuggestion": _POSITION_SIZE[action],
        "reasonSummary": summary,
        "reasons": reasons,
        "warnings": warnings,
        "nextAction": next_action,
    }


# ---------------------------------------------------------------------------
# 15. orquestador
# ---------------------------------------------------------------------------


def analyze_crypto(
    token: str,
    quote: str = "USDT",
    interval: str = "1h",
    klines_limit: int = 500,
    depth_limit: int = 100,
    trades_limit: int = 100,
    agg_trades_limit: int = 500,
    window_size: str = "1h",
    include_futures: bool = True,
    include_higher_tf: bool = True,
    fee_pct_round_trip: float = DEFAULT_FEE_PCT_ROUND_TRIP,
    slippage_pct: float = DEFAULT_SLIPPAGE_PCT,
) -> dict:
    started = time.time()
    symbol = f"{token.upper()}{quote.upper()}"

    # 1) exchangeInfo va primero (cacheado): si el símbolo no existe, abortamos
    #    sin gastar las otras 17 llamadas.
    info = _cached_exchange_info(symbol)
    if not _is_ok(info) or not info.get("valid"):
        return {
            "token": token.upper(),
            "symbol": symbol,
            "error": True,
            "message": "Símbolo inválido o no disponible",
            "exchangeInfo": info,
        }

    # 2) Construimos la batería de llamadas independientes y las disparamos
    #    todas en paralelo. avg_price y open_interest se llaman SIN spot_price;
    #    los campos derivados (deviationPct, openInterestNotional) se calculan
    #    después, sin volver a llamar.
    tasks: dict[str, tuple] = {
        "price":     (get_ticker_price,         (symbol,)),
        "avg":       (get_avg_price,            (symbol,)),
        "ticker24":  (get_ticker_24h,           (symbol,)),
        "window":    (get_ticker_window,        (symbol, window_size)),
        "klines":    (get_klines_analysis,      (symbol, interval, klines_limit)),
        "depth":     (get_order_book_analysis,  (symbol, depth_limit)),
        "trades":    (get_recent_trades,        (symbol, trades_limit)),
        "agg":       (get_agg_trades,           (symbol, agg_trades_limit)),
        "book":      (get_book_ticker,          (symbol,)),
    }
    if include_futures:
        tasks.update({
            "f24":     (get_futures_ticker_24h, (symbol,)),
            "oi":      (get_open_interest,      (symbol,)),
            "funding": (get_funding_rate,       (symbol,)),
            "premium": (get_premium_index,      (symbol,)),
        })
    if include_higher_tf:
        tasks.update({
            "klines_4h": (get_klines_analysis, (symbol, "4h", 250)),
            "klines_1d": (get_klines_analysis, (symbol, "1d", 250)),
        })

    results = _run_parallel(tasks, max_workers=min(len(tasks), 16))

    price = results["price"]
    spot_price = price["price"] if _is_ok(price) else None

    # Enriquecimiento post-paralelo (no requiere nuevas llamadas HTTP).
    avg = results["avg"]
    if spot_price and _is_ok(avg) and avg.get("avgPrice"):
        dev = (spot_price - avg["avgPrice"]) / avg["avgPrice"] * 100
        avg["deviationPct"] = round(dev, 4)
        if abs(dev) < 0.1:
            avg["deviationLabel"] = "EN_PROMEDIO"
        elif dev > 0.5:
            avg["deviationLabel"] = "POR_ENCIMA"
        elif dev < -0.5:
            avg["deviationLabel"] = "POR_DEBAJO"
        else:
            avg["deviationLabel"] = "CERCANO"

    ticker24 = results["ticker24"]
    window = results["window"]
    klines = results["klines"]
    depth = results["depth"]
    trades = results["trades"]
    agg = results["agg"]
    book = results["book"]

    funding = {"error": True, "message": "Futures omitido"}
    futures_block = None
    if include_futures:
        oi = results["oi"]
        if spot_price and _is_ok(oi) and oi.get("openInterest"):
            oi["openInterestNotional"] = round(oi["openInterest"] * spot_price, 2)
        funding = results["funding"]
        futures_block = {
            "ticker24h": results["f24"],
            "openInterest": oi,
            "fundingRate": funding,
            "premiumIndex": results["premium"],
        }

    higher_tf = {}
    if include_higher_tf:
        for tf, key in (("4h", "klines_4h"), ("1d", "klines_1d")):
            k = results[key]
            if not _is_ok(k):
                higher_tf[tf] = {"error": True}
                continue
            last_close = k.get("lastCandle", {}).get("close")
            sup = k.get("supports", [])
            res = k.get("resistances", [])
            higher_tf[tf] = {
                "trend": k.get("trend"),
                "structure": k.get("structure", {}).get("structure"),
                "rsi14": k.get("indicators", {}).get("rsi14"),
                "lastClose": last_close,
                "nearestSupport": sup[0] if sup else None,
                "nearestResistance": res[0] if res else None,
                "nearMajorResistance": bool(
                    res and last_close and _pct_distance(last_close, res[0]) < 1.0
                ),
                "nearMajorSupport": bool(
                    sup and last_close and _pct_distance(last_close, sup[0]) < 1.0
                ),
            }

    setup = classify_setup(klines, ticker24)
    risk = build_risk_management(spot_price, klines, setup["type"])
    cost_rr = cost_adjust_rr(risk, fee_pct_round_trip, slippage_pct)
    candle_status = analyze_candle_status(klines, interval)
    supports_list = klines.get("supports", []) if _is_ok(klines) else []
    candle_conf = analyze_candle_confirmation(klines, supports_list)
    levels_strength = score_levels_strength(klines)
    market_regime = detect_market_regime(klines, ticker24)
    micro = analyze_microstructure(trades, agg, depth)
    micro_struct = (
        micro_structure(
            [c["high"] for c in klines.get("allCandles", [])],
            [c["low"] for c in klines.get("allCandles", [])],
        )
        if _is_ok(klines)
        else {"structure": "N/A"}
    )

    setup_score = evaluate_setup_checklist(setup["type"], info, ticker24, klines, depth, risk)
    entries = build_entries(spot_price, klines) if spot_price else {}
    exec_score = compute_execution_score(
        micro, candle_conf, candle_status, klines, risk, cost_rr,
        higher_tf, setup["type"], spot_price,
    )
    blocking = evaluate_blocking_rules(
        klines, micro, risk, cost_rr, candle_status, higher_tf,
        setup["type"], supports_list, spot_price,
    )
    trade_plan = build_trade_plan_conditional(setup, klines, risk, levels_strength, entries)
    recommendation = build_recommendation(
        setup, setup_score, exec_score, blocking, risk, cost_rr, klines
    )

    market_state = {
        "trend": klines.get("trend") if _is_ok(klines) else None,
        "structure": klines.get("structure", {}).get("structure") if _is_ok(klines) else None,
        "rsi14": klines.get("indicators", {}).get("rsi14") if _is_ok(klines) else None,
        "macdLabel": klines.get("indicators", {}).get("macdLabel") if _is_ok(klines) else None,
        "relativeVolume": klines.get("indicators", {}).get("relativeVolume") if _is_ok(klines) else None,
        "momentum24h": ticker24.get("momentumLabel") if _is_ok(ticker24) else None,
        "priceChange24hPct": ticker24.get("priceChangePercent") if _is_ok(ticker24) else None,
        "positionInRangePct": ticker24.get("positionInRangePct") if _is_ok(ticker24) else None,
        "liquidityScore": depth.get("liquidityScore") if _is_ok(depth) else None,
        "spreadPct": depth.get("spreadPct") if _is_ok(depth) else None,
        "fundingBias": funding.get("biasLabel") if _is_ok(funding) else None,
    }

    # Limpiamos allCandles del raw para no inflar el JSON.
    if _is_ok(klines) and "allCandles" in klines:
        del klines["allCandles"]

    return {
        "token": token.upper(),
        "quote": quote.upper(),
        "symbol": symbol,
        "interval": interval,
        "generatedAt": int(time.time() * 1000),
        "elapsedSeconds": round(time.time() - started, 2),
        "spotPrice": spot_price,
        "marketState": market_state,
        "marketRegime": market_regime,
        "candleStatus": candle_status,
        "candleConfirmation": candle_conf,
        "microTrend": micro_struct,
        "higherTimeframes": higher_tf,
        "setup": setup,
        "setupScore": setup_score,
        "executionScore": exec_score,
        "blockingRules": blocking,
        "supports": levels_strength.get("supports", []),
        "resistances": levels_strength.get("resistances", []),
        "entries": entries,
        "riskManagement": risk,
        "costAdjustedRR": cost_rr,
        "microstructure": micro,
        "tradePlan": trade_plan,
        "recommendation": recommendation,
        "raw": {
            "exchangeInfo": info,
            "tickerPrice": price,
            "avgPrice": avg,
            "ticker24h": ticker24,
            "tickerWindow": window,
            "klines": klines,
            "depth": depth,
            "trades": trades,
            "aggTrades": agg,
            "bookTicker": book,
            "futures": futures_block,
        },
        "sources": [
            "https://data-api.binance.vision",
            "https://fapi.binance.com" if include_futures else None,
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Análisis completo de una criptomoneda con scoring de setup vs ejecución."
    )
    parser.add_argument("token")
    parser.add_argument("--quote", default="USDT")
    parser.add_argument("--interval", default="1h")
    parser.add_argument("--klines-limit", type=int, default=500)
    parser.add_argument("--depth-limit", type=int, default=100)
    parser.add_argument("--no-futures", action="store_true")
    parser.add_argument("--no-higher-tf", action="store_true")
    parser.add_argument("--fee-pct", type=float, default=DEFAULT_FEE_PCT_ROUND_TRIP)
    parser.add_argument("--slippage-pct", type=float, default=DEFAULT_SLIPPAGE_PCT)
    parser.add_argument("--out")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument(
        "--no-raw",
        action="store_true",
        help="Omitir la sección 'raw' (~10x más liviano, ideal para LLMs).",
    )
    args = parser.parse_args()

    try:
        result = analyze_crypto(
            token=args.token,
            quote=args.quote,
            interval=args.interval,
            klines_limit=args.klines_limit,
            depth_limit=args.depth_limit,
            include_futures=not args.no_futures,
            include_higher_tf=not args.no_higher_tf,
            fee_pct_round_trip=args.fee_pct,
            slippage_pct=args.slippage_pct,
        )
    except Exception as e:  # noqa: BLE001
        print(f"Error fatal: {e}", file=sys.stderr)
        traceback.print_exc()
        return 2

    if args.no_raw and "raw" in result:
        del result["raw"]
    payload = json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        print(f"OK: análisis guardado en {args.out}")
        rec = result.get("recommendation", {})
        setup = result.get("setup", {})
        ss = result.get("setupScore", {})
        es = result.get("executionScore", {})
        print(f"Setup: {setup.get('type')} ({setup.get('confidence')}) | "
              f"setupScore={ss.get('scorePct')}% | executionScore={es.get('scorePct')}%")
        print(f"Recomendación: {rec.get('action')} — {rec.get('positionSizeSuggestion')}")
        print(f"  → {rec.get('reasonSummary')}")
        print(f"  → Next: {rec.get('nextAction')}")
        if result.get("blockingRules"):
            print("Bloqueos:")
            for b in result["blockingRules"]:
                print(f"  ! [{b['severity']}] {b['rule']}: {b['reason']}")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
