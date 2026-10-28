# AURA CORE — Fase II: Informe del Experimento Controlado de Generalización A/B

**Fecha y Hora:** 2026-10-26 19:16:00 UTC-3  
**Rol:** Principal Engineer — Inferencia Local, Evaluación Experimental de LLM y Optimización  
**Suite Evaluada:** `evals/generalization_tasks.json` (8 tareas originales de código no vistas)  
**Modelo:** `models/qwen2.5-coder-3b-instruct-q4_k_m.gguf`  
**Servidor Experimental:** Puerto 8083 (PID `18728`, iniciado exclusivamente para la prueba y detenido al 100%)  
**Puerto de Producción (8089):** Intacto y cerrado en todo momento.  
**Archivos JSON Producidos:**
- Variante A (Baseline): [`experiments/ab_selective_eval/20261026_211630_generalization_variant_A.json`](file:///c:/Users/Guille/Downloads/IA/experiments/ab_selective_eval/20261026_211630_generalization_variant_A.json)
- Variante B (Recuperación ICL): [`experiments/ab_selective_eval/20261026_214750_generalization_variant_B.json`](file:///c:/Users/Guille/Downloads/IA/experiments/ab_selective_eval/20261026_214750_generalization_variant_B.json)

---

## 1. Resumen Ejecutivo

Se ejecutó un experimento A/B controlado sobre las **8 tareas de código no vistas** de `evals/generalization_tasks.json` bajo el protocolo de dos intentos máximos (Pass@1 + Reparación con Diagnóstico de Contrato).

El ajuste del parámetro de timeout por llamada a 240 segundos eliminó completamente los fallos de infraestructura: **8/8 tareas completaron de forma válida en ambas variantes (0 errores de infraestructura, 0 timeouts)**.

### Resultados Sintéticos:
- **Pass@1:**
  - Variante A (Baseline): 0 / 8 (0.0%)
  - Variante B (Recuperación ICL): 0 / 8 (0.0%)
- **Reparaciones Exitosas (Intento 2):**
  - Variante A (Baseline): **1 tarea reparada** (`gen_04_matrix_spiral_traversal`)
  - Variante B (Recuperación ICL): **0 tareas reparadas**
- **Aciertos Finales:**
  - Variante A (Baseline): **1 / 8 (12.5%)**
  - Variante B (Recuperación ICL): **0 / 8 (0.0%)**
- **Balance Neto (B - A):** **-1 tarea (Delta: -12.5%)**.
  - **Tareas Ganadas por B:** 0
  - **Regresiones Causadas por B:** 1 (`gen_04_matrix_spiral_traversal`)
  - **Empates:** 7 tareas (ambas fallaron en `gen_01`, `gen_02`, `gen_03`, `gen_05`, `gen_06`, `gen_07`, `gen_08`).

---

## 2. Tabla Comparativa por Tarea

| # | Task ID | Categoría | Var A Pass@1 | Var A Final | Var B Pass@1 | Var B Final | Ejemplos Recuperados en B | Impacto Neto |
|:---:|---|---|:---:|:---:|:---:|:---:|---|:---:|
| **01** | `gen_01_token_bucket_limiter` | `code_generation` | FAIL (114.6s) | FAIL (114.6s) | FAIL (124.9s) | FAIL (120.7s) | `train_36_cron_schedule_next_occurrence` | Neutro (Fallo mutuo) |
| **02** | `gen_02_deep_merge_dict` | `code_generation` | FAIL (95.0s) | FAIL (134.7s) | FAIL (72.2s) | FAIL (74.7s) | `train_35_safe_nested_path_extractor`, `train_07_debug_generator_pipeline` | Neutro (Fallo mutuo) |
| **03** | `gen_03_debug_retry_decorator` | `debugging` | FAIL (71.3s) | FAIL (96.3s) | FAIL (75.1s) | FAIL (61.3s) | `train_28_debug_rate_limited_batch_retry`, `train_10_debug_event_emitter_leak` | Neutro (Fallo mutuo) |
| **04** | `gen_04_matrix_spiral_traversal` | `code_generation` | FAIL (90.8s) | **PASS (135.5s, REPARADA)** | FAIL (92.5s) | FAIL (87.1s) | `train_04_matrix_rotation_90deg`, `train_23_sliding_window_maximum` | **REGRESIÓN EN B (-1)** |
| **05** | `gen_05_safe_csv_parser` | `code_generation` | FAIL (116.1s) | FAIL (155.4s) | FAIL (98.6s) | FAIL (81.4s) | `train_24_canonical_json_serializer`, `train_07_debug_generator_pipeline` | Neutro (Fallo mutuo) |
| **06** | `gen_06_async_task_pool_with_cancellation` | `code_generation` | FAIL (83.8s) | FAIL (112.8s) | FAIL (108.5s) | FAIL (133.1s) | `train_18_async_rate_limited_semaphore_worker`, `train_23_sliding_window_maximum` | Neutro (Fallo mutuo) |
| **07** | `gen_07_debug_circular_buffer` | `debugging` | FAIL (65.9s) | FAIL (168.1s) | FAIL (119.8s) | FAIL (101.6s) | `train_17_bounded_blocking_queue`, `train_07_debug_generator_pipeline` | Neutro (Fallo mutuo) |
| **08** | `gen_08_dependency_graph_topological_sort` | `code_generation` | FAIL (86.4s) | FAIL (159.8s) | FAIL (111.5s) | FAIL (92.1s) | `train_24_canonical_json_serializer`, `train_07_debug_generator_pipeline` | Neutro (Fallo mutuo) |

---

## 3. Análisis Causal de las Diferencias Funcionales: La Regresión en `gen_04`

Para determinar por qué la Variante A reparó `gen_04` y la Variante B falló, se inspeccionaron los diagnósticos estructurados y los códigos de ambas variantes:

1. **El fallo en el Intento Inicial (común a A y B):**  
   Ambas implementaciones iniciales calcularon correctamente el recorrido en espiral pero omitieron validar la homogeneidad de tipos internos de la matriz (`test_invalid_types` falló porque la matriz contenía elementos que no eran `int` ni `float`).
2. **Diagnóstico y Reparación en la Variante A (Baseline):**  
   En la Variante A, al recibir el feedback del error condensado de las pruebas sin ejemplos ajenos que dispersaran la atención semántica, el modelo diagnosticó de forma precisa y exhaustiva:  
   - `**ERROR:** The original code did not raise a TypeError when encountering non-integer/float elements in the matrix.`  
   - `**CONTRATO:** The contract specified that TypeError("Invalid matrix type") should be raised if any element in the matrix is not an integer or float.`  
   - `**CORRECCIÓN:** The function now checks each element in the matrix to ensure it is an integer or float before appending it to the result list. If an element is not valid, a TypeError is raised.`  
   El código resultante implementó la validación recursiva exacta y superó el 100% de las pruebas (**PASS**).
3. **Efecto de Distracción en la Variante B (ICL):**  
   En la Variante B, el prompt inicial contenía dos ejemplos recuperados: `train_04_matrix_rotation_90deg` y `train_23_sliding_window_maximum`.  
   Al recibir el error de pruebas en el reintento, el modelo emitió un diagnóstico superficial y defectuoso:  
   - `**ERROR:** TypeError not raised.`  
   - `**CONTRATO:** TypeError("Invalid matrix type") should be raised for non-list inputs.`  
   - `**CORRECCIÓN:** Add a check to raise TypeError if the input is not a list.`  
   El modelo en B solo verificó `if not isinstance(matrix, list)` pero omitió verificar los tipos de los elementos internos de cada fila, repitiendo exactamente el mismo fallo en el segundo intento (**FAIL**).

---

## 4. Métricas de Latencia y Costo Temporal

| Métrica Temporal | Variante A (Baseline) | Variante B (Recuperación ICL) | Delta (B - A) |
|---|:---:|:---:|:---:|
| **Latencia Total Inferencia** | 1,801.08 s (~30.0 min) | 1,555.08 s (~25.9 min) | -246.00 s (-13.7%) |
| **Latencia Media por Tarea** | 225.13 s | 194.39 s | -30.74 s |
| **Latencia Mediana por Tarea** | 229.43 s | 191.82 s | -37.61 s |
| **Latencia Máxima (1 tarea, 2 intentos)** | 271.52 s (`gen_05`) | 245.56 s (`gen_01`) | -25.96 s |
| **Latencia Media Intento 1** | 90.50 s | 100.40 s | +9.90 s (+10.9% por ICL) |
| **Latencia Media Intento 2** | 134.63 s | 93.99 s | -40.64 s |

**Observación sobre Tiempos:**  
En el Intento 1, la Variante B tardó en promedio ~10 segundos más por tarea debido al procesamiento inicial de los tokens de contexto ICL (prefill time). En el Intento 2, la Variante B generó soluciones más breves que no resolvieron la validación de tipos, resultando en menor tiempo de generación en el reintento.

---

## 5. Paridad Experimental y Evidencia de Control

1. **Mismo Modelo y Temperatura:** `qwen2.5-coder-3b-instruct-q4_k_m.gguf`, `temperature: 0.0` para determinismo.
2. **Mismo Sistema y Contexto:** Prompt de Sistema V2, ventana de contexto 8,192 tokens, max_tokens 1,024.
3. **Mismo Mecanismo de Evaluación:** Ejecución estricta en Debian WSL2 bajo `aura_sandbox` con `unshare -r -n`, límites `prlimit` y timeout de ejecución de código de 10s.
4. **Mismo Timeout HTTP Común:** 240.0s verificado y registrado en los metadatos de configuración de ambos JSON.
5. **Aislamiento de la Inyección:** La Variante A no recibió ningún bloque ICL. En el Intento 2 (reparación), ninguna variante recibió ejemplos ICL, garantizando que el reintento evaluara idéntica plantilla de diagnóstico.

---

## 6. Verificación de Integridad Criptográfica

Los hashes SHA-256 de todos los datasets y benchmarks permanecen idénticos a los registrados al inicio de la sesión:
- `datasets/training_pairs_pilot.json`: `7E1B43E291A2BF40023A5B78BFCDE2855EB48219678E28B2F92202DC38B8FB3B`
- `datasets/training_pairs_batch_01.json`: `FEFBF971771FA9F441815B37CA04B7C81429288C807CCCAE954219C0CA8DB671`
- `evals/coding_tasks.json`: `DA721A900C4041DBD57AD49DA3DEC1FCFBDE1AB0DFF87301249736BE74D1EA42`
- `evals/generalization_tasks.json`: `3AD870F30A9FE4AB3FDB0A0BB9BD03CAFB739840CC81D4650C517CB8EB2FFB98`

---

## 7. Limitaciones, Amenazas a la Validez y Conclusión Científica

1. **Tamaño Muestral ($N = 8$):** Con una muestra de 8 tareas no vistas, el resultado es estrictamente exploratorio y no permite extraer conclusiones estadísticas definitivas.
2. **Ausencia de Transferencia General:** A diferencia de la suite de referencia (donde el corpus contenía tareas con léxico y estructuras muy similares, ej. LRU vs LFU, lo que favoreció la reparación de `task_02`), en la suite de generalización la recuperación de ejemplos no aportó mejoras y provocó un efecto distractor en `gen_04`.
3. **Conclusión Técnica:** La recuperación de ejemplos basada en BM25 superficial no generaliza automáticamente a problemas nuevos y no sustituye la capacidad de razonamiento contractual del modelo. Para tareas fuera de distribución, inyectar ejemplos parcialmente similares introduce ruido en el contexto que puede degradar la precisión del diagnóstico de error en el reintento.

---

## 8. Estado de la Infraestructura

- **Puerto 8083 (Experimental):** Detenido formalmente y verificado como **CLOSED**.
- **Puerto 8089 (Producción):** Intacto y verificado como **CLOSED**.
- **Git:** Sin commits ni pushes realizados. Todos los cambios permanecen en el árbol de trabajo no rastreado.
