# Binance URLs públicas para consultar información de criptomonedas

> Objetivo: centralizar URLs y contratos útiles para obtener precios, históricos, datos de mercado, comportamiento, patrones, noticias, research y reportes relacionados con cualquier criptomoneda.
>
> Fecha de referencia: 2026-04-25.
>
> Nota importante:
> - Los endpoints oficiales y soportados son los documentados por Binance en `developers.binance.com` y repositorios oficiales.
> - Los endpoints `https://www.binance.com/bapi/...` son usados por la web/app de Binance, pero no deben tratarse como API pública estable. Pueden cambiar, romperse, requerir headers/cookies, bloquear por región o dejar de responder sin aviso.

---

## 1. Bases oficiales recomendadas

### Spot REST público

```text
https://data-api.binance.vision
```

Uso recomendado para datos públicos de mercado Spot sin autenticación.

También existe:

```text
https://api.binance.com
```

Pero para market data público Binance recomienda `data-api.binance.vision`.

### Futures USD-M público

```text
https://fapi.binance.com
```

### Futures COIN-M público

```text
https://dapi.binance.com
```

### WebSocket Spot

```text
wss://stream.binance.com:9443/ws
wss://stream.binance.com:9443/stream
```

### Datos históricos descargables

```text
https://data.binance.vision
```

---

## 2. Contrato base para consultar cualquier criptomoneda

Para trabajar con cualquier cripto, normalmente necesitas:

```json
{
  "baseAsset": "BTC",
  "quoteAsset": "USDT",
  "symbol": "BTCUSDT",
  "interval": "1h",
  "startTime": 1704067200000,
  "endTime": 1735689600000,
  "limit": 500
}
```

### Campos clave

| Campo | Tipo | Ejemplo | Uso |
|---|---:|---|---|
| `baseAsset` | string | `BTC` | Activo principal |
| `quoteAsset` | string | `USDT` | Moneda de cotización |
| `symbol` | string | `BTCUSDT` | Par de trading |
| `interval` | string | `1m`, `5m`, `1h`, `1d` | Temporalidad de velas |
| `startTime` | number | `1704067200000` | Timestamp inicial en ms |
| `endTime` | number | `1735689600000` | Timestamp final en ms |
| `limit` | number | `100`, `500`, `1000` | Número máximo de registros |

### Intervalos comunes

```text
1s
1m
3m
5m
15m
30m
1h
2h
4h
6h
8h
12h
1d
3d
1w
1M
```

---

## 3. Descubrir símbolos disponibles

Antes de consultar una cripto, valida que el símbolo exista.

### Exchange info general

```http
GET https://data-api.binance.vision/api/v3/exchangeInfo
```

### Exchange info de un símbolo

```http
GET https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT
```

### Request

```json
{
  "symbol": "BTCUSDT"
}
```

### Response resumida

```json
{
  "timezone": "UTC",
  "serverTime": 1710000000000,
  "symbols": [
    {
      "symbol": "BTCUSDT",
      "status": "TRADING",
      "baseAsset": "BTC",
      "quoteAsset": "USDT",
      "orderTypes": ["LIMIT", "MARKET"],
      "isSpotTradingAllowed": true,
      "filters": [
        {
          "filterType": "PRICE_FILTER",
          "minPrice": "0.01000000",
          "maxPrice": "1000000.00000000",
          "tickSize": "0.01000000"
        },
        {
          "filterType": "LOT_SIZE",
          "minQty": "0.00001000",
          "maxQty": "9000.00000000",
          "stepSize": "0.00001000"
        }
      ]
    }
  ]
}
```

### Uso

Sirve para:
- Validar si un par existe.
- Saber si está en estado `TRADING`.
- Obtener precisión de precio y cantidad.
- Construir dinámicamente pares como `ETHUSDT`, `SOLUSDT`, `BNBUSDT`.

---

## 4. Precios actuales

### Precio actual de un símbolo

```http
GET https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT
```

### Response

```json
{
  "symbol": "BTCUSDT",
  "price": "65000.00000000"
}
```

