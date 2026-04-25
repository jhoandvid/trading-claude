# Ajustes recomendados para mejorar la precisión del analizador de criptomonedas

## Contexto

Este documento resume los ajustes recomendados para mejorar la precisión del orquestador `crypto_analyzer`, cuyo objetivo es analizar un par de criptomonedas usando endpoints públicos de Binance y devolver:

- Datos crudos por endpoint.
- Resumen de mercado.
- Análisis técnico.
- Liquidez.
- Datos de derivados.
- Plan de trade sugerido.
- Checklist de compra.
- Recomendación final.

El código actual funciona bien como primera versión, pero tiene un problema importante: **es demasiado permisivo para generar una señal `BUY`**.

En la data analizada, el sistema devolvió `BUY` aunque existían varias señales de precaución:

- Tendencia lateral.
- Estructura lateral.
- RSI débil.
- MACD con cruce bajista.
- Precio debajo de EMA20 y EMA50.
- Flujo de trades equilibrado.
- Order book equilibrado.
- TP1 con relación riesgo/beneficio débil.

Por eso, la recomendación principal es cambiar el sistema para que no produzca únicamente `BUY`, `WAIT` o `AVOID`, sino una clasificación más precisa del setup.

---

# 1. Problema principal del sistema actual

Actualmente, el sistema convierte un checklist de condiciones básicas en una señal directa de compra.

Ejemplo actual:

```python
if score >= 75:
    action = "BUY"
    reasons.append(f"Checklist pasado al {score}%")
```

Esto es peligroso porque un checklist alto no necesariamente significa que haya una entrada fuerte.

Un activo puede tener:

- Buena liquidez.
- Spread bajo.
- Buen riesgo/beneficio hacia TP2.
- Precio lejos de resistencia.

Pero al mismo tiempo tener:

- Momentum débil.
- MACD bajista.
- Tendencia lateral.
- Precio debajo de medias móviles importantes.

En ese caso, no debería salir `BUY` como señal limpia. Debería salir algo como:

```text
BUY_PARTIAL
BUY_CONDICIONADO
WAIT_CONFIRMATION
```

---

# 2. Nueva clasificación recomendada

En lugar de usar solo:

```text
BUY / WAIT / AVOID
```

Se recomienda usar:

```text
STRONG_BUY
BUY_PARTIAL
WAIT
AVOID
```

## Significado de cada acción

| Acción | Significado |
|---|---|
| `STRONG_BUY` | Compra fuerte. Tendencia, momentum, volumen y riesgo/beneficio alineados. |
| `BUY_PARTIAL` | Compra táctica o condicionada. Hay oportunidad, pero también advertencias. |
| `WAIT` | El setup puede ser interesante, pero requiere confirmación. |
| `AVOID` | El riesgo no compensa o la estructura está en contra. |

## Uso práctico

Una salida más profesional sería:

```json
{
  "action": "BUY_PARTIAL",
  "reasons": [
    "Checklist favorable, pero con advertencias"
  ],
  "warnings": [
    "Mercado lateral",
    "MACD bajista",
    "RSI débil",
    "Precio debajo de EMA20",
    "Precio debajo de EMA50"
  ]
}
```

---

# 3. No contar tendencia lateral como favorable completa

## Problema actual

El código actual considera `LATERAL` como una condición favorable:

```python
trend in ("ALCISTA", "ALCISTA_FUERTE", "LATERAL")
```

Esto infla el score.

Una tendencia lateral no es necesariamente negativa, pero tampoco confirma compra. Debe tratarse como neutral.

## Ajuste recomendado

```python
trend = klines.get("trend")
structure = klines.get("structure", {}).get("structure")

if trend in ("ALCISTA", "ALCISTA_FUERTE") and structure in ("ALCISTA", "ALCISTA_FUERTE"):
    trend_ok = True
elif trend == "LATERAL" and structure == "LATERAL":
    trend_ok = None
else:
    trend_ok = False

add(
    "Estructura/tendencia favorable",
    trend_ok,
    f"trend={trend}, structure={structure}",
)
```

