# AURA CORE — Informe de Auditoría y Validación de Batch 01

**Fecha de Auditoría:** 2026-10-26  
**Lote Auditado:** Lote 1 de Ampliación (`datasets/training_pairs_batch_01.json`, 20 tareas: `train_21` a `train_40`)  
**Dataset Piloto Aprobado:** [`datasets/training_pairs_pilot.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.json) (20 tareas: `train_01` a `train_20`)  
**Hash SHA-256 del Piloto (Invariable):** `7E1B43E291A2BF40023A5B78BFCDE2855EB48219678E28B2F92202DC38B8FB3B`  
**Entorno de Ejecución:** Debian 13 WSL2 (`aura_sandbox`, aislamiento con `unshare -r -n`)  
**Evaluador:** AURA CORE Quality Assurance & Verification Subsystem  
**Estado Final del Lote 1:** **APTO**

---

## 1. Resumen Ejecutivo

En cumplimiento de la directiva de ampliación controlada del dataset, se diseñó, implementó y validó de forma independiente el **Lote 1** (`datasets/training_pairs_batch_01.json`), compuesto por 20 nuevos pares de entrenamiento verificables (`train_21` a `train_40`).

El dataset piloto previo se mantuvo **completamente intacto**, verificado mediante su hash criptográfico SHA-256 (`7E1B43...`). El nuevo lote se generó en un archivo independiente sin concatenación prematura.

### Resultados Cuantitativos Principales:
- **Tasa de aprobación de soluciones de referencia:** **20 / 20 (100.0%) PASS** en sandbox Debian WSL2.
- **Tasa de aniquilación de mutantes (Mutation Testing):** **20 / 20 (100.0%) KILLED** (sensibilidad del 100% en las suites de pruebas).
- **Esquema de datos:** **20 / 20 conformes** con los 10 campos requeridos (`task_id`, `category`, `contract`, `input_signature`, `reference_solution`, `edge_cases`, `tests`, `verification_status`, `source`, `verified_at_iso`).
- **Separación frente a Benchmarks de Evaluación (`evals/coding_tasks.json` y `evals/generalization_tasks.json`):**
  - **0 colisiones de ID** (0 / 40 colisiones).
  - **Similitud léxica Jaccard máxima:** **0.1556** (entre `train_31_doubly_linked_list_deque` y `gen_07_debug_circular_buffer` debido a vocabulario genérico de colas).
  - **0% fuga de código de solución o tests.**
- **Claridad Contractual:** Todos los 20 contratos distinguen formalmente entre `TypeError` y `ValueError` de acuerdo con las directivas del piloto.

---

## 2. Tabla Consolidada de los 20 Ejemplos de Batch 01

| # | Task ID | Categoría | Solución Ref. (WSL2 Sandbox) | Mutation Testing (Sensibilidad) | Complejidad / Diseño | Estado |
|:---:|---|---|:---:|:---:|---|:---:|
| **21** | `train_21_binary_tree_diameter` | `code_generation` | **PASS** (3.724s) | **KILLED** (FAIL: `test_diameter_not_passing_root`) | $O(N)$ tiempo, $O(H)$ espacio | **APTO** |
| **22** | `train_22_k_way_sorted_merge_generator` | `code_generation` | **PASS** (0.316s) | **KILLED** (FAIL: `test_standard_merge`) | Min-Heap perezoso $O(K)$ RAM | **APTO** |
| **23** | `train_23_sliding_window_maximum` | `code_generation` | **PASS** (0.310s) | **KILLED** (FAIL: `test_standard_case`) | Deque monótono lineal $O(N)$ | **APTO** |
| **24** | `train_24_canonical_json_serializer` | `code_generation` | **PASS** (0.300s) | **KILLED** (FAIL: `test_key_sorting_determinism`) | Canónico RFC 8785 determinista | **APTO** |
| **25** | `train_25_bloom_filter_bitarray` | `code_generation` | **PASS** (0.350s) | **KILLED** (FAIL: `test_add_and_membership`) | Bit array con hashes SHA-256 | **APTO** |
| **26** | `train_26_debug_flatten_tree_preorder` | `debugging` | **PASS** (0.272s) | **KILLED** (FAIL: `test_standard_flatten`) | In-place pre-order sin punteros perdidos | **APTO** |
| **27** | `train_27_debug_dag_longest_path` | `debugging` | **PASS** (0.291s) | **KILLED** (FAIL: `test_cycle_detection_raises`) | Kahn topo-sort + DP sobre DAG | **APTO** |
| **28** | `train_28_debug_rate_limited_batch_retry` | `debugging` | **PASS** (0.312s) | **KILLED** (FAIL: `test_non_retryable_exception_fails_immediately`) | Backoff exponencial con filtros | **APTO** |
| **29** | `train_29_debug_concurrent_counter_deadlock` | `debugging` | **PASS** (0.309s) | **KILLED** (FAIL: `test_insufficient_funds`) | Prevención de deadlock por orden ID | **APTO** |
| **30** | `train_30_fenwick_tree_binary_indexed_tree` | `data_structures` | **PASS** (0.261s) | **KILLED** (FAIL: `test_prefix_and_range_sum`) | Fenwick tree $O(\log N)$ sumas y deltas | **APTO** |
| **31** | `train_31_doubly_linked_list_deque` | `data_structures` | **PASS** (0.401s) | **KILLED** (FAIL: `test_fifo_and_lifo_operations`) | Centinelas dobles $O(1)$ sin tamaño fijo | **APTO** |
| **32** | `train_32_radix_tree_compressed_trie` | `data_structures` | **PASS** (0.386s) | **KILLED** (FAIL: `test_insert_search_starts_with`) | Patricia Trie con compresión de aristas | **APTO** |
| **33** | `train_33_interval_tree_point_query` | `data_structures` | **PASS** (0.333s) | **KILLED** (FAIL: `test_point_boundary`) | Árbol de intervalos para puntos $O(\log N + K)$ | **APTO** |
| **34** | `train_34_semver_expression_matcher` | `edge_cases` | **PASS** (0.302s) | **KILLED** (FAIL: `test_range_and_caret`) | Caret, tilde y rangos SemVer | **APTO** |
| **35** | `train_35_safe_nested_path_extractor` | `edge_cases` | **PASS** (0.344s) | **KILLED** (FAIL: `test_nested_dict_and_array`) | Sintaxis `a[0].b` segura con defaults | **APTO** |
| **36** | `train_36_cron_schedule_next_occurrence` | `edge_cases` | **PASS** (0.353s) | **KILLED** (FAIL: `test_hourly_and_steps`) | Parser Cron 5 campos y proyección UTC | **APTO** |
| **37** | `train_37_async_debounced_coroutine` | `concurrency` | **PASS** (0.446s) | **KILLED** (FAIL: `test_debounced_burst`) | Debounce asíncrono y cancelación limpia | **APTO** |
| **38** | `train_38_thread_pool_barrier_synchronizer` | `concurrency` | **PASS** (0.319s) | **KILLED** (FAIL: `test_barrier_release_and_cycle`) | CyclicBarrier con condición y timeout | **APTO** |
| **39** | `train_39_refactor_pipeline_middleware_chain` | `refactoring` | **PASS** (0.291s) | **KILLED** (FAIL: `test_onion_execution_order`) | Patrón Onion Pipeline encadenable | **APTO** |
| **40** | `train_40_refactor_specification_filter_engine` | `refactoring` | **PASS** (0.290s) | **KILLED** (FAIL: `test_composite_specification`) | Patrón Specification con operadores booleanos | **APTO** |

---

## 3. Incidencias Detectadas y Resueltas Durante la Construcción

### Incidencia 1: Topología de Prueba No Discriminatoria en `train_21`
- **Descripción:** El mutante de diámetro de árbol binario computaba la suma de alturas de los subárboles de la raíz principal (`h(root.left) + h(root.right)`). En la prueba inicial, el camino de prueba tenía su diámetro pasando por la raíz principal, por lo que el mutante sobrevivió inicialmente.
- **Corrección:** Se añadió un caso de prueba donde el subárbol izquierdo tiene un camino interno largo (diámetro 6) mientras que cualquier camino que pase por la raíz principal mide a lo sumo 5.
- **Resultado:** El mutante fue rechazado inequívocamente (`FAIL`), garantizando la detección del defecto.

### Incidencia 2: Resolución de Futuros Cancelados en `train_37`
- **Descripción:** En la implementación inicial del `AsyncDebouncer`, cuando una nueva llamada cancelaba a la tarea anterior en cola (`self._pending_task.cancel()`), el `Future` de la llamada cancelada no recibía un resultado inmediato, provocando que `asyncio.gather` esperara indefinidamente hasta el timeout de 10 segundos del runner.
- **Corrección:** Se asoció un tracking de `_pending_future`, resolviéndolo con `None` de forma atómica e inmediata al recibir la señal de cancelación antes de crear la nueva tarea.
- **Resultado:** Tiempo de ejecución reducido a 0.446s con 100% de éxito en sandbox.

---

## 4. Auditoría de Separación y No-Contaminación

La auditoría automática ejecutada mediante [`scratch/audit_batch_01_separation.py`](file:///c:/Users/Guille/Downloads/IA/scratch/audit_batch_01_separation.py) arrojó:
- **0 colisiones de nombres o identificadores** entre Batch 01, el Piloto y las suites de evaluación.
- **Similitud Léxica Jaccard Máxima:** **0.1556** (entre `train_31` y `gen_07` debido únicamente a términos comunes como `empty`, `append`, `pop`).
- **0% de superposición de código o aserciones de prueba.**

> [!NOTE]
> Como se especifica en los estándares de calidad de AURA CORE, las métricas de similitud léxica automática representan una cota superior de vocabulario compartido y no garantizan por sí solas la ausencia absoluta de contaminación semántica. La garantía sustantiva proviene de la ortogonalidad conceptual documentada en [`reports/inventario_training_batch_01.md`](file:///c:/Users/Guille/Downloads/IA/reports/inventario_training_batch_01.md), donde cada tarea aborda un problema algorítmico independiente.

---

## 5. Estado Final y Próximos Pasos

### Veredicto: **APTO**
El lote `datasets/training_pairs_batch_01.json` cumple íntegramente todos los requisitos de verificación en sandbox aislado, sensibilidad de mutantes, separación de datos y consistencia contractual.

**Recomendaciones para fases posteriores:**
1. Mantener ambos archivos independientes (`datasets/training_pairs_pilot.json` y `datasets/training_pairs_batch_01.json`) hasta contar con la autorización explícita para la unificación en un corpus consolidado de 40 ejemplos.
2. Proceder, bajo indicación del usuario, con el Lote 2 (hacia 60 ejemplos) o con la fase de formateo y preparación del pipeline de fine-tuning LoRA.
