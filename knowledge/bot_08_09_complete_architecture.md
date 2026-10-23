# Arquitectura y Especificación Técnica Completa de Bot-08-09

Este documento describe la arquitectura, estrategias, filtros e integración del bot de trading de opciones binarias y análisis de mercado ubicado en `Bot-08-09`.

---

## 1. Arquitectura de Escaneo y Análisis Multi-Temporal (MTF)
El bot ejecuta un ciclo de análisis continuo (por defecto cada 10 segundos):
- **Escaneo Multi-Par:** Analiza pares de divisas OTC configurados en `config.json` (ej: `EURUSD_otc`, `GBPUSD_otc`, `USDJPY_otc`).
- **Escaneo Multi-Temporal (MTF):** Recorre temporalidades secuenciales (`60s` para M1, `300s` para M5, `900s` para M15).
- **Descarga de Datos en Tiempo Real:** Extrae hasta 400 velas eliminando duplicados y ordenándolas en DataFrames de pandas.
- **Cálculo Técnico Vectorizado:**
  - Medias Móviles: `SMA_200`, `EMA_20`, `EMA_50`.
  - Osciladores: `RSI` (14), `Stochastic` (14, 3, 3) con líneas `Stoch_K` y `Stoch_D`, y `MACD` con línea de señal.
  - Volatilidad: `ATR` (Average True Range).
- **Patrones de Velas Detectados:** Doji, Martillo (Hammer), Estrella Fugaz (Shooting Star), Envolvente Alcista/Bajista (Engulfing), Morning Star y Evening Star.
- **Patrones Chartistas:** Dobles Techos, Dobles Suelos y Triángulos de compresión mediante extremos relativos.

---

## 2. Las 4 Estrategias de Trading Core

### A. Estocástico + SMA200 (`StrategyStochastic`)
- **Tipo:** Tendencia (`TREND`).
- **Regla:** Busca giros a favor de la tendencia macro.
  - Alcista: Precio > `SMA_200` y `EMA_20` > `EMA_50`.
  - Bajista: Precio < `SMA_200` y `EMA_20` < `EMA_50`.
- **Filtros Clave:**
  - Crossover en Extremos: Compra si `Stoch_K < 20` cruzando al alza. Venta si `Stoch_K > 80` cruzando a la baja.
  - Filtro Cruce Tardío: Límite de 30 para compras y 70 para ventas.
  - Filtro Vela Agotadora: Cuerpo de vela menor al 60% del `ATR`.
  - Zona RSI: Entre 40 y 70 en compras; entre 30 y 60 en ventas.

### B. Cambio de Estructura - MSS (`StrategyStructure`)
- **Tipo:** Reversión (`REVERSION`).
- **Lógica:** Detecta roturas del Neckline en Dobles Techos o Dobles Suelos.
- **Filtros Clave:**
  - Ruptura fresca en la vela actual.
  - Distancia estricta menor a `0.25 * ATR` respecto al cuello para evitar entradas tardías.
  - Confirmación de cruce de histograma MACD en las últimas 3 velas.

### C. Patrones de Continuación (`StrategyContinuation`)
- **Tipo:** Tendencia (`TREND`).
- **Lógica:** Breakout de zonas de compresión (triángulos de máximos decrecientes y mínimos crecientes).
- **Filtros Clave:**
  - Breakout mínimo de `0.25 * ATR` sobre el fractal de soporte/resistencia.
  - Límite máximo de `0.45 * ATR` para no entrar en rupturas agotadas.

### D. Fibonacci Retracement 61.8% (`StrategyFibonacci`)
- **Tipo:** Tendencia (`TREND`).
- **Lógica:** Rebote en el 61.8% de retroceso del impulso reciente.
- **Filtros Clave:** Tolerancia de ±2.5% del nivel y giro confirmado con vela de rechazo (Martillo/Envolvente) y sobreventa/sobrecompra estocástica.

---

## 3. Capas de Gestión de Riesgo (Risk Management)
1. **Lock de Concurrencia:** Máximo 1 operación activa simultáneamente en toda la cuenta.
2. **Stop Loss y Take Profit Diario:** Límite monetario configurable (`daily_stop_loss`, `daily_take_profit`). Al tocarse, el bot entra en pausa preventiva hasta el día siguiente.
3. **Circuit Breaker por Racha:** Si una estrategia suma 3 fallos seguidos, se desactiva en memoria.
4. **Modalidades de Capital:** `fixed` (monto fijo), `compound` (porcentaje de capital), `martingale` (multiplicador acotado por `martingale_max_steps`).
5. **Filtro de Régimen de Mercado:** Bloqueo en `SIDEWAYS` (lateral) y `VOLATILE`.
6. **Protección de Procesos en Ejecución:** Los procesos `main.py`, `paper_bot.py` y `PiBot_Terminal.pyw` son vitales y nunca deben ser terminados abruptamente.