## Interpretación

| Condición | Resultado |
|---|---|
| Tendencia alcista + estructura alcista | Positivo |
| Tendencia lateral + estructura lateral | Neutral |
| Tendencia bajista o estructura bajista | Negativo |

---

# 4. Penalizar MACD bajista

## Problema actual

El MACD aparece en el resumen, pero no afecta el checklist ni la recomendación final de forma suficiente.

Esto permite que el sistema devuelva `BUY` aunque el MACD esté en `CRUCE_BAJISTA`.

## Ajuste recomendado

Agregar un check específico:

```python
macd_label = klines.get("indicators", {}).get("macdLabel")
macd_hist = klines.get("indicators", {}).get("macdHistogram")

if macd_label == "CRUCE_BAJISTA" or (macd_hist is not None and macd_hist < 0):
    macd_ok = False
elif macd_hist is not None and macd_hist > 0:
    macd_ok = True
else:
    macd_ok = None

add(
    "MACD sin presión bajista",
    macd_ok,
    f"macdLabel={macd_label}, histogram={macd_hist}",
)
```

## Reglas sugeridas

| MACD | Interpretación |
|---|---|
| Histograma positivo | Positivo |
| Cruce alcista | Positivo |
| Histograma cercano a cero | Neutral |
| Cruce bajista | Negativo |
| Histograma negativo creciente | Negativo fuerte |

---

# 5. Mejorar la lógica del RSI

## Problema actual

El código actual solo valida que el RSI no esté en sobrecompra extrema:

```python
rsi_v < 75
```

Esto es insuficiente.

Un RSI de 38 pasa el check porque no está sobrecomprado, pero eso no significa que el activo tenga fuerza compradora.

## Ajuste recomendado

```python
rsi_v = klines.get("indicators", {}).get("rsi14")

if rsi_v is not None:
    if 45 <= rsi_v <= 65:
        rsi_ok = True
    elif 35 <= rsi_v < 45:
        rsi_ok = None
    elif rsi_v < 35:
        rsi_ok = False
    elif 65 < rsi_v < 75:
        rsi_ok = None
    else:
        rsi_ok = False

    add(
        "RSI en zona saludable",
        rsi_ok,
        f"rsi14={round(rsi_v, 2)}",
    )
```

## Interpretación sugerida

| RSI | Lectura |
|---|---|
| Menor a 35 | Debilidad fuerte. Esperar confirmación. |
| 35 a 45 | Débil, posible rebote, pero no compra fuerte. |
| 45 a 65 | Zona saludable para continuación. |
| 65 a 75 | Momentum fuerte, pero riesgo de entrada tardía. |
| Mayor a 75 | Sobrecompra extrema. Evitar compra agresiva. |

---

# 6. Exigir más al volumen relativo

## Problema actual

Actualmente el código considera suficiente:

```python
relativeVolume >= 1.0
```

Eso es muy permisivo. Un volumen relativo de 1.08 o 1.10 no confirma una entrada fuerte.

## Ajuste recomendado

```python
rel_vol = klines.get("indicators", {}).get("relativeVolume")

if rel_vol is not None:
    if rel_vol >= 1.5:
        volume_ok = True
    elif rel_vol >= 1.0:
        volume_ok = None
    else:
        volume_ok = False

    add(
        "Volumen confirmando con fuerza",
        volume_ok,
        f"relativeVolume={round(rel_vol, 2)}",
    )
```

## Interpretación sugerida

| Relative Volume | Lectura |
|---|---|
| Menor a 1.0 | Volumen insuficiente. |
| 1.0 a 1.49 | Volumen aceptable, pero no confirmatorio fuerte. |
| 1.5 o más | Confirmación relevante. |
| 2.0 o más | Confirmación fuerte. |

---

# 7. Agregar filtro de EMAs

## Problema actual

El código trae EMA20, EMA50 y EMA200, pero no las usa para decidir.

