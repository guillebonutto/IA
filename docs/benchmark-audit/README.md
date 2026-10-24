# Auditoría Técnica y Protocolo de Reproducibilidad de Benchmarks: AURA CORE

Este documento reúne la auditoría técnica completa del rendimiento de inferencia local sobre **Qwen 2.5 Coder 3B Instruct (Q4_K_M)** en un procesador **AMD Ryzen 5 2400G** bajo **Windows 10**.

---

## 1. Perfil del Hardware y Entorno de Ejecución

* **Procesador (CPU)**: AMD Ryzen 5 2400G with Radeon Vega Graphics (Arquitectura Zen 1).
  * Núcleos físicos: 4.
  * Hilos lógicos (SMT): 8.
  * Extensiones vectoriales: AVX2, FMA3, BMI2 (sin AVX-512 / sin AVX-VNNI).
  * Caché L3: 4 MB compartido.
* **Memoria RAM**: 32 GB DDR4 (Dual Channel, ancho de banda físico real ~22-25 GB/s).
* **Gráfica Integrada (iGPU)**: Radeon RX Vega 11 (2 GB asignados compartidos; sin aceleración CUDA).
* **Sistema Operativo**: Windows 10 Pro (10.0.19045).
* **Motor de Inferencia**: `llama.cpp` nativo para Windows (C++ bare metal).
  * Build: `b11719-5aeac37a3`.
  * Backend activo: `ggml-cpu-haswell.dll` (instrucciones AVX2 nativas) + `libomp.dll` (OpenMP multithread).
* **Modelo Evaluado**: `models/qwen2.5-coder-3b-instruct-q4_k_m.gguf`
  * Parámetros: 3.397.103.616 (3.40 B).
  * Tamaño del archivo: 2.098.976.768 bytes (~1.95 GiB).
  * Vocabulario BPE: 151.936 tokens.

---

## 2. Scripts de Auditoría Disponibles

Todos los scripts utilizan resolución dinámica de rutas relativas al repositorio, evitando rutas absolutas personales:

| Script | Propósito | Método de Inferencia | Estado |
| :--- | :--- | :--- | :--- |
| [`audit_prompt_ingestion.py`](audit_prompt_ingestion.py) | Barrido controlado de ingesta de prompts (256 a 4096 tokens). | Directo por C++ con `llama-bench.exe` en JSON. | Ejecutado y validado. |
| [`benchmark_protocol.py`](benchmark_protocol.py) | Comparación de variables a 8 hilos (Flash Attention, formatos KV y contexto). | Servidor HTTP `llama-server.exe` en puerto 8082. | Ejecutado y validado. |
| [`test_real_workload.py`](test_real_workload.py) | Medición de 4 cargas reales con métricas separadas (prefill, TTFT real SSE, gen t/s, HTTP total). | Servidor HTTP `llama-server.exe` en puerto 8089 (streaming SSE). | Ejecutado y validado. |
| [`test_context_generation.py`](test_context_generation.py) | Benchmark de generación manteniendo `-c 8192` constante y variando contexto previo (256 a 4096 tok). | Servidor HTTP `llama-server.exe` en puerto 8083. | **Diseñado (pruebas estáticas aprobadas; purga de slots y benchmark pendientes de validación en ejecución)**. |
| [`verify_tokenizer.py`](verify_tokenizer.py) | Comprobación reproducible del tokenizador (archivos crudos vs ChatML completo; bytes vs tokens). | Dual: endpoint `/tokenize` HTTP y `llama-tokenize.exe`. | Ejecutado y validado. |
| [`audit_ingestion_results.json`](audit_ingestion_results.json) | Persistencia con separación estricta entre `raw_samples` y `summary_statistics`. | Salida estructurada de `audit_prompt_ingestion.py`. | Validado. |

---

## 3. Separación Rigurosa de Métricas y Auditoría del Protocolo

Para evitar distorsiones metodológicas, se definen y separan cuatro métricas distintas:

