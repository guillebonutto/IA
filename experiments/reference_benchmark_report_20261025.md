# AURA CORE — Informe de Referencia: Benchmark de Programación (Línea Base)
**Fecha y Hora (UTC):** 2026-10-25T18:09:52Z  
**Archivo de Resultados:** `experiments/coding_eval_results_20261025_150952.json`  
**Objetivo:** Establecer la línea base objetiva y reproducible del modelo Qwen 2.5 Coder 3B Instruct (Q4_K_M) utilizando la suite estandarizada de 12 tareas y el entorno de ejecución aislado en Debian WSL2.

---

## 1. Identificación y Parámetros del Entorno

- **Modelo:** `qwen2.5-coder-3b-instruct-q4_k_m.gguf` (2,007.4 MB, SHA-256 verificado en catálogo de modelos)
- **Cuantización:** `Q4_K_M`
- **Motor de Inferencia:** `llama-server.exe` (llama.cpp)
- **Endpoint Utilizado:** `http://127.0.0.1:8083/v1` (Puerto experimental exclusivo; puerto 8089 intacto)
- **Parámetros de Inferencia:**
  - `temperature`: `0.0` (decodificación determinista)
  - `max_tokens`: `1024`
  - `context_size`: `4096`
  - `threads`: `8` (CPU compute / batch)
  - `prompt_cache`: desactivado / sin estado previo
- **Entorno de Ejecución Aislado:**
  - Debian 13 WSL2
  - Usuario: `aura_sandbox` (UID 1001, sin sudo)
  - Aislamiento de Red: `unshare -r -n` (Pila vacía, `Network is unreachable`)
  - Límites de Recursos: `prlimit` (512 MB RAM, 128 procesos/threads, 10 MB tamaño de archivo)
  - Límites de Salida: Lector en streaming no bloqueante con `selectors` (32 KB máx. en memoria, corte inmediato al alcanzar 5 MB generados)
  - Timeout por Tarea: `timeout -k 2s 10.0s` (Terminación forzada de árbol de procesos)

---

## 2. Resumen Global de Puntuación

| Métrica | Valor Observado |
| :--- | :--- |
| **Puntuación Total** | **2.0 / 12.0** |
| **Porcentaje de Aprobación** | **16.7 %** |
| **Tareas Evaluadas** | 12 de 12 (100 %) |
| **Tareas Bloqueadas por Entorno** | 0 (0 %) |
| **Violaciones de Seguridad / Fallos de Sandbox** | 0 (0 %) |
| **Duración Total de la Evaluación** | **701.36 segundos** (~11.7 minutos) |
| **Tiempo Medio de Inferencia** | 54.55 s por tarea |
| **Tiempo Medio de Ejecución de Pruebas** | 0.088 s por tarea |

---

## 3. Rendimiento por Categoría

| Categoría | Total Tareas | Aprobadas | Tasa de Aprobación | Observaciones Principales |
| :--- | :---: | :---: | :---: | :--- |
| **Generación de Código (`code_generation`)** | 3 | 1 | 33.3 % | Resuelve LRU Cache en O(1). Falla en Rate Limiter (tipado/comparación) y Flatten Dict (recursión en primitivos). |
| **Depuración (`debugging`)** | 2 | 1 | 50.0 % | Resuelve Búsqueda Binaria O(log N). Falla en Mutable Default (persistencia de mutación del diccionario). |
| **Casos Límite (`edge_cases_reasoning`)** | 2 | 0 | 0.0 % | Omite validación de argumentos en intervalos. Falla sintáctica con API `re.Match.groups()` en SemVer. |
| **Refactorización (`refactoring`)** | 2 | 0 | 0.0 % | Rompe contrato de API en cálculo de precios (crea clase en vez de función). Bloquea semáforo erróneamente en async. |
| **Creación de Tests (`test_creation`)** | 1 | 0 | 0.0 % | La suite generada malinterpreta el sobregiro bancario y falla contra la solución canónica. |
| **Explicación Técnica (`technical_explanation`)** | 2 | 0 | 0.0 % | Estructura comprensible pero omite términos léxicos indispensables (`conteo de referencias`, `parametrización`). |

---

## 4. Tabla Detallada de las 12 Tareas

