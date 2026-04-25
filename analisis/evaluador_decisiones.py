"""Evaluador de decisiones de trading.

Lee los JSON guardados en decisiones/, trae las velas posteriores de Binance y
rellena el campo evaluacionPosterior con el resultado real:
  - ¿Se ejecutó la orden LIMIT (escenario A)?
  - ¿Confirmó el breakout (escenario B)?
  - ¿Tocó TP1, TP2, stop, o ninguno?
  - Resultado en % y veredicto "decisionAcertada"

Uso:
    python3 -m analisis.evaluador_decisiones                 # evalúa todos los pendientes
    python3 -m analisis.evaluador_decisiones --file <ruta>   # evalúa uno específico
    python3 -m analisis.evaluador_decisiones --max-candles 96
    python3 -m analisis.evaluador_decisiones --force         # re-evalúa los ya cerrados
    python3 -m analisis.evaluador_decisiones --dry-run       # no escribe el JSON
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from binance._client import spot_get

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DECISIONES_DIR = PROJECT_ROOT / "decisiones"

INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
}


def fetch_klines(symbol: str, interval: str, start_ms: int, limit: int = 200) -> list[dict]:
    raw = spot_get(
        "/api/v3/klines",
        {
            "symbol": symbol.upper(),
            "interval": interval,
            "startTime": start_ms,
            "limit": min(limit, 1000),
        },
    )
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
            }
        )
    return out


def evaluate_long_trade(
    candles: list[dict],
    entry_trigger: float,
    entry_direction: str,
    stop: float,
    tp1: float,
    tp2: float,
) -> dict:
    """Simula un trade LONG sobre las velas posteriores.

    entry_direction:
        "limit_below" — orden LIMIT BUY: dispara cuando low <= entry_trigger.
        "stop_above"  — STOP BUY (breakout): dispara cuando high >= entry_trigger.

    En la vela donde se llena, busca primero si el stop o TP fue tocado en velas
    SIGUIENTES (no la misma para ser realista). Si en una vela posterior tanto
    el stop como TP1 son tocados, asume el peor caso (stop primero).
    """
    fill_index = None
    fill_price = None
    fill_time = None

    for i, c in enumerate(candles):
        if entry_direction == "limit_below" and c["low"] <= entry_trigger:
            fill_index = i
            fill_price = entry_trigger
            fill_time = c["openTime"]
            break
        if entry_direction == "stop_above" and c["high"] >= entry_trigger:
            fill_index = i
            fill_price = entry_trigger
            fill_time = c["openTime"]
            break

    if fill_index is None:
        return {
            "ordenEjecutada": False,
            "razon": "Precio nunca tocó el trigger en el horizonte evaluado",
            "tp1Alcanzado": False,
            "tp2Alcanzado": False,
            "stopAlcanzado": False,
            "resultadoPct": 0.0,
            "resultadoUsdtPorUnidad": 0.0,
            "velasHastaResolucion": None,
        }

    tp1_hit = False
    tp2_hit = False
    stop_hit = False
    resolution_index = None
    resolution_event = None
    resolution_price = None

    for j in range(fill_index, len(candles)):
        c = candles[j]
        touched_stop = c["low"] <= stop
        touched_tp1 = c["high"] >= tp1
        touched_tp2 = c["high"] >= tp2

        if j == fill_index and entry_direction == "limit_below":
            same_candle_after_fill_low = c["low"]
            same_candle_after_fill_high = c["high"]
            touched_stop = same_candle_after_fill_low <= stop
            touched_tp1 = same_candle_after_fill_high >= tp1
            touched_tp2 = same_candle_after_fill_high >= tp2

        if touched_stop and (touched_tp1 or touched_tp2):
            stop_hit = True
            tp1_hit = touched_tp1
            tp2_hit = touched_tp2
            resolution_index = j
            resolution_event = "STOP_FIRST_AMBIGUO"
            resolution_price = stop
            break
        if touched_stop:
            stop_hit = True
            resolution_index = j
            resolution_event = "STOP"
            resolution_price = stop
            break
        if touched_tp2:
            tp1_hit = True
            tp2_hit = True
            resolution_index = j
            resolution_event = "TP2"
            resolution_price = tp2
            break
        if touched_tp1:
            tp1_hit = True
            resolution_index = j
            resolution_event = "TP1"
            resolution_price = tp1

    if resolution_event is None:
        last_close = candles[-1]["close"]
        resolution_price = last_close
        resolution_event = "ABIERTO"
        resolution_index = len(candles) - 1

    resultado_pct = round((resolution_price - fill_price) / fill_price * 100, 4)
    velas_resolucion = (
        resolution_index - fill_index if resolution_index is not None else None
    )

    return {
        "ordenEjecutada": True,
        "fillTimeMs": fill_time,
        "fillTimeIso": datetime.fromtimestamp(fill_time / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "fillPrice": fill_price,
        "tp1Alcanzado": tp1_hit,
        "tp2Alcanzado": tp2_hit,
        "stopAlcanzado": stop_hit,
        "evento": resolution_event,
        "precioResolucion": resolution_price,
        "resultadoPct": resultado_pct,
        "resultadoUsdtPorUnidad": round(resolution_price - fill_price, 4),
        "velasHastaEjecucion": fill_index,
        "velasHastaResolucion": velas_resolucion,
    }


def classify_decision(
    accion_sistema: str,
    eval_a: dict,
    eval_b: dict,
    plan_principal: dict,
) -> tuple[bool | None, str]:
    """Determina si la decisión fue acertada.

    Lógica:
    - El sistema dijo AVOID y NO entró por limit ni breakout → CORRECTA si el
      precio efectivamente cayó (no había prisa) o lateraló sin oportunidad.
    - Entró por limit y pegó TP1/TP2 → CORRECTA.
    - Entró por limit y pegó stop → INCORRECTA.
    - Entró por breakout y pegó TP → CORRECTA pero contra el plan principal.
    - Ningún escenario disparó → INDETERMINADA (esperar más velas).
    """
    a_filled = eval_a.get("ordenEjecutada", False)
    b_filled = eval_b.get("ordenEjecutada", False) if eval_b else False

    a_event = eval_a.get("evento")
    b_event = eval_b.get("evento") if eval_b else None

    if accion_sistema in ("AVOID", "WAIT", "ESPERAR_LIMIT_EN_SOPORTE"):
        if not a_filled and not b_filled:
            return None, (
                "INDETERMINADA: el sistema esperó y ningún escenario disparó en el "
                "horizonte evaluado. Decisión defensiva sin contradicción."
            )
        if a_filled and a_event in ("TP1", "TP2"):
            return True, (
                "CORRECTA: el sistema dijo esperar el limit en soporte; el limit se "
                f"ejecutó y alcanzó {a_event}. Paciencia premiada."
            )
        if a_filled and a_event in ("STOP", "STOP_FIRST_AMBIGUO"):
            return False, (
                "INCORRECTA (parcial): el limit se ejecutó pero el precio rompió el "
                "soporte y tocó stop. Riesgo bien definido aunque el setup falló."
            )
        if b_filled and b_event in ("TP1", "TP2"):
            return True, (
                "CORRECTA (escenario B): no se cumplió el pullback pero el breakout "
                f"confirmó y llegó a {b_event}. El plan alternativo capturó el move."
            )
        if b_filled and b_event in ("STOP", "STOP_FIRST_AMBIGUO"):
            return False, (
                "INCORRECTA (escenario B): el breakout se confirmó pero falló el "
                "retesteo y volvió debajo del nivel."
            )
        return None, "INDETERMINADA: revisar manualmente."

    return None, f"Acción del sistema no clasificable automáticamente: {accion_sistema}"


def evaluate_decision_file(
    path: Path, max_candles: int = 48, force: bool = False
) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))

    eval_state = data.get("evaluacionPosterior", {}).get("estado")
    if eval_state == "EVALUADA" and not force:
        return {"path": str(path), "skipped": True, "reason": "ya evaluada (usa --force)"}

    activo = data["activo"]
    symbol = activo["symbol"]
    interval = activo["interval"]
    start_ms = data["timestamp"]["epochMs"]

    if interval not in INTERVAL_MS:
        return {"path": str(path), "error": f"intervalo no soportado: {interval}"}

    interval_ms = INTERVAL_MS[interval]
    fetch_start_ms = start_ms - interval_ms
    candles = fetch_klines(symbol, interval, fetch_start_ms, limit=max_candles + 1)
    candles = [c for c in candles if c["closeTime"] >= start_ms]
    if not candles:
        return {"path": str(path), "error": "Sin velas disponibles aún (decisión muy reciente)"}

    last_candle_close_ms = candles[-1]["closeTime"]
    horizon_complete = (
        last_candle_close_ms < int(time.time() * 1000) and len(candles) >= 2
    )

    plan = data["plan"]
    principal = plan["escenarioPrincipal"]
    alternativo = plan.get("escenarioAlternativo")

    eval_a = evaluate_long_trade(
        candles=candles,
        entry_trigger=principal["compra"],
        entry_direction="limit_below",
        stop=principal["stop"],
        tp1=principal["vendeTp1"],
        tp2=principal["vendeTp2"],
    )

    eval_b = None
    if alternativo and "compraSiRompe" in alternativo:
        eval_b = evaluate_long_trade(
            candles=candles,
            entry_trigger=alternativo["compraSiRompe"],
            entry_direction="stop_above",
            stop=alternativo["stop"],
            tp1=alternativo["vendeTp1"],
            tp2=alternativo["vendeTp2"],
        )

    accion = data.get("estrategia", {}).get("decisionFinal") or data["snapshot"].get(
        "accionSistema"
    )
    acertada, leccion = classify_decision(accion, eval_a, eval_b, principal)

    precio_max = max(c["high"] for c in candles)
    precio_min = min(c["low"] for c in candles)

    closed = bool(
        eval_a.get("evento") in ("TP1", "TP2", "STOP", "STOP_FIRST_AMBIGUO")
        or (eval_b and eval_b.get("evento") in ("TP1", "TP2", "STOP", "STOP_FIRST_AMBIGUO"))
    )

    estado = "EVALUADA" if closed or horizon_complete else "PARCIAL"

    data["evaluacionPosterior"] = {
        "estado": estado,
        "fechaEvaluacion": datetime.now().astimezone().isoformat(timespec="milliseconds"),
        "horizonteVelas": len(candles),
        "intervalo": interval,
        "primeraVelaIso": datetime.fromtimestamp(candles[0]["openTime"] / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "ultimaVelaIso": datetime.fromtimestamp(candles[-1]["closeTime"] / 1000, tz=timezone.utc)
        .isoformat()
        .replace("+00:00", "Z"),
        "precioMaxPosterior": round(precio_max, 4),
        "precioMinPosterior": round(precio_min, 4),
        "escenarioA_LimitPullback": eval_a,
        "escenarioB_Breakout": eval_b,
        "decisionAcertada": acertada,
        "leccion": leccion,
    }

    return {"path": str(path), "data": data, "skipped": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evalúa decisiones guardadas en decisiones/")
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Ruta a un JSON específico (default: todos los pendientes en decisiones/)",
    )
    parser.add_argument("--max-candles", type=int, default=48)
    parser.add_argument("--force", action="store_true", help="Re-evalúa los ya cerrados")
    parser.add_argument("--dry-run", action="store_true", help="No escribe el JSON")
    args = parser.parse_args(argv)

    if args.file:
        files = [Path(args.file)]
    else:
        files = sorted(DECISIONES_DIR.glob("*.json"))

    if not files:
        print(f"No se encontraron decisiones en {DECISIONES_DIR}", file=sys.stderr)
        return 1

    summary = []
    for f in files:
        try:
            result = evaluate_decision_file(f, max_candles=args.max_candles, force=args.force)
        except Exception as e:
            summary.append({"path": str(f), "error": str(e)})
            continue

        if result.get("skipped"):
            summary.append({"path": result["path"], "skipped": True, "reason": result["reason"]})
            continue

        if result.get("error"):
            summary.append(result)
            continue

        data = result["data"]
        if not args.dry_run:
            f.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

        ev = data["evaluacionPosterior"]
        summary.append(
            {
                "path": result["path"],
                "estado": ev["estado"],
                "decisionAcertada": ev["decisionAcertada"],
                "leccion": ev["leccion"],
                "escenarioA": {
                    "ejecutada": ev["escenarioA_LimitPullback"]["ordenEjecutada"],
                    "evento": ev["escenarioA_LimitPullback"].get("evento"),
                    "resultadoPct": ev["escenarioA_LimitPullback"].get("resultadoPct"),
                },
                "escenarioB": (
                    {
                        "ejecutada": ev["escenarioB_Breakout"]["ordenEjecutada"],
                        "evento": ev["escenarioB_Breakout"].get("evento"),
                        "resultadoPct": ev["escenarioB_Breakout"].get("resultadoPct"),
                    }
                    if ev["escenarioB_Breakout"]
                    else None
                ),
            }
        )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