```
[Cliente HTTP envía petición]
       │
       ├─► 1. Latencia de red loopback + cola del servidor + tokenización ChatML
       │
       ├─► 2. Tiempo interno de prefill (prompt_ms): cálculo bare-metal de llama_decode en CPU
       │
[Primer evento SSE recibido por cliente] ──► REGISTRO DE: TTFT Real SSE (client_ttft_s)
       │
       ├─► 3. Decodificación autoregresiva (predicted_ms): cálculo por token generado
       │
[Último evento SSE recibido ([DONE])]   ──► REGISTRO DE: Tiempo Total HTTP (total_elapsed)
```

### A. Tiempo Interno de Prefill (`prompt_ms`)
* **Definición**: Tiempo exacto en milisegundos que el motor C++ GGML dedica a procesar los vectores del prompt en CPU.
* **Origen**: Reportado directamente por `llama.cpp` en el campo `timings.prompt_ms`.
* **Uso correcto**: Permite calcular la velocidad intrínseca de prefill:
  $$\text{prompt\_tps} = \frac{\text{prompt\_n}}{\text{prompt\_ms} / 1000}$$

### B. TTFT Real del Cliente (`client_ttft_sse_s`)
* **Definición**: Tiempo de reloj de pared (*wall-clock*) transcurrido desde el despacho del socket HTTP hasta la recepción del primer fragmento de contenido mediante streaming Server-Sent Events (SSE).
* **Alcance**: Incorpora el overhead de serialización, encolado, tokenización de la plantilla ChatML, el prefill del modelo y la transmisión TCP loopback. Es la métrica que refleja la experiencia real del usuario o agente.
* **Regla de integridad**: Si no se detecta el primer evento SSE con contenido (por ejemplo ante timeout o error de stream), `client_ttft_sse_s` se registra estrictamente como `null` acompañado de una condición explícita de error (`ttft_status`). **Queda prohibido sustituir el TTFT por `total_elapsed`**.

### C. Velocidad de Generación (`gen_tps` / `predicted_per_second`)
* **Definición**: Tasa pura de generación autoregresiva en tokens por segundo.
* **Cálculo estricto**:
  $$\text{gen\_tps} = \frac{\text{predicted\_n}}{\text{predicted\_ms} / 1000}$$
* **Regla metodológica fundamental**: **Nunca utilizar el tiempo total de la petición HTTP (`total_elapsed`) como divisor para calcular la velocidad de generación**. El tiempo total incluye el prefill (que en contextos largos puede tardar decenas de segundos); dividir los tokens generados por el tiempo total distorsiona y subestima artificialmente la velocidad de decodificación.

### D. Reutilización de Caché KV en el Servidor (Slot Cache Reuse)
* `llama-server.exe` mantiene en memoria el estado del slot de inferencia. Si una petición comparte prefijos idénticos con una anterior (como las instrucciones de sistema), el servidor reutiliza los vectores ya calculados.
* **Detección**: `llama.cpp` reporta `cache_n` (tokens reusados) y `prompt_n` (tokens nuevos evaluados).
  * En una petición donde `cache_n > 0`, el prefill reportado corresponde únicamente a los tokens incrementales.
  * Para medir ingesta pura sin sesgo, `test_context_generation.py` y `benchmark_protocol.py` limpian el slot entre corridas (`/slots/0?action=erase`) o garantizan contextos limpios.

---

## 4. Validación del Conteo de Tokens (Bytes vs Tokens)

Se incorporó [`verify_tokenizer.py`](verify_tokenizer.py) para auditar el tokenizador BPE de Qwen 2.5 (151.936 tokens de vocabulario).

### A. Resultados de la Verificación

