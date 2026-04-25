# Evaluador de Decisiones de Trading

Sistema para **registrar** una decisión de trading y, después, **medir si fue acertada** comparándola con lo que realmente hizo el precio en Binance.

Tiene dos piezas:

1. **Generación de la decisión** — cuando preguntas algo como "¿compro ETH?", el `crypto_analyzer` responde con un plan (compra, vende, stop). El plan se guarda en un JSON dentro de `decisiones/`.
2. **Evaluación posterior** — `evaluador_decisiones.py` lee esos JSON, trae las velas que pasaron desde el momento de la decisión y simula qué habría ocurrido si hubieras ejecutado el plan exacto.

El objetivo final es **medir tu tasa de acierto** y entender qué tipo de setups funcionan mejor en tu mercado.

---

## Estructura de carpetas

```
trading/
├── analisis/
│   ├── crypto_analyzer.py          ← genera la decisión
│   └── evaluador_decisiones.py     ← evalúa la decisión a posteriori
├── decisiones/
│   └── YYYY-MM-DD_TOKEN_INTERVAL_SETUP.json   ← un archivo por decisión
└── evaluador.md                    ← este documento
```

---

## Comando 1: Generar una decisión

### Qué hace
Analiza un token usando los 18 endpoints públicos de Binance y produce un veredicto operativo (`STRONG_BUY` / `BUY_PARTIAL` / `WAIT` / `AVOID`) junto con dos planes de entrada concretos.

### Comando

```bash
cd "/media/david-rojas/Nuevo vol/Proyectos/trading"
python3 -m analisis.crypto_analyzer ETH --no-raw
```

### Flags importantes

| Flag | Para qué sirve | Default | Cuándo usarla |
|---|---|---|---|
| `--no-raw` | Quita los datos crudos de los 18 endpoints. JSON pasa de ~14KB a ~7KB. | (incluye raw) | **Siempre úsala** salvo que necesites depurar los datos crudos. |
| `--interval 1h` | Marco temporal de análisis. Acepta `1m`, `5m`, `15m`, `30m`, `1h`, `4h`, `1d`. | `1h` | `15m` para scalping, `1h` para day-trading, `4h` para swing, `1d` para posición. |
| `--quote USDT` | Moneda contra la que cotiza. | `USDT` | Para pares contra BTC (`--quote BTC`) o BUSD. |
| `--fee-pct 0.1` | Comisión total de la operación (round-trip, en %). | `0.2` | Si eres VIP de Binance con menor comisión. Afecta el R:B neto. |
| `--out archivo.json` | Guarda el output en un archivo. | (stdout) | **No la uses** con esta skill: bloquea la lectura del JSON. |

### Ejemplo

```bash
# Análisis de ETH en 4h para swing trading
python3 -m analisis.crypto_analyzer ETH --interval 4h --no-raw

# Análisis de SOL contra BTC (par no-USDT)
python3 -m analisis.crypto_analyzer SOL --quote BTC --no-raw

# Trader con comisión VIP
python3 -m analisis.crypto_analyzer BTC --fee-pct 0.1 --no-raw
```

### Qué hago yo (Claude) con el output

Recibo el JSON, lo interpreto como un trader senior y construyo un archivo en `decisiones/` con esta estructura:

- `timestamp` (ISO + epoch ms + tz)
- `activo` (token, quote, symbol, intervalo)
- `snapshot` del estado del mercado (precio, RSI, volumen, trends en 1h/4h/1d)
- `estrategia` (tipo de setup, decisión final, razonamiento)
- `plan.escenarioPrincipal` (limit en soporte: compra, TPs, stop)
- `plan.escenarioAlternativo` (breakout: compraSiRompe, TPs, stop)
- `bloqueosActivos` (reglas que generaron el AVOID/WAIT)
- `nivelesClave` (soportes y resistencias ponderados)
- `evaluacionPosterior` (vacío, espera al evaluador)

---

## Comando 2: Evaluar decisiones guardadas

### Qué hace
Recorre los JSON en `decisiones/`, trae las velas posteriores de Binance y simula los dos escenarios:

- **Escenario A (limit en soporte)** → marca como ejecutada cuando alguna vela posterior toca o perfora el precio de compra (`low <= compra`). Después busca qué se tocó primero: stop, TP1 o TP2.
- **Escenario B (breakout)** → marca como ejecutada cuando alguna vela posterior rompe el nivel hacia arriba (`high >= compraSiRompe`). Misma lógica de resolución.

Si en una misma vela tocó stop **y** TP, asume el peor caso (`STOP_FIRST_AMBIGUO`) — Binance no expone el orden intra-vela.

