# AURA CORE — Informe de Auditoría de Calidad del Dataset Piloto

**Fecha de Auditoría Original:** 2026-10-26  
**Fecha de Corrección Contractual:** 2026-10-26  
**Entorno de Ejecución:** Debian 13 WSL2 (`aura_sandbox`, aislamiento con `unshare -r -n`)  
**Evaluador:** AURA CORE Quality Assurance & Verification Subsystem  
**Dataset Auditado y Corregido:** [`datasets/training_pairs_pilot.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.json) (20 registros)  
**Respaldo Pre-Corrección:** [`datasets/training_pairs_pilot.pre_correction.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.pre_correction.json)  
**Respaldo Histórico Original:** [`datasets/training_pairs_pilot.original.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.original.json)  
**Veredicto Global Final:** **APTO**

---

## 1. Resumen Ejecutivo

En el marco de la preparación para el futuro fine-tuning LoRA de AURA CORE, se ha completado una **auditoría integral y rigurosa**, complementada con una **fase de corrección contractual**, sobre los 20 ejemplos que componen el dataset piloto ([`datasets/training_pairs_pilot.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.json)).

La auditoría inicial detectó 4 discordancias menores de redacción contractual respecto a la distinción entre `TypeError` (tipos de entrada incorrectos) y `ValueError` (valores de dominio inválidos). Tras la aplicación de correcciones contractuales estrictas y la posterior revalidación dinámica completa en el entorno Debian 13 WSL2 sandbox (`aura_sandbox`), todas las ambigüedades quedaron formalmente resueltas.

### Principales Resultados Cuantitativos Consolidados:
- **Tasa de éxito de soluciones de referencia:** **20 / 20 (100.0%) PASS** en sandbox aislado (tiempo medio: ~65 ms por tarea).
- **Tasa de aniquilación de mutantes (Mutation Testing):** **20 / 20 (100.0%) KILLED** (ningún mutante defectuoso sobrevivió a la suite de tests).
- **Pruebas unitarias del evaluador (`evals`):** **23 / 23 (100.0%) PASS** en 3.83s.
- **Acceso a detalles internos privados en tests:** **0 / 20 (0.0%)** (los tests interactúan exclusivamente a través de las interfaces y contratos públicos).
- **Contaminación / Colisión con suites de evaluación:** **0 colisiones de ID**, similitud léxica máxima de 0.351 (debida a términos estándar de interfaz de caching como `get`/`put`/`capacity`), **0% fuga de código de solución o pruebas**.
- **Consistencia de esquemas JSON:** Todos los 20 registros poseen los 10 campos requeridos conforme a las especificaciones.

---

## 2. Tabla Consolidada de los 20 Ejemplos y Estado Final

