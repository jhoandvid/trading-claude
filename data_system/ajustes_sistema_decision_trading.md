# Ajustes recomendados para mejorar el sistema de decisión de compra

## Contexto

El sistema actual ya detecta setups útiles, como `MEAN_REVERSION`, calcula soportes, resistencias, EMAs, RSI, MACD, ATR, flujo de trades, order book, funding y riesgo/beneficio. Sin embargo, todavía necesita separar mejor dos conceptos distintos:

1. **Detectar una oportunidad técnica.**
2. **Autorizar una entrada real de compra.**

Un setup puede existir, pero eso no significa que se deba comprar inmediatamente. El objetivo de estos ajustes es convertir el analizador en un sistema más operable, capaz de decir:

```text
No compres ahora.
Compra solo si ocurre A, B y C.
Invalida si ocurre X.
Reduce tamaño si ocurre Y.
No operes si Z sigue presente.
```

---

# 1. Separar `setupScore` de `executionScore`

## Problema actual

El sistema puede mostrar un `setupQuality.scorePct` alto, por ejemplo `91.1%`, pero terminar con una recomendación `AVOID`. Esto indica que el score mide la calidad del setup, pero no necesariamente la calidad de la entrada actual.

## Ajuste recomendado

Separar el análisis en dos scores:

```json
{
  "setupScore": 91.1,
  "executionScore": 35.0,
  "decision": "AVOID"
}
```

## Definición

### `setupScore`

Mide si existe una idea válida de mercado.

Ejemplos:

- Mean reversion.
- Breakout.
- Pullback.
- Continuation.
- Reversal.

### `executionScore`

Mide si se puede entrar ahora.

Debe evaluar:

- Volumen relativo.
- Microestructura.
- Flujo comprador/vendedor.
- R:B hacia TP1 y TP2.
- Confirmación de vela.
- Estado de la vela actual.
- Proximidad a soporte/resistencia.
- Spread, liquidez y slippage.

## Regla sugerida

```text
Si setupScore es alto pero executionScore es bajo, la decisión debe ser WAIT o AVOID.
```

---

# 2. Agregar reglas bloqueantes explícitas

## Problema actual

Algunas señales deberían bloquear automáticamente una compra, aunque el setup parezca atractivo.

Por ejemplo:

```text
relativeVolume bajo + flujo vendedor + microestructura bajista = no comprar
```

## Ajuste recomendado

Agregar una sección `blockingRules`.

```json
{
  "blockingRules": [
    {
      "rule": "LOW_VOLUME_NO_BUYERS",
      "triggered": true,
      "severity": "HIGH",
      "reason": "relativeVolume 0.13x + microestructura bajista"
    },
    {
      "rule": "BAD_TP1_RR",
      "triggered": true,
      "severity": "HIGH",
      "reason": "rrTp1 0.78 < 1.2"
    }
  ]
}
```

## Reglas bloqueantes sugeridas

### `LOW_VOLUME_NO_BUYERS`

```text
Si relativeVolume < 0.5
Y tradeFlow = AGRESIVO_VENDEDOR
Y microstructure.consensusBias = BEARISH
entonces action máximo = WAIT o AVOID.
```

### `BAD_TP1_RR`

```text
Si rrTp1 < 1.2
entonces no permitir BUY ni STRONG_BUY.
```

### `BEARISH_MICROSTRUCTURE`

```text
Si tradesBuyerAggPct < 45
Y aggBuyerAggPct < 45
Y depthImbalance = VENDEDOR_DOMINA
entonces action máximo = WAIT o AVOID.
```

### `UNCONFIRMED_CANDLE`

```text
Si la señal depende de indicadores de 1h
Y la vela de 1h no ha cerrado
entonces no permitir STRONG_BUY.
```

### `PRICE_TOO_FAR_FROM_SUPPORT`

```text
Para mean reversion:
Si distancia al soporte > 0.75% o > 1 ATR parcial,
entonces no comprar agresivo.
```

---

# 3. Agregar confirmación de vela

## Problema actual

El sistema analiza indicadores, pero no describe suficientemente la vela actual ni las últimas velas.