| # | Tarea | Categoría | Puntos | Latencia Inf. | Latencia Eval. | Estado | Causa de Fallo / Observación |
| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :--- |
| **01** | `task_01_lru_cache` | `code_generation` | **1.0 / 1.0** | 60.44 s | 0.087 s | **PASS** | Implementación O(1) con `OrderedDict` correcta y manejo de `ValueError`. |
| **02** | `task_02_sliding_rate_limiter` | `code_generation` | **0.0 / 1.0** | 36.90 s | 0.124 s | **FAIL** | Error de tipado: compara lista con float (`list >= float`) al purgar timestamps en dict comprehension. |
| **03** | `task_03_flatten_nested_json` | `code_generation` | **0.0 / 1.0** | 21.74 s | 0.075 s | **FAIL** | `AttributeError`: invoca `.items()` sobre enteros/strings dentro de listas anidadas; omite contenedores vacíos. |
| **04** | `task_04_debug_mutable_default_and_closure` | `debugging` | **0.0 / 1.0** | 51.47 s | 0.073 s | **FAIL** | Corrige el late-binding pero sigue mutando el diccionario del llamador (`base_config`) sin copia defensiva. |
| **05** | `task_05_debug_binary_search_edge_cases` | `debugging` | **1.0 / 1.0** | 53.97 s | 0.083 s | **PASS** | Búsqueda binaria O(log N) correcta, encuentra primer índice con duplicados y gestiona listas vacías. |
| **06** | `task_06_edge_case_interval_merging` | `edge_cases_reasoning` | **0.0 / 1.0** | 43.86 s | 0.094 s | **FAIL** | Fusión de intervalos correcta pero olvida validar `start > end`, no levantando el `ValueError` requerido. |
| **07** | `task_07_edge_case_robust_semver_comparator` | `edge_cases_reasoning` | **0.0 / 1.0** | 88.53 s | 0.055 s | **FAIL** | Uso erróneo de la API de expresiones regulares (`match.groups('major', 'minor', 'patch')` en vez de `group()`). |
| **08** | `task_08_refactor_cyclomatic_complexity` | `refactoring` | **0.0 / 1.0** | 75.89 s | 0.082 s | **FAIL** | Violación de contrato de API: generó una clase `Order` en lugar de la función obligatoria `calculate_order_price(order: dict)`. |
| **09** | `task_09_refactor_async_parallel_batcher` | `refactoring` | **0.0 / 1.0** | 44.45 s | 0.247 s | **FAIL** | Lógica de concurrencia invertida: envolvió todo el `gather()` en `async with semaphore` en lugar de delimitar cada tarea. |
| **10** | `task_10_test_creation_bank_account` | `test_creation` | **0.0 / 1.0** | 43.17 s | 0.091 s | **FAIL** | Lógica de prueba defectuosa: asume que un retiro dentro del margen de sobregiro levanta `InsufficientFundsError`. |
| **11** | `task_11_tech_explanation_gil_and_multiprocessing` | `technical_explanation` | **0.0 / 1.0** | 71.71 s | 0.0001 s | **FAIL** | Omitió el concepto explícito de "conteo de referencias" (`reference counting`) requerido por la rúbrica. |
| **12** | `task_12_tech_explanation_sql_injection_defense` | `technical_explanation` | **0.0 / 1.0** | 96.57 s | 0.0002 s | **FAIL** | Omitió el término de "parametrización" / "consultas parametrizadas" requerido por la rúbrica objetiva. |

---

## 5. Patrones y Agrupación de Errores

1. **Ruptura de Contrato de API e Instrucciones Negativas (3 tareas):**
   - En T08, el modelo ignoró la instrucción de mantener la función de entrada y refactorizó a una clase orientada a objetos.
   - En T06, omitió la validación explícita de precondiciones (`start > end`).
   - En T04, ignoró el requisito de pureza y mutó el argumento mutable recibido.
2. **Defectos de Tipado y Suposición de Estructura de Datos (2 tareas):**
   - En T02, iteró sobre un diccionario asumiendo valores escalares cuando eran listas.
   - En T03, asumió que los elementos hijos eran recursivamente diccionarios y llamó `.items()` sobre primitivos.
3. **Uso Defectuoso de APIs Estándar de Python (2 tareas):**
   - En T07, pasó nombres de grupos posicionalmente a `re.Match.groups()`.
   - En T09, aplicó el semáforo de `asyncio` al contenedor del lote en lugar de a cada invocación asíncrona.
4. **Fallas Conceptuales en Diseño de Pruebas (1 tarea):**
   - En T10, el modelo no comprendió la regla de negocio del sobregiro en su propia prueba unitaria.
5. **Cobertura Terminológica en Explicaciones Técnicas (2 tareas):**
   - En T11 y T12, el modelo explicó conceptualmente los problemas pero omitió las palabras clave canónicas exigidas por la rúbrica léxica.

---

## 6. Limitaciones del Protocolo y Observaciones

1. **Aislamiento Verificado al 100 %:** No se registraron caídas, fallos de conectividad hacia el host ni desbordamientos de memoria en el ejecutor aislado. Todas las ejecuciones de código candidato ocurrieron exclusivamente en Debian WSL2 bajo el usuario `aura_sandbox`.
2. **Determinismo:** Con `temperature=0.0`, los resultados son 100 % reproducibles con este mismo checkpoint y configuración.
3. **Línea Base Inicial:** Este benchmark establece la marca cero (**16.7 %**) sobre la cual se deberán evaluar y contrastar futuras intervenciones de prompting, fine-tuning o tooling.