### Precio actual de todos los símbolos

```http
GET https://data-api.binance.vision/api/v3/ticker/price
```

### Response

```json
[
  {
    "symbol": "BTCUSDT",
    "price": "65000.00000000"
  },
  {
    "symbol": "ETHUSDT",
    "price": "3200.00000000"
  }
]
```

---

## 5. Precio promedio

### URL

```http
GET https://data-api.binance.vision/api/v3/avgPrice?symbol=BTCUSDT
```

### Response

```json
{
  "mins": 5,
  "price": "65000.00000000",
  "closeTime": 1710000000000
}
```

### Uso

Útil para:
- Obtener referencia suavizada.
- Evitar usar únicamente el último trade.
- Comparar precio actual contra promedio reciente.

---

## 6. Estadísticas 24h

### URL

```http
GET https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT
```

### Response resumida

```json
{
  "symbol": "BTCUSDT",
  "priceChange": "1200.00000000",
  "priceChangePercent": "1.85",
  "weightedAvgPrice": "64500.00000000",
  "prevClosePrice": "63800.00000000",
  "lastPrice": "65000.00000000",
  "bidPrice": "64999.99000000",
  "askPrice": "65000.00000000",
  "openPrice": "63800.00000000",
  "highPrice": "65500.00000000",
  "lowPrice": "63000.00000000",
  "volume": "25000.00000000",
  "quoteVolume": "1600000000.00000000",
  "openTime": 1710000000000,
  "closeTime": 1710086400000,
  "count": 1500000
}
```

### Uso

Sirve para:
- Variación porcentual.
- Volumen.
- Rango high/low.
- Momentum.
- Ranking de mayores subidas y caídas.

---

## 7. Estadísticas por ventana móvil

### URL

```http
GET https://data-api.binance.vision/api/v3/ticker?symbol=BTCUSDT&windowSize=1h
```

### Parámetros

```json
{
  "symbol": "BTCUSDT",
  "windowSize": "1h"
}
```

### Ventanas soportadas comunes

```text
1m
5m
15m
30m
1h
4h
12h
1d
3d
7d
```

### Uso

Útil para:
- Comportamiento por ventana.
- Momentum reciente.
- Scanners de mercado por ventanas menores a 24h.

---

## 8. Velas históricas / Klines

### URL básica

```http
GET https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=500
```

### URL con rango

```http
GET https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1d&startTime=1704067200000&endTime=1735689600000
```

### Request

```json
{
  "symbol": "BTCUSDT",
  "interval": "1h",
  "startTime": 1704067200000,
  "endTime": 1735689600000,
  "limit": 500
}
```

### Response

```json
[
  [
    1704067200000,
    "42280.00000000",
    "43100.00000000",
    "42000.00000000",
    "42850.00000000",
    "1250.12345000",
    1704070799999,
    "53500000.00000000",
    120000,
    "620.00000000",
    "26500000.00000000",
    "0"
  ]
]
```

### Mapeo de campos

| Índice | Campo |
|---:|---|
| 0 | `openTime` |
| 1 | `open` |
| 2 | `high` |
| 3 | `low` |
| 4 | `close` |
| 5 | `volume` |
| 6 | `closeTime` |
| 7 | `quoteAssetVolume` |
| 8 | `numberOfTrades` |
| 9 | `takerBuyBaseAssetVolume` |
| 10 | `takerBuyQuoteAssetVolume` |
| 11 | `ignore` |

### Uso para patrones

Con `klines` puedes calcular:
- RSI.
- MACD.
- EMA/SMA.
- Bollinger Bands.
- Soportes y resistencias.
- Rupturas.
- Cruces de medias.
- Patrones de velas.
- Volatilidad.
- Retornos.
- Tendencia.
- Volumen relativo.

---

## 9. Order book / profundidad de mercado

### URL

```http
GET https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=100
```

### Request

```json
{
  "symbol": "BTCUSDT",
  "limit": 100
}
```

### Response