Esto es un problema porque el precio puede estar debajo de EMA20 y EMA50, mostrando debilidad de corto plazo, y aun así el sistema puede devolver `BUY`.

## Ajuste recomendado

```python
price = ticker24.get("lastPrice") or plan.get("entry")
indicators = klines.get("indicators", {})

ema20 = indicators.get("ema20")
ema50 = indicators.get("ema50")
ema200 = indicators.get("ema200")

if price and ema20 and ema50 and ema200:
    if price > ema20 > ema50:
        ema_ok = True
    elif price > ema200 and price < ema20:
        ema_ok = None
    else:
        ema_ok = False

    add(
        "Precio alineado con EMAs",
        ema_ok,
        f"price={price}, ema20={ema20}, ema50={ema50}, ema200={ema200}",
    )
```

## Interpretación

| Condición | Lectura |
|---|---|
| Precio > EMA20 > EMA50 | Setup alcista de corto plazo. |
| Precio > EMA200 pero debajo de EMA20/EMA50 | Rebote táctico, no tendencia fuerte. |
| Precio < EMA200 | Precaución fuerte. |
| EMA20 < EMA50 | Momentum corto débil. |

---

# 8. Mejorar el cálculo del stop loss

## Problema actual

El stop actual se calcula así:

```python
stop = min(stop_candidates) * 0.998
```

Esto puede ser demasiado arbitrario.

Problemas posibles:

- El stop puede quedar demasiado cerca y ser barrido por ruido.
- El stop puede quedar demasiado lejos y afectar el riesgo/beneficio.
- No se diferencia entre entrada por soporte, entrada agresiva o entrada por breakout.

## Ajuste recomendado

Usar ATR y soporte juntos:

```python
if nearest_support and atr_v:
    stop_by_support = nearest_support - (0.25 * atr_v)
    stop_by_atr = spot_price - (1.5 * atr_v)
    stop = min(stop_by_support, stop_by_atr)
elif atr_v:
    stop = spot_price - (1.5 * atr_v)
elif nearest_support:
    stop = nearest_support * 0.998
else:
    stop = spot_price * 0.97
```

## Reglas recomendadas por tipo de entrada

### Entrada cerca de soporte

```python
stop = nearest_support - (0.25 * atr_v)
```

### Entrada agresiva al precio actual

```python
stop = spot_price - (1.5 * atr_v)
```

### Entrada por breakout

```python
stop = breakout_level - (0.5 * atr_v)
```

---

# 9. No usar siempre el precio actual como entrada

## Problema actual

El plan usa siempre:

```python
"entry": spot_price
```

Eso obliga al sistema a recomendar comprar al precio actual.

Pero un trader no siempre compra en el precio actual. A veces espera:

- Pullback a soporte.
- Ruptura confirmada.
- Retesteo.
- Mejor relación riesgo/beneficio.

## Ajuste recomendado

Generar varias entradas:

```python
entry_aggressive = spot_price
entry_support = nearest_support
entry_confirmation = nearest_resistance

entries = {
    "aggressive": round(entry_aggressive, 8),
    "supportPullback": round(entry_support, 8) if entry_support else None,
    "confirmationBreakout": round(entry_confirmation, 8) if entry_confirmation else None,
}
```

## Ejemplo de salida

```json
{
  "entries": {
    "aggressive": 77200.0,
    "supportPullback": 76924.62,
    "confirmationBreakout": 77725.66
  }
}
```

## Uso profesional

| Entrada | Cuándo usarla |
|---|---|
| `aggressive` | Entrada parcial, mayor riesgo. |
| `supportPullback` | Entrada ideal si el precio defiende soporte. |
| `confirmationBreakout` | Entrada más segura si rompe resistencia con volumen. |

---

# 10. Penalizar si TP1 tiene mal riesgo/beneficio

## Problema actual

El código actual usa:

```python
"meetsMinRR": (rr_tp1 or 0) >= 2 or (rr_tp2 or 0) >= 2
```

Esto permite que el trade pase si TP2 tiene buen R/R, aunque TP1 sea débil.