Para una compra, no basta con estar cerca de soporte. Se necesita evidencia de rechazo, absorción o recuperación.

## Ajuste recomendado

Agregar una sección `candleConfirmation`.

```json
{
  "candleConfirmation": {
    "lastCandleType": "HAMMER",
    "closePositionInCandlePct": 72,
    "bodyPctOfRange": 35,
    "upperWickPct": 20,
    "lowerWickPct": 45,
    "rejectionAtSupport": true,
    "bullishCloseAbovePreviousHigh": false,
    "confirmationScore": 68
  }
}
```

## Señales útiles para compra

- Mecha inferior fuerte.
- Cierre en la parte alta de la vela.
- Vela verde después de barrer mínimos.
- Rechazo claro en soporte.
- Envolvente alcista.
- Recuperación de nivel perdido.
- Cierre por encima del máximo de la vela anterior.

## Regla sugerida para mean reversion

```text
Para permitir BUY en mean reversion, exigir al menos una confirmación:
- rejectionAtSupport = true
- closePositionInCandlePct >= 60
- lowerWickPct >= 35
- bullishCloseAbovePreviousHigh = true
```

---

# 4. Medir fuerza real de soportes y resistencias

## Problema actual

El sistema lista soportes y resistencias, pero no indica qué tan fuertes son.

No todos los soportes tienen el mismo valor. Un soporte reciente con varias reacciones y alto volumen es más relevante que un nivel viejo o apenas tocado.

## Ajuste recomendado

Agregar `supportStrength` y `resistanceStrength`.

```json
{
  "supportStrength": [
    {
      "price": 76926.02,
      "touches": 4,
      "lastTouchedHoursAgo": 6,
      "volumeAtLevel": "HIGH",
      "reactionAvgPct": 0.42,
      "brokenRecently": false,
      "liquiditySweepObserved": true,
      "strengthScore": 82
    }
  ]
}
```

## Campos recomendados

- `touches`: número de reacciones históricas.
- `lastTouchedHoursAgo`: recencia del nivel.
- `volumeAtLevel`: volumen negociado cerca del nivel.
- `reactionAvgPct`: reacción promedio después de tocar el nivel.
- `brokenRecently`: si fue roto recientemente.
- `liquiditySweepObserved`: si hubo barrida de liquidez.
- `strengthScore`: puntuación final del nivel.

## Regla sugerida

```text
Para comprar por mean reversion,
el soporte objetivo debería tener strengthScore >= 70.
```

---

# 5. Agregar estructura menor o microtendencia

## Problema actual

El sistema marca `trend: LATERAL` y `structure: LATERAL`, pero eso puede ser demasiado general.

Dentro de una estructura lateral de 1h puede existir una microestructura bajista de corto plazo.

## Ajuste recomendado

Agregar una sección `microTrend`.

```json
{
  "microTrend": {
    "last3SwingHighs": "LOWER_HIGHS",
    "last3SwingLows": "LOWER_LOWS",
    "minorStructure": "BEARISH",
    "structureShift": false,
    "choch": false,
    "bos": false
  }
}
```

## Definiciones

- `LOWER_HIGHS`: máximos descendentes.
- `LOWER_LOWS`: mínimos descendentes.
- `CHOCH`: cambio de carácter.
- `BOS`: ruptura de estructura.
- `structureShift`: cambio estructural confirmado.

## Regla sugerida

```text
Para compra agresiva:
No permitir BUY si minorStructure = BEARISH y choch = false.
```

Para una entrada más sólida:

```text
Primero: barrido de mínimo.
Luego: recuperación del nivel.
Después: CHoCH alcista o ruptura de microestructura.
```

---

# 6. Detectar si la vela del timeframe principal está cerrada

## Problema actual

Si el análisis usa intervalo `1h`, la última vela puede estar abierta. RSI, MACD, volumen y forma de vela pueden cambiar antes del cierre.

## Ajuste recomendado

Agregar `candleStatus`.

```json
{
  "candleStatus": {
    "timeframe": "1h",
    "isClosed": false,
    "minutesToClose": 36,
    "signalRequiresClose": true,
    "reliabilityPenalty": 20
  }
}
```