| Elemento Analizado | Bytes | Tokens | Ratio (Bytes/Tok) | Cabe en `-c 4096` | Cabe en `-c 8192` |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Chat Corto (Texto plano)** | 84 B | 21 tok | 4.00 B/tok | SÍ | SÍ |
| **Chat Corto (ChatML Completo)** | 181 B | 39 tok | 4.64 B/tok | SÍ | SÍ |
| **`agent/watchdog.py` (Código crudo)** | 6.610 B | 1.455 tok | 4.54 B/tok | SÍ | SÍ |
| **`agent/watchdog.py` (Prompt + ChatML)** | 6.883 B | 1.515 tok | 4.54 B/tok | SÍ | SÍ |
| **`agent/tools.py` (Código crudo)** | 19.693 B | 4.401 tok | 4.47 B/tok | **NO (Excede)** | SÍ |
| **`agent/tools.py` (Prompt + ChatML)** | 19.963 B | 4.461 tok | 4.47 B/tok | **NO (Excede)** | SÍ |

### B. Conclusiones sobre Tokenización
1. **No equiparar bytes a tokens**: El código fuente en Python sobre Qwen 2.5 presenta una tasa empírica estable de **~4.47 a 4.54 bytes por token**.
2. **Plantilla ChatML**: Agregar encabezados de sistema (`<|im_start|>system\n...<|im_end|>`) añade entre 18 y 60 tokens adicionales al payload.
3. **Explicación del fallo de `tools.py` en `-c 4096`**:
   * En `test_real_workload.py`, la carga 3 evaluó originalmente `agent/watchdog.py` (1.515 tokens con ChatML), ajustándose al límite de 4096 tokens.
   * Si se intentara cargar `agent/tools.py` (4.461 tokens con ChatML) en un servidor configurado con `-c 4096`, el servidor rechaza la petición con `HTTP 400 Bad Request` por exceder la ventana de contexto.
   * **Corrección de reproducibilidad**: Se corrigió la discrepancia de nombres en `test_real_workload.py` para rotular explícitamente `watchdog.py` y documentar por qué `tools.py` requiere `-c 8192`.

---

## 5. Resultados del Benchmark de Ingesta Controlada (`llama-bench`)

Prueba ejecutada con [`audit_prompt_ingestion.py`](audit_prompt_ingestion.py) con **8 hilos constantes**, **FP16 KV-Cache**, **Flash Attention OFF (`-fa 0`)**, **`-b 512`** y **`-ub 128`** (3 repeticiones por longitud):

| Longitud Prompt | Corridas Ingesta `[1, 2, 3]` | Mediana Ingesta | Desv. Estándar | Tiempo Mediano Ingesta | Generación de Referencia (`n_prompt=0`, 16 tok) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **256 tokens** | `[31.03, 29.29, 34.79] t/s` | **31.03 t/s** | ±2.81 t/s | **8.25 seg** | **13.51 t/s** (±0.37) |
| **512 tokens** | `[33.15, 34.25, 33.52] t/s` | **33.52 t/s** | ±0.56 t/s | **15.27 seg** | **14.74 t/s** (±0.23) |
| **1024 tokens** | `[32.74, 32.19, 31.79] t/s` | **32.19 t/s** | ±0.48 t/s | **31.82 seg** | **14.78 t/s** (±0.82) |
| **2048 tokens** | `[30.23, 29.82, 30.30] t/s` | **30.23 t/s** | ±0.26 t/s | **67.74 seg** | **14.08 t/s** (±1.36) |
| **4096 tokens** | `[26.83, 26.79, 19.36] t/s` | **26.79 t/s** | ±4.30 t/s | **152.89 seg** | **10.89 t/s** (±0.31) |

### Rectificación Crítica sobre la Conclusión de Generación
> [!IMPORTANT]
> **Corrección metodológica**: `audit_prompt_ingestion.py` extrae la métrica de generación a partir de los registros de `llama-bench` donde `n_prompt == 0` y `n_gen > 0`.
>
> Esto significa que `llama-bench` ejecuta una prueba de generación **desde un contexto vacío ($n_{prompt}=0$)**, midiendo la velocidad base del decodificador y **no la decodificación tras haber procesado 4096 tokens previos en la memoria KV**.
>
> Por tanto, **los datos de `llama-bench` no demuestran causalidad ni prueban que la generación caiga un 26 % por efecto de tener 4096 tokens previos en el KV cache**. El origen de la variación observada en esa corrida de referencia (`n_prompt=0`) no quedó determinado experimentalmente y **no se puede atribuir al contexto previo**.