```json
{
  "lastUpdateId": 123456789,
  "bids": [
    ["64999.99000000", "0.50000000"]
  ],
  "asks": [
    ["65000.00000000", "0.30000000"]
  ]
}
```

### Uso

Sirve para:
- Spread bid/ask.
- Liquidez.
- Profundidad.
- Presión compradora/vendedora.
- Detección de muros de compra/venta.

---

## 10. Trades recientes

### URL

```http
GET https://data-api.binance.vision/api/v3/trades?symbol=BTCUSDT&limit=100
```

### Response

```json
[
  {
    "id": 28457,
    "price": "65000.00000000",
    "qty": "0.01000000",
    "quoteQty": "650.00000000",
    "time": 1710000000000,
    "isBuyerMaker": true,
    "isBestMatch": true
  }
]
```

### Uso

Sirve para:
- Flujo reciente de trades.
- Presión de mercado.
- Detección de agresividad compradora/vendedora.

---

## 11. Aggregate trades

### URL

```http
GET https://data-api.binance.vision/api/v3/aggTrades?symbol=BTCUSDT&limit=500
```

### URL con rango temporal

```http
GET https://data-api.binance.vision/api/v3/aggTrades?symbol=BTCUSDT&startTime=1704067200000&endTime=1704153600000
```

### Response

```json
[
  {
    "a": 26129,
    "p": "65000.00000000",
    "q": "0.01000000",
    "f": 27781,
    "l": 27781,
    "T": 1710000000000,
    "m": true,
    "M": true
  }
]
```

### Mapeo

| Campo | Significado |
|---|---|
| `a` | Aggregate trade ID |
| `p` | Price |
| `q` | Quantity |
| `f` | First trade ID |
| `l` | Last trade ID |
| `T` | Timestamp |
| `m` | Buyer was maker |
| `M` | Best price match |

---

## 12. Book ticker

### URL

```http
GET https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol=BTCUSDT
```

### Response

```json
{
  "symbol": "BTCUSDT",
  "bidPrice": "64999.99000000",
  "bidQty": "0.50000000",
  "askPrice": "65000.00000000",
  "askQty": "0.30000000"
}
```

### Uso

Sirve para:
- Mejor bid.
- Mejor ask.
- Spread inmediato.
- Señales de liquidez muy rápidas.

---

## 13. WebSockets públicos para tiempo real

### Trade stream

```text
wss://stream.binance.com:9443/ws/btcusdt@trade
```

### Kline stream

```text
wss://stream.binance.com:9443/ws/btcusdt@kline_1m
```

### Mini ticker

```text
wss://stream.binance.com:9443/ws/btcusdt@miniTicker
```

### Ticker 24h

```text
wss://stream.binance.com:9443/ws/btcusdt@ticker
```

### Book ticker

```text
wss://stream.binance.com:9443/ws/btcusdt@bookTicker
```

### Depth stream

```text
wss://stream.binance.com:9443/ws/btcusdt@depth
```

### Combined stream

```text
wss://stream.binance.com:9443/stream?streams=btcusdt@ticker/ethusdt@ticker/solusdt@ticker
```

---

## 14. Futures USD-M públicos

### Precio actual

```http
GET https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT
```

### Ticker 24h

```http
GET https://fapi.binance.com/fapi/v1/ticker/24hr?symbol=BTCUSDT
```

### Klines

```http
GET https://fapi.binance.com/fapi/v1/klines?symbol=BTCUSDT&interval=1h&limit=500
```

### Open interest

```http
GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT
```

### Funding rate histórico

```http
GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=100
```

### Premium index

```http
GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
```

### Uso

Sirve para:
- Sesgo de apalancamiento.
- Funding positivo/negativo.
- Open interest.
- Diferencia spot vs perpetual.
- Lectura de mercado de derivados.

---

## 15. Históricos descargables desde Binance Data

### Portal

```text
https://data.binance.vision
```

### Spot daily klines

```text
https://data.binance.vision/?prefix=data/spot/daily/klines/BTCUSDT/1h/
```

### Spot monthly klines

```text
https://data.binance.vision/?prefix=data/spot/monthly/klines/BTCUSDT/1d/
```