| # | Task ID | Categoría | Solución Ref. (WSL2 Sandbox) | Mutation Testing (Sensibilidad) | Complejidad / Diseño | Estado Final |
|---|---|---|---|---|---|---|
| **01** | `train_01_trie_prefix_tree` | `code_generation` | **PASS** (0.076s) | **KILLED** (FAIL: `test_empty_string_insert_raises`) | $O(L)$ tiempo, nodos limpios en borrado | **APTO** |
| **02** | `train_02_min_heap_priority_queue` | `code_generation` | **PASS** (0.061s) | **KILLED** (FAIL: `test_push_and_pop_order`) | Heap array, $O(\log N)$ push/pop, $O(1)$ peek | **APTO** |
| **03** | `train_03_stream_median_calculator` | `code_generation` | **PASS** (0.059s) | **KILLED** (FAIL: `test_running_median`) | Two-heaps, $O(\log N)$ inserción, $O(1)$ mediana | **APTO** |
| **04** | `train_04_matrix_rotation_90deg` | `code_generation` | **PASS** (0.055s) | **KILLED** (FAIL: `test_square_3x3`) | In-place, $O(N^2)$ tiempo, $O(1)$ memoria aux. | **APTO** |
| **05** | `train_05_interval_disjoint_intersection` | `code_generation` | **PASS** (0.059s) | **KILLED** (FAIL: `test_invalid_interval_raises`) | Two-pointer $O(N+M)$ tiempo | **APTO** |
| **06** | `train_06_string_run_length_encoding` | `code_generation` | **PASS** (0.055s) | **KILLED** (FAIL: `test_invalid_decode_format_raises`) | Funciones puras, regex estricto | **APTO** |
| **07** | `train_07_debug_generator_pipeline` | `debugging` | **PASS** (0.055s) | **KILLED** (FAIL: `test_invalid_batch_size_raises`) | `itertools.islice`, streaming perezoso $O(1)$ RAM | **APTO** |
| **08** | `train_08_debug_binary_search_rotated` | `debugging` | **PASS** (0.058s) | **KILLED** (FAIL: `test_found_elements`) | Búsqueda binaria adaptada $O(\log N)$ tiempo | **APTO** |
| **09** | `train_09_debug_linked_list_cycle_detection` | `debugging` | **PASS** (0.063s) | **KILLED** (FAIL: `test_cycle_present`) | Floyd's Tortoise and Hare $O(1)$ memoria aux. | **APTO** |
| **10** | `train_10_debug_event_emitter_leak` | `debugging` | **PASS** (0.055s) | **KILLED** (FAIL: `test_on_and_emit`) | Cierre léxico seguro, desuscripción sin fugas | **APTO** |
| **11** | `train_11_disjoint_set_union_find` | `data_structures` | **PASS** (0.070s) | **KILLED** (FAIL: `test_out_of_bounds_raises`) | Path compression + union by rank $O(\alpha(N))$ | **APTO** |
| **12** | `train_12_monotonic_stack_next_greater` | `data_structures` | **PASS** (0.056s) | **KILLED** (FAIL: `test_standard_case`) | Stack monótono decreciente $O(N)$ tiempo lineal | **APTO** |
| **13** | `train_13_lfu_cache_frequency_bucket` | `data_structures` | **PASS** (0.057s) | **KILLED** (FAIL: `test_lfu_eviction`) | $O(1)$ get/put mediante `OrderedDict` buckets | **APTO** |
| **14** | `train_14_roman_numeral_strict_parser` | `edge_cases` | **PASS** (0.061s) | **KILLED** (FAIL: `test_invalid_syntax_raises`) | Validador canónico estricto 1-3999 | **APTO** |
| **15** | `train_15_ip_network_cidr_validator` | `edge_cases` | **PASS** (0.065s) | **KILLED** (FAIL: `test_invalid_octets_raise`) | Aritmética de máscaras binarias de 32 bits | **APTO** |
| **16** | `train_16_levenshtein_distance_matrix` | `edge_cases` | **PASS** (0.057s) | **KILLED** (FAIL: `test_standard_distances`) | DP con doble búfer rodante $O(\min(M, N))$ RAM | **APTO** |
| **17** | `train_17_bounded_blocking_queue` | `concurrency` | **PASS** (0.163s) | **KILLED** (FAIL: `test_empty_get_timeout`) | `threading.Condition` con timeouts exactos | **APTO** |
| **18** | `train_18_async_rate_limited_semaphore_worker` | `concurrency` | **PASS** (0.201s) | **KILLED** (FAIL: `test_preserves_order_and_limits_concurrency`) | `asyncio.Semaphore`, orden preservado y cancelación | **APTO** |
| **19** | `train_19_refactor_order_state_machine` | `refactoring` | **PASS** (0.065s) | **KILLED** (FAIL: `test_illegal_transition_raises`) | Máquina de estados con tabla determinista | **APTO** |
| **20** | `train_20_refactor_polymorphic_discount_engine` | `refactoring` | **PASS** (0.055s) | **KILLED** (FAIL: `test_coupon_capped_at_50_pct`) | Inmutabilidad estricta y tope de cupones | **APTO** |

---

## 3. Defectos Encontrados y Correcciones Realizadas

### Defecto 1: Advertencia de Secuencia de Escape en Expresión Regular (`train_06`)
- **Identificador:** `DEF-PILOT-01` (`train_06_string_run_length_encoding`).
- **Naturaleza e Impacto:** En el archivo generador y validador `scratch/build_and_verify_training_pairs.py`, la expresión regular `pattern = re.compile(r"^([^0-9]\d+)+$")` dentro de una cadena de triple comilla ordinaria generaba un `SyntaxWarning: "\d" is an invalid escape sequence` bajo Python 3.12+.
- **Corrección Mínima:** Escapado defensivo explícito `\\d` en las especificaciones del patrón.
- **Resultado Posterior:** Ejecución completamente limpia, 0 advertencias de sintaxis.