---

## 6. Diseño de la Prueba de Contexto Real (`test_context_generation.py`)

Para medir de manera rigurosa si el tamaño del contexto previo degrada o no la velocidad de generación, se diseñó [`test_context_generation.py`](test_context_generation.py).

### Protocolo Científico y Control de Variables
* **Contexto CONFIGURADO (`-c`)**: **8192 tokens constante**.
  * Separación clave: la memoria reservada para el KV cache en RAM se mantiene exactamente fija durante todas las mediciones, aislando el impacto de la asignación de memoria del impacto del cálculo de atención.
* **Contexto REALMENTE PROCESADO**: barrido de **256, 512, 1024, 2048 y 4096 tokens** de prompt de código real.
* **Tokens Objetivo a Generar**: **64 tokens constantes** a temperatura `0.0` (decodificación determinista).
* **Parámetros fijos**: Modelo Qwen 3B Q4_K_M, 8 hilos (`-t 8 -tb 8`), `-b 512 -ub 128`, KV-Cache FP16, Flash Attention OFF (`-fa off`).

### Salvaguardas Metodológicas Obligatorias
1. **Protocolo de Calentamiento (Warmup)**:
   * 2 corridas previas no contabilizadas (prefill ~512 tok, generación ~16 tok) para cargar pesos en caché de archivos del sistema operativo y estabilizar hilos OpenMP antes de registrar muestras oficiales.
2. **Repeticiones**:
   * Al menos **5 repeticiones por longitud de contexto** para permitir cálculo riguroso de medianas y desviaciones estándar.
3. **Verificación de Compatibilidad y Purga de Slots (`/slots/0?action=erase`)**:
   * En la arquitectura de `llama-server` (build `b11719`), el endpoint `/slots/:id_slot?action=erase` gestiona la purga del contexto almacenado en el KV cache.
   * La presencia del parámetro `--slot-save-path` es indispensable para registrar la ruta en el servidor (sin él, responde `HTTP 501 Not Implemented: "This server does not support slots action. Start it with --slot-save-path"`), pero **no constituye prueba suficiente de que el contexto anterior fue eliminado**.
   * El script comprueba la respuesta `HTTP 200`, inspecciona contadores mediante `GET /slots` y audita durante la inferencia que `cache_n == 0`. Si se detectara `cache_n > 0`, la corrida se marca con reuso de caché y se invalida para la comparación de generación.
   * Si el script no puede verificar la capacidad de purga al iniciar, **aborta de inmediato sin producir resultados etiquetados como válidos**.
4. **Diferenciación de Valores Objetivo frente a Valores Reportados**:
   * Se registran por corrida los valores objetivo (`target_prompt_tokens`, `target_gen_tokens`) de manera estrictamente separada de los valores reales reportados por el servidor (`prompt_n`, `cache_n`, `predicted_n`).
5. **Separación de Corridas Válidas, Distinción de Errores y Registro de Exclusiones**:
   * No se asume que `temperature=0.0` garantiza exactamente 64 tokens generados. Se inspecciona `finish_reason` ('length', 'stop') y si el modelo emite EOS antes del objetivo o sufre reuso de caché, la corrida se excluye de la métrica de generación comparativa.
   * **Tipificación explícita de categorías de exclusión**: Las estadísticas distinguen inequívocamente:
     * `model_early_termination`: el modelo detuvo la generación prematuramente (emisión de `<|im_end|>` / `stop`, `predicted_n < 64`).
     * `transport_or_timeout_error`: error de red, timeout HTTP/socket o interrupción de SSE sin recibir primer token (`client_ttft_sse_s = null`).
     * `cache_contamination`: la petición se completó, pero `cache_n > 0` evidencia reuso inadvertido de prefijos del KV cache.
   * **Conservación íntegra sin descarte silencioso**: Se conservan todas las muestras crudas, el `finish_reason` original y la razón explícita de exclusión (`exclusion_reason`) en el JSON final.
   * **Conteo de muestras válidas reportado por longitud**: El resumen estadístico de cada longitud de contexto (`summary_statistics`) expone explícitamente `valid_runs_count`, `early_terminations_count`, `transport_errors_count` y `cache_reuse_count`.