### Futures USD-M monthly klines

```text
https://data.binance.vision/?prefix=data/futures/um/monthly/klines/BTCUSDT/1h/
```

### Futures USD-M daily klines

```text
https://data.binance.vision/?prefix=data/futures/um/daily/klines/BTCUSDT/1h/
```

### Uso

Útil para:
- Backtesting.
- Modelos de ML.
- Descargas masivas.
- Evitar rate limits del REST API.

---

## 16. Research, análisis y reportes públicos

### Binance Research - análisis

```text
https://www.binance.com/en/research/analysis
```

### Binance Research - project reports

```text
https://www.binance.com/en/research/project-reports
```

### Binance Research general

```text
https://research.binance.com/
```

### Binance Blog

```text
https://www.binance.com/en/blog
```

### Binance Announcements

```text
https://www.binance.com/en/support/announcement
```

### Binance News

```text
https://www.binance.com/en/news
```

### Binance Square

```text
https://www.binance.com/en/square
```

### Binance Academy

```text
https://academy.binance.com/
```

### Uso

Sirven para:
- Noticias.
- Análisis de mercado.
- Reportes de tokens.
- Explicaciones educativas.
- Contexto fundamental.
- Anuncios de listados, delistings, staking, launchpool, etc.

---

## 17. Endpoint BAPI de AI Token Report que compartiste

### URL

```http
POST https://www.binance.com/bapi/bigdata/v3/friendly/bigdata/search/ai-report/report
```

### Payload que compartiste

```json
{
  "lang": "en",
  "token": "BTC",
  "symbol": "BTCUSDT",
  "product": "web-spot",
  "timestamp": "1777144758794",
  "quoteToken": "",
  "version": "v4",
  "translateToken": null
}
```

### Contrato probable del request

```json
{
  "lang": "en",
  "token": "BTC",
  "symbol": "BTCUSDT",
  "product": "web-spot",
  "timestamp": "1777144758794",
  "quoteToken": "",
  "version": "v4",
  "translateToken": null
}
```

### Campos

| Campo | Tipo | Ejemplo | Descripción |
|---|---:|---|---|
| `lang` | string | `en` | Idioma del reporte |
| `token` | string | `BTC` | Token base |
| `symbol` | string | `BTCUSDT` | Par de trading |
| `product` | string | `web-spot` | Producto origen |
| `timestamp` | string/number | `1777144758794` | Timestamp enviado por el front |
| `quoteToken` | string | `USDT` o vacío | Token de cotización |
| `version` | string | `v4` | Versión del contrato del reporte |
| `translateToken` | string/null | `null` | Token traducido si aplica |

### Ejemplo para ETH

```json
{
  "lang": "en",
  "token": "ETH",
  "symbol": "ETHUSDT",
  "product": "web-spot",
  "timestamp": "1777144758794",
  "quoteToken": "",
  "version": "v4",
  "translateToken": null
}
```

### Ejemplo con `curl`

```bash
curl -X POST "https://www.binance.com/bapi/bigdata/v3/friendly/bigdata/search/ai-report/report" \
  -H "Content-Type: application/json" \
  -H "Clienttype: web" \
  -H "Lang: en" \
  --data '{
    "lang": "en",
    "token": "BTC",
    "symbol": "BTCUSDT",
    "product": "web-spot",
    "timestamp": "1777144758794",
    "quoteToken": "",
    "version": "v4",
    "translateToken": null
  }'
```

### Advertencia sobre BAPI

Este endpoint puede ser útil para obtener reportes enriquecidos de una cripto, pero:
- No es un endpoint oficial documentado para integradores.
- Puede cambiar el contrato sin aviso.
- Puede requerir headers, cookies, región o sesión según el caso.
- Puede devolver errores aunque antes funcionara.
- No es recomendable usarlo como única fuente en producción.
- Úsalo como fuente auxiliar, no como dependencia crítica.

---

## 18. Endpoints BAPI no oficiales para noticias/anuncios

Binance no garantiza una API pública oficial para noticias/anuncios web. Aun así, históricamente se han usado rutas `bapi` de la web.