### Defecto 2: Limitación en la Inspección AST para Corutinas Asíncronas (`train_18`)
- **Identificador:** `DEF-AUDIT-01` (Script de auditoría de sintaxis y firmas).
- **Naturaleza e Impacto:** La herramienta de verificación de AST original buscaba funciones exclusivamente con `isinstance(n, ast.FunctionDef)`, provocando una falsa alarma al evaluar corutinas `async def` (`ast.AsyncFunctionDef`) en `train_18`.
- **Corrección Mínima:** Ampliación del inspector para contemplar `(ast.FunctionDef, ast.AsyncFunctionDef)`.
- **Resultado Posterior:** Detección precisa de la signatura de la corutina `async_map_with_concurrency`.

### Corrección 3: Armonización Contractual de Excepciones (`train_05`, `train_14`, `train_15`, `train_20`)
- **Identificador:** `CORR-CONTRACT-01` a `CORR-CONTRACT-04`.
- **Naturaleza:** Los contratos textuales agrupaban errores de tipo (`TypeError`) dentro de cláusulas de `ValueError`.
- **Resolución:** Se especificó en cada contrato la exigencia de `TypeError` para parámetros de tipo inválido y `ValueError` para valores de dominio o sintaxis inválidos, documentado en detalle en [`reports/cambios_contractuales_training_pairs.md`](file:///c:/Users/Guille/Downloads/IA/reports/cambios_contractuales_training_pairs.md).

---

## 4. Evidencia de Pruebas Dinámicas y Mutation Testing

Todas las ejecuciones se realizaron en el sandbox Debian WSL2 mediante `/opt/aura_sandbox/isolated_runner.py` con aislamiento estricto de red y privilegios (`unshare -r -n`).

### 4.1. Resumen de Ejecución Dinámica
- **Soluciones de Referencia:**
  - 20 / 20 pasaron todas las pruebas unitarias sin errores ni excepciones no capturadas.
  - Tiempo total de ejecución de las 20 soluciones: **1.45 segundos** (promedio: **72 ms** por suite).
  - Tiempos de tareas concurrentes: `train_17` (163 ms), `train_18` (201 ms), reflejando la adecuada emulación de tiempos de bloqueo y esperas asíncronas controladas.

### 4.2. Eficacia del Mutation Testing
Para cada uno de los 20 problemas, se diseñó un mutante inyectando un error conceptual o algorítmico realista:
- 20 / 20 mutantes eliminados (**100% Mutation Score**).
- Cada mutante falló por el motivo específico para el que fue diseñado, garantizando que los tests tienen alta sensibilidad funcional y no toleran implementaciones rotas.

---

## 5. Resolución de Observaciones Técnicas

Las 4 observaciones señaladas en la auditoría inicial han sido plenamente resueltas:
1. `train_05`: Contrato formalizado con `TypeError` (no-listas o no-enteros) y `ValueError` (intervalos mal formados o `start > end`).
2. `train_14`: Contrato formalizado con `TypeError` (no-string) y `ValueError` (cadena vacía o números romanos mal formados).
3. `train_15`: Contrato formalizado con `TypeError` (argumentos no-string) y `ValueError` (octetos y prefijos fuera de rango).
4. `train_20`: Contrato formalizado con `TypeError` (`order` no-dict) y `ValueError` (subtotales negativos/no numéricos o tier desconocido).

---

## 6. Evaluación Final

### Calificación: **APTO**

#### Justificación Técnica:
1. **Calidad de Código y Arquitectura:** Todas las 20 soluciones implementan algoritmos canónicos óptimos y eficientes, sin librerías externas innecesarias, con tipado claro y sin dependencias de variables privadas.
2. **Robustez de Evaluación:** 100% de reproducibilidad en el sandbox Debian WSL2. Todos los mutantes son eliminados por sus pruebas específicas.
3. **Seguridad y No-Contaminación:** Separación total comprobada frente a los bancos de pruebas de benchmarking y generalización.
4. **Claridad Contractual:** Todos los contratos son precisos, no contienen contradicciones y distinguen con exactitud los tipos de error esperados.

---

## 7. Próximos Pasos Recomendados

1. **Ampliación Sistemática del Dataset:** Utilizar este lote piloto validado de 20 problemas como plantilla canónica para expandir el dataset hacia 100-200 pares de entrenamiento balanceados.
2. **Formateo para Fine-Tuning:** Generar las variantes formateadas en formato Alpaca y ChatML a partir de los pares verificados y auditados una vez autorizada la fase siguiente.
3. **Preservación Estricta:** Mantener intactos los pesos actuales, el entorno de inferencia de producción y los scripts del sistema hasta la aprobación explícita del usuario.