## Regla sugerida

```text
Si signalRequiresClose = true
Y isClosed = false
entonces no permitir STRONG_BUY.
```

También se puede degradar:

```text
BUY -> BUY_PARTIAL
BUY_PARTIAL -> WAIT
WAIT -> AVOID, si además hay señales bajistas.
```

---

# 7. Agregar contexto multi-timeframe

## Problema actual

Una señal en 1h puede verse atractiva, pero si 4h o 1D están en resistencia o caída fuerte, la compra es más riesgosa.

## Ajuste recomendado

Agregar análisis de varios marcos temporales.

```json
{
  "timeframes": {
    "15m": {
      "trend": "BEARISH",
      "rsi": 38,
      "structure": "LOWER_LOWS",
      "priceVsEma200Pct": -0.4
    },
    "1h": {
      "trend": "LATERAL",
      "rsi": 42,
      "structure": "LATERAL",
      "priceVsEma200Pct": 0.9
    },
    "4h": {
      "trend": "LATERAL",
      "rsi": 48,
      "structure": "RANGE",
      "priceVsEma200Pct": 1.7
    },
    "1d": {
      "majorTrend": "BULLISH",
      "nearMajorResistance": false,
      "nearMajorSupport": true
    }
  }
}
```

## Regla sugerida para compra

```text
Para BUY en 1h:
- 15m no debe estar en caída fuerte.
- 1h debe estar en zona válida.
- 4h no debe mostrar rechazo fuerte.
- 1D no debe estar en resistencia mayor inmediata.
```

---

# 8. Agregar `historicalEdge` mediante backtesting

## Problema actual

El sistema puede sonar lógico, pero sin backtesting no se sabe si realmente tiene ventaja estadística.

## Ajuste recomendado

Guardar señales históricas y medir resultados.

```json
{
  "historicalEdge": {
    "similarSetups": 842,
    "winRateToTp1": 54.8,
    "winRateToTp2": 31.2,
    "avgReturnR": 0.18,
    "medianReturnR": 0.07,
    "maxDrawdownR": -3.6,
    "profitFactor": 1.21,
    "sampleQuality": "MEDIUM"
  }
}
```

## Métricas mínimas

- `similarSetups`: número de casos similares.
- `winRateToTp1`: porcentaje que alcanza TP1 antes del stop.
- `winRateToTp2`: porcentaje que alcanza TP2 antes del stop.
- `avgReturnR`: retorno promedio en múltiplos de riesgo.
- `medianReturnR`: retorno mediano en múltiplos de riesgo.
- `maxDrawdownR`: peor racha o caída histórica.
- `profitFactor`: ganancias brutas / pérdidas brutas.
- `sampleQuality`: calidad de la muestra.

## Regla sugerida

```text
No permitir STRONG_BUY si historicalEdge.profitFactor < 1.3
o similarSetups < 100.
```

---

# 9. Ajustar R:B por comisiones y slippage

## Problema actual

El sistema calcula R:B bruto, pero el resultado real depende de comisiones y deslizamiento.

Un `rrTp1` de `0.78` puede ser todavía peor después de costos.

## Ajuste recomendado

Agregar `costAdjustedRR`.

```json
{
  "costAdjustedRR": {
    "feePctRoundTrip": 0.2,
    "estimatedSlippagePct": 0.03,
    "rrTp1Raw": 0.78,
    "rrTp1Net": 0.61,
    "rrTp2Raw": 2.58,
    "rrTp2Net": 2.32
  }
}
```

## Regla sugerida

```text
Para permitir BUY:
rrTp1Net >= 1.0
y rrTp2Net >= 2.0.
```

Para permitir STRONG_BUY:

```text
rrTp1Net >= 1.2
y rrTp2Net >= 2.2.
```

---

# 10. Convertir entradas en plan condicional

## Problema actual

El sistema muestra entradas como:

```json
{
  "entries": {
    "aggressive": 77350.5,
    "supportPullback": 76926.02,
    "breakoutConfirmation": 77835.8
  }
}
```

Eso es útil, pero falta convertirlo en escenarios operables.