El problema es que si TP1 está muy cerca, puede haber rechazo antes de que el trade realmente pague el riesgo.

## Ajuste recomendado

```python
meets_min_rr = (rr_tp2 or 0) >= 2
tp1_acceptable = (rr_tp1 or 0) >= 1.2

rr_quality = {
    "tp1Acceptable": tp1_acceptable,
    "tp2Acceptable": meets_min_rr,
    "quality": "GOOD" if meets_min_rr and tp1_acceptable else "WEAK_TP1",
}
```

## Advertencia recomendada

```python
if rr_tp1 is not None and rr_tp1 < 1.2:
    warnings.append("TP1 no compensa suficientemente el riesgo")
```

---

# 11. Implementar scoring ponderado

## Problema actual

Todos los checks pesan igual.

Esto no es correcto porque no tiene el mismo peso:

- Spread aceptable.
- Liquidez alta.
- MACD bajista.
- Tendencia bajista.
- Relación riesgo/beneficio.

La tendencia, el momentum y el riesgo/beneficio deben pesar más.

## Ajuste recomendado

Modificar `add()` para aceptar peso:

```python
def add(name: str, ok: bool | None, detail: str = "", weight: float = 1.0) -> None:
    items.append({
        "check": name,
        "ok": ok,
        "detail": detail,
        "weight": weight,
    })
```

Modificar cálculo del score:

```python
earned = sum(i["weight"] for i in items if i["ok"] is True)
possible = sum(i["weight"] for i in items if i["ok"] is not None)
score_pct = round(earned / possible * 100, 1) if possible > 0 else 0
```

## Pesos sugeridos

| Check | Peso sugerido |
|---|---:|
| Tendencia / estructura | 2.0 |
| Relación riesgo/beneficio | 2.0 |
| Volumen relativo | 1.5 |
| MACD / momentum | 1.5 |
| No comprar en resistencia | 1.5 |
| RSI | 1.2 |
| EMAs | 1.5 |
| Funding / derivados | 1.0 |
| Liquidez | 1.0 |
| Spread | 0.5 |

---

# 12. Usar order book y trade flow como confirmación secundaria

## Problema actual

El sistema analiza depth, trades y aggTrades, pero estos datos pueden cambiar muy rápido.

Por eso, no deberían producir una señal principal de compra, sino confirmar o advertir.

## Función sugerida

```python
def _microstructure_signal(depth: dict, trades: dict, agg: dict) -> dict:
    score = 0
    reasons = []

    if _is_ok(depth):
        imbalance = depth.get("imbalance")
        if imbalance == "COMPRADOR_DOMINA":
            score += 1
            reasons.append("Order book comprador")
        elif imbalance == "VENDEDOR_DOMINA":
            score -= 1
            reasons.append("Order book vendedor")

    if _is_ok(trades):
        flow = trades.get("flow")
        if flow == "AGRESIVO_COMPRADOR":
            score += 1
            reasons.append("Flujo comprador reciente")
        elif flow == "AGRESIVO_VENDEDOR":
            score -= 1
            reasons.append("Flujo vendedor reciente")

    if _is_ok(agg):
        buy_aggr = agg.get("buyAggressionPct")
        if buy_aggr is not None:
            if buy_aggr >= 60:
                score += 1
                reasons.append(f"AggTrades comprador: {round(buy_aggr, 2)}%")
            elif buy_aggr <= 40:
                score -= 1
                reasons.append(f"AggTrades vendedor: {round(buy_aggr, 2)}%")

    if score >= 2:
        label = "BUY_CONFIRMATION"
    elif score <= -2:
        label = "SELL_PRESSURE"
    else:
        label = "NEUTRAL"

    return {
        "score": score,
        "label": label,
        "reasons": reasons,
    }
```

## Uso recomendado

- Si microestructura es `BUY_CONFIRMATION`, puede mejorar una entrada parcial.
- Si microestructura es `SELL_PRESSURE`, puede degradar `BUY_PARTIAL` a `WAIT`.
- Si es `NEUTRAL`, no debería afectar mucho la señal.