### Announcements / notices

```http
GET https://www.binance.com/bapi/composite/v1/public/market/notice/get?page=1&rows=20
```

### Posible contrato

```json
{
  "page": 1,
  "rows": 20
}
```

### Posible uso

- Últimos anuncios.
- Listados.
- Mantenimientos.
- Cambios de productos.
- Campañas.

### Advertencia

Trátalo como no oficial. Para producción, usa:
- Página pública de announcements.
- Scraper controlado.
- RSS si Binance lo ofrece para la sección.
- Proveedor externo de noticias cripto.
- Cache interno para no depender de llamadas frecuentes.

---

## 19. Flujo recomendado para consultar información de cualquier criptomoneda

### Entrada

```json
{
  "token": "BTC",
  "quoteAsset": "USDT",
  "interval": "1h",
  "limit": 500
}
```

### Paso 1: construir símbolo

```text
symbol = token + quoteAsset
BTC + USDT = BTCUSDT
```

### Paso 2: validar símbolo

```http
GET https://data-api.binance.vision/api/v3/exchangeInfo?symbol=BTCUSDT
```

### Paso 3: precio actual

```http
GET https://data-api.binance.vision/api/v3/ticker/price?symbol=BTCUSDT
```

### Paso 4: comportamiento 24h

```http
GET https://data-api.binance.vision/api/v3/ticker/24hr?symbol=BTCUSDT
```

### Paso 5: histórico

```http
GET https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=500
```

### Paso 6: liquidez

```http
GET https://data-api.binance.vision/api/v3/depth?symbol=BTCUSDT&limit=100
```

### Paso 7: trades

```http
GET https://data-api.binance.vision/api/v3/aggTrades?symbol=BTCUSDT&limit=500
```

### Paso 8: derivados, si aplica

```http
GET https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT
GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=100
GET https://fapi.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT
```

### Paso 9: noticias y análisis

```text
https://www.binance.com/en/research/analysis
https://www.binance.com/en/support/announcement
https://www.binance.com/en/news
https://www.binance.com/en/blog
https://academy.binance.com/
```

### Paso 10: AI report, si decides usar BAPI no oficial

```http
POST https://www.binance.com/bapi/bigdata/v3/friendly/bigdata/search/ai-report/report
```

---

## 20. Contrato interno recomendado para normalizar respuestas

Puedes convertir todas las fuentes en una respuesta común:

```json
{
  "token": "BTC",
  "symbol": "BTCUSDT",
  "quoteAsset": "USDT",
  "market": {
    "price": "65000.00000000",
    "priceChangePercent24h": "1.85",
    "high24h": "65500.00000000",
    "low24h": "63000.00000000",
    "volume24h": "25000.00000000",
    "quoteVolume24h": "1600000000.00000000"
  },
  "technical": {
    "interval": "1h",
    "candles": [],
    "rsi": null,
    "macd": null,
    "trend": null,
    "supportLevels": [],
    "resistanceLevels": []
  },
  "liquidity": {
    "bid": "64999.99000000",
    "ask": "65000.00000000",
    "spread": "0.01000000",
    "orderBook": {
      "bids": [],
      "asks": []
    }
  },
  "derivatives": {
    "openInterest": null,
    "fundingRate": null,
    "markPrice": null,
    "indexPrice": null
  },
  "news": [],
  "research": [],
  "aiReport": null,
  "sources": []
}
```

---

## 21. Fuentes recomendadas por tipo de información

| Necesidad | Fuente recomendada | Estabilidad |
|---|---|---|
| Precio actual | `/api/v3/ticker/price` | Alta |
| Variación 24h | `/api/v3/ticker/24hr` | Alta |
| Históricos | `/api/v3/klines` o `data.binance.vision` | Alta |
| Trades | `/api/v3/trades`, `/api/v3/aggTrades` | Alta |
| Liquidez | `/api/v3/depth`, `/api/v3/ticker/bookTicker` | Alta |
| Tiempo real | WebSocket streams | Alta |
| Futures | `/fapi/v1/...` | Alta |
| Funding/Open Interest | `/fapi/v1/fundingRate`, `/fapi/v1/openInterest` | Alta |
| Research | Binance Research web | Media |
| Noticias | Binance News / Blog / Announcements | Media |
| AI Report | `/bapi/bigdata/.../ai-report/report` | Baja / no oficial |
| Announcements vía BAPI | `/bapi/composite/.../notice/get` | Baja / no oficial |