## Ajuste recomendado

Agregar `tradePlan`.

```json
{
  "tradePlan": {
    "bestEntryType": "WAIT_FOR_PULLBACK_OR_CONFIRMATION",
    "scenarioA": {
      "name": "Comprar pullback en soporte",
      "entryZone": [76920, 77020],
      "requires": [
        "rejection candle",
        "buyerAggressionPct > 55",
        "relativeVolume > 0.7",
        "supportStrengthScore >= 70"
      ],
      "stop": 76870,
      "tp1": 77725,
      "tp2": 78585,
      "invalidIf": "1h close below stop with volume"
    },
    "scenarioB": {
      "name": "Comprar confirmación breakout",
      "entryAbove": 77835,
      "requires": [
        "1h close above resistance",
        "volume expansion",
        "successful retest",
        "microstructure not bearish"
      ],
      "invalidIf": "breakout fails back below 77725"
    }
  }
}
```

## Beneficio

El sistema deja de decir solamente `BUY`, `WAIT` o `AVOID`, y empieza a entregar una guía accionable.

---

# 11. Agregar penalización por contradicciones

## Problema actual

Algunas señales pueden ser alcistas y bajistas al mismo tiempo. El sistema debe explicar esas contradicciones y resolverlas.

## Ajuste recomendado

Agregar `signalConflicts`.

```json
{
  "signalConflicts": [
    {
      "bullishSignal": "price near support",
      "bearishSignal": "seller-dominated microstructure",
      "resolution": "wait for confirmation"
    },
    {
      "bullishSignal": "price above EMA200",
      "bearishSignal": "price below EMA20 and EMA50",
      "resolution": "trend not strong enough for aggressive buy"
    }
  ]
}
```

## Regla sugerida

```text
Si hay 2 o más conflictos críticos sin resolución alcista,
no permitir BUY.
```

---

# 12. Detectar régimen de mercado

## Problema actual

No todos los setups funcionan igual en todos los regímenes de mercado.

Mean reversion funciona mejor en rangos. Breakout funciona mejor con expansión de volatilidad. Pullback funciona mejor en tendencia fuerte.

## Ajuste recomendado

Agregar `marketRegime`.

```json
{
  "marketRegime": {
    "regime": "LOW_VOL_RANGE",
    "volatility": "LOW",
    "trendStrength": "WEAK",
    "meanReversionFriendly": true,
    "breakoutFriendly": false,
    "continuationFriendly": false
  }
}
```

## Regímenes sugeridos

| Régimen | Setup preferido |
|---|---|
| `LOW_VOL_RANGE` | Mean reversion |
| `HIGH_VOL_RANGE` | Mean reversion con tamaño reducido |
| `TRENDING_UP` | Pullback / continuation |
| `TRENDING_DOWN` | Evitar longs o buscar shorts |
| `VOL_EXPANSION` | Breakout con confirmación |
| `CHOP_EXTREME` | No operar |

## Regla sugerida

```text
Solo habilitar setups compatibles con el régimen de mercado actual.
```

---

# 13. Mejorar la jerarquía de decisión

## Decisión recomendada

La decisión final debería seguir esta jerarquía:

```text
1. Validar símbolo y liquidez.
2. Detectar régimen de mercado.
3. Detectar setup.
4. Calcular setupScore.
5. Evaluar reglas bloqueantes.
6. Calcular executionScore.
7. Validar R:B neto.
8. Validar microestructura.
9. Validar vela cerrada o aplicar penalización.
10. Revisar backtesting de setups similares.
11. Generar tradePlan condicional.
12. Emitir acción final.
```

## Pseudocódigo sugerido

```ts
if (!symbolValid || liquidityScore === 'BAJA') {
  return 'AVOID';
}

const setup = detectSetup(marketData);
const setupScore = calculateSetupScore(setup, marketData);

const blockingRules = evaluateBlockingRules(marketData, setup);
if (blockingRules.some(rule => rule.severity === 'CRITICAL' && rule.triggered)) {
  return 'AVOID';
}

const executionScore = calculateExecutionScore({
  volume,
  microstructure,
  candleConfirmation,
  riskReward,
  supportStrength,
  candleStatus,
  marketRegime
});

if (executionScore < 40) {
  return 'AVOID';
}

if (executionScore < 65) {
  return 'WAIT';
}

if (setup.confidence !== 'HIGH' && action === 'STRONG_BUY') {
  return 'BUY_PARTIAL';
}

if (costAdjustedRR.rrTp1Net < 1.0) {
  return 'WAIT';
}

return finalAction;
```