---

# 13. Agregar regla de señales contradictorias

## Problema actual

El sistema puede devolver `BUY` aunque haya múltiples señales mixtas.

Ejemplo:

```text
Checklist 100%
RSI débil
MACD bajista
Tendencia lateral
Precio debajo de EMA20
Precio debajo de EMA50
```

Eso debería activar una advertencia y degradar la señal.

## Ajuste recomendado

```python
bearish_warnings = 0
warnings = []

if macd_label == "CRUCE_BAJISTA":
    bearish_warnings += 1
    warnings.append("MACD bajista")

if rsi_v is not None and rsi_v < 45:
    bearish_warnings += 1
    warnings.append(f"RSI débil: {round(rsi_v, 2)}")

if price and ema20 and price < ema20:
    bearish_warnings += 1
    warnings.append("Precio debajo de EMA20")

if price and ema50 and price < ema50:
    bearish_warnings += 1
    warnings.append("Precio debajo de EMA50")

if trend == "LATERAL":
    bearish_warnings += 1
    warnings.append("Mercado lateral")

if bearish_warnings >= 3 and action == "BUY":
    action = "BUY_PARTIAL"
    reasons.append("Señales mixtas: compra solo parcial o esperar confirmación")

if bearish_warnings >= 4 and action in ("BUY", "BUY_PARTIAL"):
    action = "WAIT"
    reasons.append("Demasiadas señales contradictorias")
```

---

# 14. Versión mejorada de `_final_recommendation`

```python
def _final_recommendation(
    checklist: dict,
    klines: dict,
    funding: dict,
    plan: dict | None = None,
) -> dict:
    score = checklist["scorePct"]
    reasons: list[str] = []
    warnings: list[str] = []

    action = "WAIT"

    trend = None
    structure = None
    indicators = {}

    if _is_ok(klines):
        trend = klines.get("trend")
        structure = klines.get("structure", {}).get("structure")
        indicators = klines.get("indicators", {})

    rsi = indicators.get("rsi14")
    macd_label = indicators.get("macdLabel")
    macd_hist = indicators.get("macdHistogram")
    ema20 = indicators.get("ema20")
    ema50 = indicators.get("ema50")
    ema200 = indicators.get("ema200")

    bearish_warnings = 0

    if trend in ("BAJISTA", "BAJISTA_FUERTE"):
        bearish_warnings += 2
        warnings.append(f"Tendencia en contra: {trend}")

    if trend == "LATERAL":
        bearish_warnings += 1
        warnings.append("Mercado lateral: no es compra de tendencia")

    if macd_label == "CRUCE_BAJISTA" or (macd_hist is not None and macd_hist < 0):
        bearish_warnings += 1
        warnings.append("MACD bajista")

    if rsi is not None and rsi < 45:
        bearish_warnings += 1
        warnings.append(f"RSI débil: {round(rsi, 2)}")

    entry = plan.get("entry") if plan else None

    if entry and ema20 and entry < ema20:
        bearish_warnings += 1
        warnings.append("Precio debajo de EMA20")

    if entry and ema50 and entry < ema50:
        bearish_warnings += 1
        warnings.append("Precio debajo de EMA50")

    if entry and ema200 and entry < ema200:
        bearish_warnings += 1
        warnings.append("Precio debajo de EMA200")

    rr_tp1 = plan.get("rrTp1") if plan else None
    rr_tp2 = plan.get("rrTp2") if plan else None

    rr_ok = rr_tp2 is not None and rr_tp2 >= 2
    rr_tp1_weak = rr_tp1 is not None and rr_tp1 < 1.2

    if rr_tp1_weak:
        warnings.append("TP1 tiene relación riesgo/beneficio débil")

    if score >= 85 and bearish_warnings == 0 and rr_ok:
        action = "STRONG_BUY"
        reasons.append(f"Checklist fuerte: {score}%")
    elif score >= 75 and rr_ok and bearish_warnings <= 2:
        action = "BUY_PARTIAL"
        reasons.append(f"Checklist favorable pero con advertencias: {score}%")
    elif score >= 60 and rr_ok:
        action = "WAIT"
        reasons.append(f"Setup potencial, pero requiere confirmación: {score}%")
    else:
        action = "AVOID"
        reasons.append(f"Setup insuficiente: {score}%")

    if _is_ok(funding):
        bias = funding.get("biasLabel", "")
        if "MUY_POSITIVO" in bias and action in ("STRONG_BUY", "BUY_PARTIAL"):
            action = "WAIT"
            warnings.append("Funding muy positivo: riesgo de long squeeze")

    if bearish_warnings >= 4 and action in ("STRONG_BUY", "BUY_PARTIAL"):
        action = "WAIT"
        warnings.append("Demasiadas señales contradictorias para comprar ahora")

    failed = [i for i in checklist["items"] if i["ok"] is False]
    if failed:
        reasons.append(
            "Pendientes: " + "; ".join(f"{i['check']}" for i in failed[:5])
        )

    return {
        "action": action,
        "reasons": reasons,
        "warnings": warnings,
        "bearishWarnings": bearish_warnings,
    }
```

