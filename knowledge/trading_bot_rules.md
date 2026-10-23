# Reglas y Arquitectura de Bots de Trading Cuantitativo

- **Origen:** Especificación de proyecto Bot-08-09
- **Nivel de Confianza:** 1.0 (Verificado)
- **Fecha de Validación:** 2026-10-22

## Estructura del Proyecto Bot-08-09
- **Ubicación:** `../Bot-08-09` (Hermano de la carpeta `IA` en Downloads).
- **Componentes clave:**
  - `main.py` / `PiBot_Terminal.pyw`: Núcleo de ejecución del bot en tiempo real.
  - `historical_data` / `historical_data_alpaca`: Registros históricos de velas y ticks.
  - `ai_models`: Modelos matemáticos y predictivos.
  - `logs`: Registro de operaciones, ejecuciones y errores.

## Reglas de Seguridad y Operación
1. **Protección de Procesos Activos:** Nunca ejecutar comandos `kill`, `taskkill` o `Stop-Process` que afecten a `main.py` o `PiBot_Terminal.pyw`.
2. **Gestión de Riesgo:** El bot aplica límite de pérdida diaria (Circuit Breaker a 2% máx) y cálculo dinámico de posición con fracción de Kelly y ATR.
3. **Persistencia:** Las velas históricas se almacenan en bases de datos SQLite con modo WAL (`PRAGMA journal_mode=WAL;`) para evitar bloqueos entre hilos de lectura y escritura.