### Comando base

```bash
cd "/media/david-rojas/Nuevo vol/Proyectos/trading"
python3 -m analisis.evaluador_decisiones
```

Sin argumentos: evalúa **todos** los JSONs pendientes en `decisiones/`, escribe el resultado en cada archivo y muestra un resumen.

### Flags

| Flag | Para qué sirve | Default | Cuándo usarla |
|---|---|---|---|
| `--file <ruta>` | Evalúa un JSON específico, no todos. | (todos) | Para revalorar manualmente una decisión sin tocar las demás. |
| `--max-candles N` | Cuántas velas hacia adelante traer de Binance. | `48` | Más velas = horizonte más largo. Para 1h: 48 = 2 días, 96 = 4 días, 168 = 1 semana. |
| `--force` | Re-evalúa también las decisiones que ya cerraron (`estado: EVALUADA`). | (no) | Útil si cambiaste la lógica del clasificador y quieres recalcular todo. |
| `--dry-run` | NO escribe los JSON, solo muestra el resumen en consola. | (escribe) | Para probar antes de comprometer cambios al disco. |

### Ejemplos concretos

```bash
# Evalúa todos los pendientes (default 48 velas hacia adelante)
python3 -m analisis.evaluador_decisiones

# Evalúa solo la decisión de ETH del 25 de abril
python3 -m analisis.evaluador_decisiones \
  --file decisiones/2026-04-25_ETH_1h_RANGE_PLAY.json

# Mira 1 semana adelante en lugar de 2 días
python3 -m analisis.evaluador_decisiones --max-candles 168

# Recalcular TODAS las decisiones (incluso las cerradas) sin escribir
python3 -m analisis.evaluador_decisiones --force --dry-run

# Recalcular y guardar
python3 -m analisis.evaluador_decisiones --force
```

### Qué imprime

Un JSON en stdout con el resumen de cada decisión evaluada. Ejemplo:

```json
[
  {
    "path": "decisiones/2026-04-25_ETH_1h_RANGE_PLAY.json",
    "estado": "PARCIAL",
    "decisionAcertada": null,
    "leccion": "INDETERMINADA: el sistema esperó y ningún escenario disparó.",
    "escenarioA": {
      "ejecutada": false,
      "evento": null,
      "resultadoPct": 0.0
    },
    "escenarioB": {
      "ejecutada": false,
      "evento": null,
      "resultadoPct": 0.0
    }
  }
]
```

Y dentro del JSON de la decisión, llena el campo `evaluacionPosterior` con el detalle completo.

---

## Diccionario de campos del `evaluacionPosterior`

Cuando corres el evaluador, este bloque se llena así:

| Campo | Significado |
|---|---|
| `estado` | `PENDIENTE` (sin evaluar), `PARCIAL` (aún no resuelve), `EVALUADA` (terminó). |
| `fechaEvaluacion` | Cuándo corrió el evaluador (ISO con tz local). |
| `horizonteVelas` | Cuántas velas se trajeron de Binance. |
| `intervalo` | Marco temporal usado (debe coincidir con la decisión). |
| `primeraVelaIso` / `ultimaVelaIso` | Rango temporal cubierto. |
| `precioMaxPosterior` / `precioMinPosterior` | Máximo y mínimo absoluto del precio durante el horizonte. |
| `escenarioA_LimitPullback` | Resultado del escenario A. Ver tabla siguiente. |
| `escenarioB_Breakout` | Resultado del escenario B. Misma estructura. |
| `decisionAcertada` | `true` / `false` / `null`. |
| `leccion` | Frase con la conclusión operativa. |

Cada `escenarioX` contiene:

| Campo | Significado |
|---|---|
| `ordenEjecutada` | `true` si el trigger se tocó en el horizonte. |
| `fillTimeMs` / `fillTimeIso` | Cuándo se llenó la orden. |
| `fillPrice` | Precio al que se ejecutó (= trigger). |
| `tp1Alcanzado` / `tp2Alcanzado` / `stopAlcanzado` | Booleanos. |
| `evento` | Cuál de los tres tocó primero. Valores posibles abajo. |
| `precioResolucion` | Precio donde el trade cerró (TP o stop) o último cierre si sigue abierto. |
| `resultadoPct` | Ganancia/pérdida en % desde fill hasta resolución (sin descontar comisiones). |
| `resultadoUsdtPorUnidad` | Ganancia/pérdida absoluta por cada unidad del activo. |
| `velasHastaEjecucion` | Cuántas velas tardó en llenarse el limit/breakout. |
| `velasHastaResolucion` | Cuántas velas desde el fill hasta TP/stop. |

### Eventos posibles (`evento`)