---

# 15. Cambio necesario en la llamada

Actualmente llamas:

```python
recommendation = _final_recommendation(checklist, klines, funding)
```

Deberías cambiarlo a:

```python
recommendation = _final_recommendation(checklist, klines, funding, plan)
```

Porque la recomendación mejorada necesita leer:

- Entrada.
- RR TP1.
- RR TP2.
- Stop.
- Distancia al objetivo.

---

# 16. Versión mejorada de `_evaluate_checklist`

Aquí hay una versión conceptual más precisa:

```python
def _evaluate_checklist(
    info: dict,
    ticker24: dict,
    klines: dict,
    depth: dict,
    plan: dict,
) -> dict:
    items: list[dict] = []

    def add(name: str, ok: bool | None, detail: str = "", weight: float = 1.0) -> None:
        items.append({
            "check": name,
            "ok": ok,
            "detail": detail,
            "weight": weight,
        })

    if _is_ok(info):
        add(
            "Símbolo válido y en TRADING",
            info.get("valid", False) and info.get("status") == "TRADING",
            f"status={info.get('status')}",
            weight=1.0,
        )

    if _is_ok(ticker24):
        add(
            "No comprar en resistencia",
            not ticker24.get("nearHighWarning"),
            f"posición rango 24h = {ticker24.get('positionInRangePct')}%",
            weight=1.5,
        )

        add(
            "Sin movimiento extremo 24h",
            ticker24.get("momentumLabel") not in ("EXTREMO_BAJISTA", "EXTREMO_ALCISTA"),
            f"momentum={ticker24.get('momentumLabel')}",
            weight=1.0,
        )

    if _is_ok(klines):
        indicators = klines.get("indicators", {})
        trend = klines.get("trend")
        structure = klines.get("structure", {}).get("structure")

        if trend in ("ALCISTA", "ALCISTA_FUERTE") and structure in ("ALCISTA", "ALCISTA_FUERTE"):
            trend_ok = True
        elif trend == "LATERAL" and structure == "LATERAL":
            trend_ok = None
        else:
            trend_ok = False

        add(
            "Estructura/tendencia favorable",
            trend_ok,
            f"trend={trend}, structure={structure}",
            weight=2.0,
        )

        rsi_v = indicators.get("rsi14")
        if rsi_v is not None:
            if 45 <= rsi_v <= 65:
                rsi_ok = True
            elif 35 <= rsi_v < 45:
                rsi_ok = None
            elif rsi_v < 35:
                rsi_ok = False
            elif 65 < rsi_v < 75:
                rsi_ok = None
            else:
                rsi_ok = False

            add(
                "RSI en zona saludable",
                rsi_ok,
                f"rsi14={round(rsi_v, 2)}",
                weight=1.2,
            )

        macd_label = indicators.get("macdLabel")
        macd_hist = indicators.get("macdHistogram")

        if macd_label == "CRUCE_BAJISTA" or (macd_hist is not None and macd_hist < 0):
            macd_ok = False
        elif macd_hist is not None and macd_hist > 0:
            macd_ok = True
        else:
            macd_ok = None

        add(
            "MACD sin presión bajista",
            macd_ok,
            f"macdLabel={macd_label}, histogram={macd_hist}",
            weight=1.5,
        )

        rel_vol = indicators.get("relativeVolume")
        if rel_vol is not None:
            if rel_vol >= 1.5:
                volume_ok = True
            elif rel_vol >= 1.0:
                volume_ok = None
            else:
                volume_ok = False

            add(
                "Volumen confirmando con fuerza",
                volume_ok,
                f"relativeVolume={round(rel_vol, 2)}",
                weight=1.5,
            )

        entry = plan.get("entry") if plan.get("available") else None
        ema20 = indicators.get("ema20")
        ema50 = indicators.get("ema50")
        ema200 = indicators.get("ema200")

        if entry and ema20 and ema50 and ema200:
            if entry > ema20 > ema50:
                ema_ok = True
            elif entry > ema200 and entry < ema20:
                ema_ok = None
            else:
                ema_ok = False

            add(
                "Precio alineado con EMAs",
                ema_ok,
                f"price={entry}, ema20={ema20}, ema50={ema50}, ema200={ema200}",
                weight=1.5,
            )

    if _is_ok(depth):
        add(
            "Liquidez suficiente",
            depth.get("liquidityScore") in ("ALTA", "MEDIA"),
            f"liquidityScore={depth.get('liquidityScore')}, spread={depth.get('spreadPct')}%",
            weight=1.0,
        )

        add(
            "Spread aceptable",
            not depth.get("wideSpreadWarning"),
            f"spreadPct={depth.get('spreadPct')}",
            weight=0.5,
        )

    if plan.get("available"):
        rr_tp1 = plan.get("rrTp1")
        rr_tp2 = plan.get("rrTp2")

        rr_ok = rr_tp2 is not None and rr_tp2 >= 2
        add(
            "Relación R/B mínima hacia TP2",
            rr_ok,
            f"rrTp1={rr_tp1}, rrTp2={rr_tp2}",
            weight=2.0,
        )

        if rr_tp1 is not None:
            add(
                "TP1 con R/B aceptable",
                rr_tp1 >= 1.2,
                f"rrTp1={rr_tp1}",
                weight=1.0,
            )

    passed = sum(1 for i in items if i["ok"] is True)
    total = len(items)

    earned_weight = sum(i["weight"] for i in items if i["ok"] is True)
    possible_weight = sum(i["weight"] for i in items if i["ok"] is not None)

    score_pct = round(earned_weight / possible_weight * 100, 1) if possible_weight > 0 else 0

    return {
        "items": items,
        "passed": passed,
        "total": total,
        "scorePct": score_pct,
        "earnedWeight": round(earned_weight, 2),
        "possibleWeight": round(possible_weight, 2),
    }
```