---

# 14. Acciones finales sugeridas

## `AVOID`

Usar cuando:

- Hay microestructura bajista.
- Volumen bajo.
- R:B insuficiente.
- Vela sin confirmar.
- Soporte débil.
- Setup contra régimen de mercado.

## `WAIT`

Usar cuando:

- Hay setup válido, pero falta confirmación.
- El precio está en zona interesante, pero sin compradores claros.
- R:B mejora si se espera mejor entrada.

## `BUY_PARTIAL`

Usar cuando:

- Setup válido.
- Confirmación parcial.
- Riesgo controlado.
- Microestructura neutral o ligeramente alcista.
- Volumen aceptable, pero no excelente.

## `BUY`

Usar cuando:

- Setup válido.
- Execution score alto.
- Microestructura favorable.
- Volumen suficiente.
- R:B neto aceptable.
- Confirmación de vela o estructura menor.

## `STRONG_BUY`

Usar solo cuando:

- `setup.confidence = HIGH`.
- `executionScore >= 80`.
- `relativeVolume >= 1.0`.
- `microstructure.consensusBias = BULLISH`.
- `rrTp1Net >= 1.2`.
- `rrTp2Net >= 2.2`.
- No hay reglas bloqueantes activas.
- La vela del timeframe principal cerró confirmando la señal.

---

# 15. Estructura JSON final recomendada

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "generatedAt": 1777148282352,
  "marketState": {},
  "marketRegime": {},
  "setup": {},
  "setupScore": {
    "scorePct": 91.1,
    "label": "HIGH"
  },
  "executionScore": {
    "scorePct": 35.0,
    "label": "LOW",
    "mainWeaknesses": [
      "LOW_VOLUME",
      "BEARISH_MICROSTRUCTURE",
      "BAD_TP1_RR"
    ]
  },
  "blockingRules": [],
  "candleStatus": {},
  "candleConfirmation": {},
  "microTrend": {},
  "supportStrength": [],
  "resistanceStrength": [],
  "costAdjustedRR": {},
  "historicalEdge": {},
  "signalConflicts": [],
  "tradePlan": {},
  "recommendation": {
    "action": "AVOID",
    "reasonSummary": "Setup válido, pero ejecución débil por volumen bajo, microestructura bajista y R:B insuficiente hacia TP1.",
    "positionSizeSuggestion": "0% — no operar",
    "nextAction": "Esperar pullback confirmado en soporte o breakout con volumen."
  }
}
```

---

# 16. Prioridad de implementación

## Prioridad alta

1. Separar `setupScore` y `executionScore`.
2. Agregar reglas bloqueantes.
3. Agregar R:B neto con comisiones y slippage.
4. Agregar plan condicional de entrada.
5. Penalizar vela no cerrada.

## Prioridad media

6. Confirmación de vela.
7. Fuerza de soportes y resistencias.
8. Microtendencia / estructura menor.
9. Conflictos entre señales.
10. Régimen de mercado.

## Prioridad avanzada

11. Backtesting e `historicalEdge`.
12. Optimización por tipo de setup.
13. Ajuste dinámico de pesos según régimen de mercado.
14. Modelo de probabilidad basado en señales históricas.

---

# Resumen final

El sistema actual ya es útil para evitar compras malas, pero necesita mejores filtros para confirmar compras buenas.

La mejora más importante es esta:

```text
No mezclar calidad del setup con calidad de entrada.
```

Un setup puede ser bueno, pero una entrada puede ser mala.

Por eso, el sistema debería pasar de:

```text
Setup bueno = comprar
```

A:

```text
Setup bueno + ejecución buena + riesgo/beneficio neto bueno + confirmación = comprar
```