| Valor | Qué significa |
|---|---|
| `TP1` | Tocó el primer take profit. Salida parcial (50%). Trade ganador. |
| `TP2` | Tocó el segundo take profit. Salida total. Trade ganador grande. |
| `STOP` | Tocó el stop loss antes que cualquier TP. Trade perdedor (controlado). |
| `STOP_FIRST_AMBIGUO` | En la misma vela tocó stop **y** TP. Asumimos stop primero (peor caso). |
| `ABIERTO` | Se llenó pero ni TP ni stop tocados todavía. Trade vivo. |
| `null` | No se ejecutó nunca el trigger en el horizonte evaluado. |

### Veredictos posibles (`decisionAcertada`)

| Valor | Lección típica |
|---|---|
| `true` | El sistema esperó (limit o breakout), se ejecutó y pegó TP. **Paciencia premiada.** |
| `false` | Se ejecutó pero pegó stop. Setup falló, riesgo bien definido. |
| `null` | El sistema dijo esperar y nada disparó. **No hay contradicción aún** — corre el evaluador más tarde con `--max-candles` mayor. |

---

## Workflow completo de uso

### Día 0 — Tomas la decisión

```bash
# Pregunta a Claude: "analiza ETH y dime cuándo comprar"
# Claude corre crypto_analyzer y guarda decisiones/YYYY-MM-DD_ETH_...json
```

### Día 0 al 2 — El mercado se mueve

Tú no haces nada. Las velas se acumulan en Binance.

### Día 2 (o cuando quieras revisar)

```bash
cd "/media/david-rojas/Nuevo vol/Proyectos/trading"
python3 -m analisis.evaluador_decisiones
```

Ves en stdout el resumen. Abres el JSON de la decisión y ves `evaluacionPosterior` lleno.

### Día 7 — Análisis de patrones

Después de tener varias decisiones evaluadas, puedes preguntar a Claude cosas como:

- *"¿Qué % de mis decisiones AVOID terminaron siendo correctas?"*
- *"¿En qué setups tipo el escenario A se ejecuta más?"*
- *"¿Qué token tiene mejor tasa de acierto?"*

Claude lee los JSON y agrega la información.

---

## Casos de uso comunes

### "Solo quiero ver qué pasó sin tocar nada"

```bash
python3 -m analisis.evaluador_decisiones --dry-run
```

### "Una decisión vieja sigue como PARCIAL, quiero ver más velas"

```bash
python3 -m analisis.evaluador_decisiones \
  --file decisiones/2026-04-20_BTC_1h_BREAKOUT.json \
  --max-candles 240 \
  --force
```

(`--force` porque la marca de "ya evaluada" puede saltarla si está en `EVALUADA`.)

### "Cambié la lógica del clasificador y quiero recalcular todo"

```bash
python3 -m analisis.evaluador_decisiones --force
```

### "Agregar evaluación automática cada N horas"

Pídeselo a Claude:
> *"Programa un agente que corra `evaluador_decisiones` cada 6 horas."*

Claude usa `/schedule` para crear una rutina cron en la nube.

---

## Errores comunes y cómo resolverlos

| Error | Causa | Solución |
|---|---|---|
| `Sin velas disponibles aún (decisión muy reciente)` | La decisión se tomó hace menos de un intervalo (ej. <1h en 1h). | Espera al menos un intervalo y vuelve a correr. |
| `intervalo no soportado: Xh` | El campo `activo.interval` del JSON tiene un valor que no está en la tabla. | Edita el JSON o ajusta `INTERVAL_MS` en el evaluador. |
| `HTTP 451 al consultar ...` | Binance bloquea la región. | Usa una VPN o cambia `SPOT_BASE` a otra réplica oficial. |
| `decisionAcertada: null` permanente | Ningún trigger se tocó en el horizonte. | Aumenta `--max-candles` o acepta que la decisión defensiva fue la correcta. |

---

## Anti-patrones (no hacer)

1. **Mover el archivo JSON de `decisiones/`** — el evaluador lo busca ahí.
2. **Editar a mano el `evaluacionPosterior`** — se sobreescribe la próxima corrida.
3. **Cambiar el `epochMs` del timestamp** — el evaluador usa eso para saber desde dónde traer velas. Si lo modificas, arruinas la evaluación.
4. **Correr el evaluador inmediatamente después de la decisión** — necesita al menos 2-3 velas posteriores para que algo ocurra. Para 1h, espera 2-3 horas mínimo.
5. **Asumir que `decisionAcertada: null` es un fallo** — significa "indeterminada todavía", no "incorrecta". Es el estado normal mientras el plan no se ejecute.