6. **Estado de Ejecución y Limitación Técnica Declarada**:
   * **Pruebas estáticas aprobadas**: La sintaxis, el protocolo, el manejo de procesos y la paridad de scripts han sido validados estáticamente al 100 %.
   * **Pendiente de validación en ejecución**: La purga efectiva de slots (`/slots/0?action=erase`) en caliente y el benchmark de generación tras ingesta de contexto permanecen **pendientes de validación en ejecución**. No se presenta ningún valor como resultado experimental medido hasta que la prueba sea expresamente autorizada y ejecutada.

### Análisis de la Arquitectura Interna de llama.cpp (b11719): `server_task_result_slot_erase` y `cache_n`

A fin de sustentar con rigor técnico el comportamiento de la limpieza de ranuras y el seguimiento de caché, se inspeccionó el código fuente y las referencias binarias de `llama.cpp` (`llama-server.exe` / `llama-server-impl.dll` b11719):

#### A. Archivos y Funciones del Código Fuente de Soporte
* **`tools/server/server-http.cpp`**:
  * Registra el router HTTP para `/slots/:id_slot`.
  * Valida la presencia de `params.slot_save_path.empty()`. Si está vacío, rechaza la petición con `HTTP 501`:
    `"This server does not support slots action. Start it with --slot-save-path"`.
  * Si `--slot-save-path` está configurado y el query param es `action=erase`, construye una tarea de servidor (`server_task_type::SLOT_ERASE`) y la encola en `server_queue`.
  * Recibe asíncronamente el resultado `server_task_result_slot_erase` y serializa la respuesta `HTTP 200 OK`.
* **`tools/server/server-task.h` / `tools/server/server-task.cpp`**:
  * Declara la estructura `server_task_result_slot_erase` heredada de `server_task_result`.
  * Maneja el despacho polimórfico verificado en binario mediante:
    `dynamic_cast<server_task_result_slot_erase*>(result.get()) != nullptr`.
* **`tools/server/server-context.h` / `tools/server/server-context.cpp`**:
  * En `server_context::process_tasks()`, procesa la tarea de borrado invocando `slot.reset()`.
  * `slot.reset()` ejecuta `llama_kv_cache_seq_rm()` sobre el identificador de secuencia del slot, liberando todas las celdas del KV cache asignadas a ese slot y restableciendo `slot.n_prompt_tokens_cache = 0`.
* **`tools/server/server-common.cpp` y serialización de `timings`**:
  * Define la semántica de `cache_n` / `n_prompt_tokens_cache`: representa el conteo de tokens del prompt que coincidieron exactamente con prefijos ya residentes en el KV cache.
  * Si `cache_n > 0`, el servidor omite evaluar esos tokens mediante `llama_decode`, reduciendo artificialmente `prompt_ms` y alterando la latencia inicial.
  * Por consiguiente, verificar que `cache_n == 0` es la única garantía determinista de que el KV cache fue purgado y que el prefill midió el 100 % de los tokens evaluados.

#### B. Separación Metodológica: Inspección de Código vs Validación en Ejecución
* **Verificado fehacientemente por inspección estática del código y binario**:
  1. La existencia y vinculación de `tools/server/server-http.cpp`, `tools/server/server-context.cpp` y `tools/server/server-task.cpp` en el binario compilado.
  2. La presencia de la clase `server_task_result_slot_erase` y el chequeo en tiempo de ejecución de tipos.
  3. El requerimiento insoslayable de `--slot-save-path` para habilitar el endpoint de purga (mensaje HTTP 501 literal).
  4. La existencia del contador `n_prompt_tokens_cache` en el slot y su exportación en los objetos de tiempo y estado.