---

# 17. Salida esperada para una data como la analizada

Con una data como esta:

```text
Tendencia: LATERAL
Estructura: LATERAL
RSI: 38
MACD: CRUCE_BAJISTA
Precio debajo de EMA20
Precio debajo de EMA50
RR TP2: 2.76
Liquidez: ALTA
Spread: 0.0%
```

El sistema no debería devolver:

```json
{
  "action": "BUY"
}
```

Debería devolver algo más parecido a:

```json
{
  "action": "BUY_PARTIAL",
  "reasons": [
    "Checklist favorable pero con advertencias"
  ],
  "warnings": [
    "Mercado lateral: no es compra de tendencia",
    "MACD bajista",
    "RSI débil",
    "Precio debajo de EMA20",
    "Precio debajo de EMA50",
    "TP1 tiene relación riesgo/beneficio débil"
  ],
  "bearishWarnings": 5
}
```

O incluso:

```json
{
  "action": "WAIT",
  "reasons": [
    "Setup potencial, pero requiere confirmación"
  ],
  "warnings": [
    "Demasiadas señales contradictorias para comprar ahora"
  ]
}
```

---

# 18. Recomendación de arquitectura del resultado final

El JSON final debería diferenciar entre:

1. Condición del mercado.
2. Calidad del setup.
3. Tipo de entrada.
4. Gestión de riesgo.
5. Recomendación.

