# Reglas Maestras de Trading, Gestión de Riesgo y Operaciones Financieras

Este documento establece los principios de gestión de riesgo, análisis cuantitativo y mitigación de fallos en el ecosistema de trading automatizado.

---

## 1. Principio Fundamental: Preservación de Capital
- **Máxima pérdida por operación:** Nunca arriesgar más del 1% al 2% del balance total por trade en operativas de tipo `compound`.
- **Drawdown Máximo Diario:** El `daily_stop_loss` debe detener todas las actividades de trading una vez alcanzado el 5% de caída máxima de la cuenta en el día.
- **Protección contra Overtrading:** La activación del Lock de Concurrencia impide operaciones cruzadas o solapadas.

---

## 2. Detección de Regímenes de Mercado
- **Tendencia Fuerte (`TRENDING`):**
  - Identificada por alineación de medias móviles (`EMA_20 > EMA_50 > SMA_200`) y pendiente positiva persistente.
  - Se operan retrocesos a medias o rupturas con volumen.
- **Rango o Consolidación (`SIDEWAYS`):**
  - Identificado por compresión de Bollinger Bands, ATR reducido y cruces erráticos de medias móviles.
  - Regla: No operar breakouts ni continuaciones; se activa el bloqueo de estrategias tendenciales.
- **Volatilidad Extrema (`VOLATILE`):**
  - Spikes de velas con wicks largos y ATR superior a 2.5 veces la media móvil de volatilidad.
  - Bloqueo total preventivo por riesgo de slippage y falsos quiebres.

---

## 3. Protocolo de Fallas y Recuperación
- **Desconexión de Websocket o API:**
  - Si la conexión con el broker o proveedor de datos se interrumpe, el sistema debe reintentar con backoff exponencial (1s, 2s, 4s, 8s, hasta 30s) sin generar órdenes ciegas.
- **Cancelación Preventiva de Tareas:**
  - En caso de excepción no controlada en el loop de trading, los procesos deben escribir el log de error en `logs/crash.log` y salvaguardar el estado en memoria antes de reintentar.