* **Pendiente de validación en ejecución (a comprobar al autorizar el benchmark)**:
  1. Comprobación empírica en el loopback Windows de que la petición `POST /slots/0?action=erase` devuelva efectivamente `HTTP 200` y libere los recursos sin bloqueos de concurrencia.
  2. Confirmación mediante consulta a `GET /slots` de que `n_prompt_tokens_cache == 0` y `is_processing == false`.
  3. Validación de que la primera solicitud de inferencia posterior reporte efectivamente `timings.cache_n == 0` en el flujo SSE.

---

## 7. Eliminación de Riesgos de Proceso y Seguridad Operativa

En versiones preliminares, `benchmark_protocol.py` contenía llamadas a `Stop-Process -Name 'llama-server' -Force`, lo cual implicaba un riesgo inaceptable de terminar procesos ajenos o el servidor de producción.

Se implementaron las siguientes salvaguardas en todos los scripts de prueba:
1. **Comprobación de puerto sin agresión**: función `is_port_in_use(port)` mediante socket TCP local. Si el puerto está ocupado, el script **aborta con un mensaje explícito** sin cerrar ningún proceso externo.
2. **Administración exclusiva de PID propio**: el script almacena el PID retornado por `subprocess.Popen` y en su bloque `finally:` administra únicamente ese proceso (`proc.terminate()` y `proc.kill()` en caso de timeout).
3. **Persistencia de logs de servidor**: la salida de error y arranque del servidor ya no se descarta en `DEVNULL`; se redirige a archivos dedicados (`benchmark_server.log`, `context_server.log`) para diagnóstico de fallas.

---

## 8. Esquema de Persistencia de Datos Crudos

Para evitar clasificar resúmenes estadísticos como datos crudos, los archivos JSON (`audit_ingestion_results.json` y futuros resultados) adoptan una estructura que separa formalmente las muestras originales de las estadísticas agregadas:

```json
{
  "target_prompt_tokens": 4096,
  "raw_samples": {
    "prompt_samples_ns": [152636725200, 152893540100, 211562912400],
    "prompt_samples_ts": [26.83, 26.79, 19.36],
    "gen_samples_ns": [1469245100, 1468921300, 1471012500],
    "gen_samples_ts": [10.89, 10.89, 10.88]
  },
  "summary_statistics": {
    "prompt_median_tps": 26.79,
    "prompt_avg_tps": 24.33,
    "prompt_stddev_tps": 4.30,
    "prompt_median_duration_s": 152.89,
    "gen_reference_median_tps": 10.89,
    "gen_reference_stddev_tps": 0.31
  },
  "metadata": {
    "note_on_generation": "La prueba de generacion de llama-bench se ejecuta con n_prompt=0 y no mide degradacion tras evaluar el prompt."
  }
}
```

---

## 9. Instrucciones de Reproducción

Todas las instrucciones utilizan rutas relativas ejecutables desde la raíz del repositorio:

### A. Validar Tokenizador (Archivos y Plantilla ChatML)
```cmd
python docs/benchmark-audit/verify_tokenizer.py
```

### B. Ingesta Controlada (llama-bench)
```cmd
python docs/benchmark-audit/audit_prompt_ingestion.py
```

### C. Evaluación de Cargas Reales (Streaming SSE y Métricas Separadas)
Asegurarse de tener el servidor activo en el puerto 8089 y ejecutar:
```cmd
python docs/benchmark-audit/test_real_workload.py
```

### D. Benchmark de Contexto Real (Pendiente de Ejecución)
Para ejecutar la prueba de degradación tras autorización:
```cmd
python docs/benchmark-audit/test_context_generation.py --run
```