---

## 22. Recomendación de arquitectura

Para un sistema robusto:

1. Usa endpoints oficiales REST para mercado.
2. Usa WebSocket para tiempo real.
3. Usa `data.binance.vision` para backtesting o históricos grandes.
4. Usa Binance Research/News/Announcements como fuentes web, no como API contractual.
5. Usa BAPI solo como fuente auxiliar.
6. Cachea respuestas de noticias/research.
7. Registra `source`, `timestamp`, `url` y `rawPayload` por cada consulta.
8. Nunca mezcles datos spot y futures sin marcar el mercado.
9. Valida siempre `symbol` con `exchangeInfo`.
10. Maneja rate limits, timeouts, errores 4xx/5xx y cambios de contrato.

---

## 23. Ejemplo de función conceptual

```ts
type CryptoInfoRequest = {
  token: string;
  quoteAsset?: string;
  interval?: string;
  limit?: number;
};

type CryptoInfoResponse = {
  token: string;
  symbol: string;
  price: unknown;
  ticker24h: unknown;
  klines: unknown[];
  orderBook: unknown;
  aggTrades: unknown[];
  futures?: {
    openInterest?: unknown;
    fundingRate?: unknown;
    premiumIndex?: unknown;
  };
  researchUrls: string[];
  newsUrls: string[];
  aiReport?: unknown;
};
```

---

## 24. URLs rápidas con placeholder

Reemplaza `{SYMBOL}` por `BTCUSDT`, `ETHUSDT`, `SOLUSDT`, etc.

```text
https://data-api.binance.vision/api/v3/exchangeInfo?symbol={SYMBOL}
https://data-api.binance.vision/api/v3/ticker/price?symbol={SYMBOL}
https://data-api.binance.vision/api/v3/avgPrice?symbol={SYMBOL}
https://data-api.binance.vision/api/v3/ticker/24hr?symbol={SYMBOL}
https://data-api.binance.vision/api/v3/ticker?symbol={SYMBOL}&windowSize=1h
https://data-api.binance.vision/api/v3/klines?symbol={SYMBOL}&interval=1h&limit=500
https://data-api.binance.vision/api/v3/depth?symbol={SYMBOL}&limit=100
https://data-api.binance.vision/api/v3/trades?symbol={SYMBOL}&limit=100
https://data-api.binance.vision/api/v3/aggTrades?symbol={SYMBOL}&limit=500
https://data-api.binance.vision/api/v3/ticker/bookTicker?symbol={SYMBOL}

https://fapi.binance.com/fapi/v1/ticker/price?symbol={SYMBOL}
https://fapi.binance.com/fapi/v1/ticker/24hr?symbol={SYMBOL}
https://fapi.binance.com/fapi/v1/klines?symbol={SYMBOL}&interval=1h&limit=500
https://fapi.binance.com/fapi/v1/openInterest?symbol={SYMBOL}
https://fapi.binance.com/fapi/v1/fundingRate?symbol={SYMBOL}&limit=100
https://fapi.binance.com/fapi/v1/premiumIndex?symbol={SYMBOL}

wss://stream.binance.com:9443/ws/{symbol_lower}@ticker
wss://stream.binance.com:9443/ws/{symbol_lower}@trade
wss://stream.binance.com:9443/ws/{symbol_lower}@kline_1m
wss://stream.binance.com:9443/ws/{symbol_lower}@depth
wss://stream.binance.com:9443/ws/{symbol_lower}@bookTicker
```

Ejemplo con BTC:

```text
https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=500
wss://stream.binance.com:9443/ws/btcusdt@ticker
```