## Ejemplo de salida ideal

```json
{
  "marketState": {
    "trend": "LATERAL",
    "structure": "LATERAL",
    "momentum": "WEAK",
    "volatility": "NORMAL"
  },
  "setupQuality": {
    "scorePct": 72.5,
    "label": "TACTICAL_SETUP",
    "warnings": [
      "MACD bajista",
      "RSI débil",
      "Precio debajo de EMA20"
    ]
  },
  "entries": {
    "aggressive": 77200.0,
    "supportPullback": 76924.62,
    "confirmationBreakout": 77725.66
  },
  "riskManagement": {
    "stop": 76698.62,
    "tp1": 77725.66,
    "tp2": 78585.93,
    "rrTp1": 1.05,
    "rrTp2": 2.76,
    "riskPct": 0.65
  },
  "recommendation": {
    "action": "BUY_PARTIAL",
    "positionSizeSuggestion": "30% - 40% de la posición normal",
    "invalidation": "Cierre 1H debajo del stop con volumen"
  }
}
```

---

# 19. Priorización de cambios

## Prioridad alta

Aplicar primero:

```text
1. Agregar BUY_PARTIAL.
2. No contar LATERAL como positivo completo.
3. Penalizar MACD bajista.
4. Mejorar lógica del RSI.
5. Agregar EMAs al checklist.
6. Cambiar recomendación final para usar warnings.
```

## Prioridad media

Después:

```text
7. Implementar scoring ponderado.
8. Separar entradas: agresiva, soporte y confirmación.
9. Penalizar TP1 débil.
10. Mejorar cálculo del stop con ATR.
```

## Prioridad avanzada

Luego:

```text
11. Agregar microestructura como confirmación secundaria.
12. Crear clasificación de mercado: TRENDING, RANGING, BREAKOUT, REVERSAL.
13. Agregar backtesting para validar thresholds.
14. Ajustar thresholds por temporalidad: 15m, 1h, 4h, 1d.
```

---

# 20. Conclusión

El código actual está bien como primera versión, pero su principal debilidad es que trata señales neutrales como señales positivas.

El mayor cambio conceptual debe ser este:

```text
El sistema no debe responder simplemente “BUY”.
Debe responder qué tipo de compra es:
- compra fuerte,
- compra parcial,
- compra condicionada,
- espera,
- o evitar.
```

La decisión de trading debe depender de:

- Tendencia.
- Momentum.
- Volumen.
- EMAs.
- Riesgo/beneficio.
- Confirmación de derivados.
- Microestructura.
- Distancia a soporte/resistencia.
- Señales contradictorias.

La mejora más importante es pasar de un checklist simple a una **calificación ponderada del setup**.

---

# Resumen ejecutivo

Cambios recomendados:

```text
1. Crear acciones STRONG_BUY, BUY_PARTIAL, WAIT y AVOID.
2. Tratar tendencia lateral como neutral, no como favorable.
3. Penalizar MACD bajista.
4. Evaluar RSI por rangos de calidad.
5. Exigir relativeVolume mayor para confirmación fuerte.
6. Usar EMA20, EMA50 y EMA200 como filtro técnico.
7. Mejorar cálculo del stop con ATR.
8. Generar múltiples zonas de entrada.
9. Penalizar TP1 débil.
10. Usar scoring ponderado.
11. Usar order book y trades como confirmación secundaria.
12. Agregar warnings de señales contradictorias.
```

Con estos cambios, el sistema sería más preciso, más realista y más parecido a cómo evaluaría un setup un trader profesional.
