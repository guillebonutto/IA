# AURA CORE — Inventario y Justificación de Diversidad de Tareas (Batch 01)

**Fecha:** 2026-10-26  
**Lote:** Lote 1 de Ampliación (`datasets/training_pairs_batch_01.json`)  
**Cantidad:** 20 tareas independientes (`train_21` a `train_40`)  
**Dataset Piloto Aprobado (SHA-256):** `7E1B43E291A2BF40023A5B78BFCDE2855EB48219678E28B2F92202DC38B8FB3B`  
**Estado:** INVENTARIO APROBADO PREVIO A IMPLEMENTACIÓN

---

## 1. Principios de Diseño y Ortogonalidad

Para garantizar que el modelo aprenda capacidades de programación generalizables y robustas sin memorización ni redundancia:
1. **Ortogonalidad Algorítmica:** Ninguna tarea duplica la estructura de datos o técnica nuclear de las 20 tareas piloto ni de los 20 problemas de evaluación (`coding_tasks.json` y `generalization_tasks.json`).
2. **Distribución Equilibrada de Habilidades:** Se distribuyen 20 problemas en 6 áreas clave:
   - **Generación de Código Canónico (`code_generation`):** 5 tareas.
   - **Depuración y Corrección de Bugs Sutíles (`debugging`):** 4 tareas.
   - **Estructuras de Datos y Algoritmos Avanzados (`data_structures`):** 4 tareas.
   - **Manejo Estricto de Casos Límite y Parsing (`edge_cases`):** 3 tareas.
   - **Concurrencia, Asincronía y Primitivas de Sincronización (`concurrency`):** 2 tareas.
   - **Refactorización y Arquitectura Limpia (`refactoring`):** 2 tareas.
3. **Contratos Inequívocos:** Separación estricta entre `TypeError` (tipos incompatibles) y `ValueError` (valores de dominio inválidos), eliminando las ambigüedades identificadas en el piloto.
4. **Validación Dual:** Cada tarea cuenta con su suite de pruebas unitarias y al menos un mutante defectuoso representativo para validar la sensibilidad en sandbox Debian WSL2.

---

## 2. Inventario Detallado de las 20 Tareas del Lote 1

### A. Generación de Código (`code_generation`) — 5 tareas

1. **`train_21_binary_tree_diameter`**
   - **Problema:** Cálculo del diámetro máximo (camino más largo entre dos nodos cualesquiera) en un árbol binario en $O(N)$ tiempo y $O(H)$ memoria.
   - **Distinción:** Árboles binarios y recursión con acumulación de estado global/post-orden.
   - **Firma:** `def binary_tree_diameter(root: TreeNode | None) -> int`

2. **`train_22_k_way_sorted_merge_generator`**
   - **Problema:** Fusión de $K$ flujos/iteradores ordenados en un único generador perezoso ordenado usando Min-Heap en $O(N \log K)$ tiempo y $O(K)$ espacio en memoria.
   - **Distinción:** Streaming perezoso de múltiples generadores sin cargar listas completas en memoria.
   - **Firma:** `def merge_k_sorted_streams(*iterables)`

3. **`train_23_sliding_window_maximum`**
   - **Problema:** Encontrar el valor máximo en cada ventana deslizante de tamaño $k$ en una secuencia numérica usando deque monótono en $O(N)$ tiempo lineal estricto.
   - **Distinción:** Deque monótono de dos extremos, ventana dinámica.
   - **Firma:** `def max_sliding_window(nums: list[int | float], k: int) -> list[int | float]`

4. **`train_24_canonical_json_serializer`**
   - **Problema:** Serializador determinista canónico de JSON según RFC 8785 (claves ordenadas lexicográficamente de forma recursiva, sin espacios superfluos, float con formato canónico).
   - **Distinción:** Serialización determinista y hashing criptográfico reproducible.
   - **Firma:** `def canonical_json_dumps(obj) -> str`

5. **`train_25_bloom_filter_bitarray`**
   - **Problema:** Filtro probabilístico Bloom Filter desde cero usando múltiples funciones hash (`hashlib.sha256`) y máscara de bits con tamaño y conteo de hashes parametrizado.
   - **Distinción:** Estructura probabilística, membership queries, ausencia de falsos negativos.
   - **Firma:** `class BloomFilter: def add(self, item: str) -> None; def __contains__(self, item: str) -> bool`

---

### B. Depuración de Código (`debugging`) — 4 tareas

6. **`train_26_debug_flatten_tree_preorder`**
   - **Problema:** Aplanar un árbol binario a una lista enlazada in-place siguiendo el recorrido pre-orden (Right-to-Left post-order o manipulación de punteros Morris/Right).
   - **Defecto a Depurar:** Sobrescribir `root.right` antes de visitar el subárbol izquierdo provocando pérdida del puntero original.
   - **Firma:** `def flatten_binary_tree(root: TreeNode | None) -> None`

7. **`train_27_debug_dag_longest_path`**
   - **Problema:** Encontrar la longitud del camino más largo en un Grafo Acíclico Dirigido (DAG) con orden topológico y programación dinámica.
   - **Defecto a Depurar:** Relajación incorrecta de aristas o ciclicidad no validada en grafo no DAG.
   - **Firma:** `def dag_longest_path(num_nodes: int, edges: list[tuple[int, int, int]]) -> int`

8. **`train_28_debug_rate_limited_batch_retry`**
   - **Problema:** Función wrapper de reintento con backoff exponencial con jitter para llamadas fallidas por rate-limiting.
   - **Defecto a Depurar:** Mutación de listas de excepciones o backoff acumulado infinito sin tope (`max_backoff`).
   - **Firma:** `def retry_with_backoff(operation: callable, max_attempts: int = 3, base_delay: float = 0.1, max_delay: float = 2.0)`

9. **`train_29_debug_concurrent_counter_deadlock`**
   - **Problema:** Estructura de cuentas bancarias y transferencias thread-safe con dos bloqueos (`threading.Lock`) evitando deadlocks mediante ordenamiento canónico de adquisición de locks.
   - **Defecto a Depurar:** Adquisición de locks en orden dependiente del emisor/receptor causando deadlock cuando A transfiere a B y B transfiere a A simultáneamente.
   - **Firma:** `def safe_account_transfer(account_a, account_b, amount: float) -> bool`

---

### C. Estructuras de Datos y Algoritmos (`data_structures`) — 4 tareas

10. **`train_30_fenwick_tree_binary_indexed_tree`**
    - **Problema:** Binary Indexed Tree (Fenwick Tree) para consultas de suma de prefijos en $O(\log N)$ y actualizaciones puntuales en $O(\log N)$.
    - **Distinción:** Aritmética de bits `x & (-x)` y sumas de rango acumulativas.
    - **Firma:** `class FenwickTree: def update(self, idx: int, delta: int) -> None; def query(self, idx: int) -> int; def range_query(self, left: int, right: int) -> int`

11. **`train_31_doubly_linked_list_deque`**
    - **Problema:** Cola de doble extremo (Deque) implementada sobre lista doblemente enlazada con nodos centinela (head y tail dummies) en $O(1)$ amortizado para todas las operaciones.
    - **Distinción:** Punteros dobles (`prev`, `next`), centinelas y gestión de memoria.
    - **Firma:** `class DoublyLinkedDeque: def append(self, val); def appendleft(self, val); def pop(self); def popleft(self); def __len__(self) -> int`

12. **`train_32_radix_tree_compressed_trie`**
    - **Problema:** Árbol de prefijos comprimido (Radix Tree / Patricia Trie) donde los nodos con un solo hijo se colapsan compartiendo subcadenas.
    - **Distinción:** Partición y división de prefijos comunes en aristas.
    - **Firma:** `class RadixTree: def insert(self, word: str) -> None; def search(self, word: str) -> bool; def starts_with(self, prefix: str) -> bool`

13. **`train_33_interval_tree_point_query`**
    - **Problema:** Árbol de intervalos para consultar en $O(\log N + K)$ todos los intervalos que solapan con un punto dado $x$.
    - **Distinción:** Segmentación y búsqueda en árboles ordenados por punto medio.
    - **Firma:** `class IntervalTree: def __init__(self, intervals: list[tuple[int, int]]); def query_point(self, point: int) -> list[tuple[int, int]]`

---

### D. Casos Límite y Parsing Estricto (`edge_cases`) — 3 tareas

14. **`train_34_semver_expression_matcher`**
    - **Problema:** Evaluador estricto de rangos SemVer (ej. `>=1.2.0 <2.0.0`, `^1.2.3`, `~1.2.0`, `*`).
    - **Distinción:** Rangos comparativos de dependencias de software con sintaxis de caret y tilde.
    - **Firma:** `def match_semver_range(version: str, constraint: str) -> bool`

15. **`train_35_safe_nested_path_extractor`**
    - **Problema:** Extractor robusto de rutas anidadas con sintaxis estilo JSONPath / dot-notation con soporte de arrays (ej. `"users[0].addresses.primary.zip"`).
    - **Distinción:** Parsing léxico de corchetes, claves escapadas y retornos de `default` sin excepciones.
    - **Firma:** `def extract_nested_path(data: dict | list, path: str, default=None)`

16. **`train_36_cron_schedule_next_occurrence`**
    - **Problema:** Parser y evaluador de expresiones Cron estándar de 5 campos (minuto, hora, día del mes, mes, día de la semana) calculando el siguiente timestamp UTC exacto.
    - **Distinción:** Rangos (`-`), pasos (`/`), listas (`,`) y asteriscos en lógica de tiempo.
    - **Firma:** `def get_next_cron_run(cron_expr: str, current_time: datetime) -> datetime`

---

### E. Concurrencia y Asincronía (`concurrency`) — 2 tareas

17. **`train_37_async_debounced_coroutine`**
    - **Problema:** Decorador / función debouncer asíncrona (`asyncio`) que pospone la ejecución de una corutina hasta que haya transcurrido un periodo de inactividad de $N$ segundos.
    - **Distinción:** `asyncio.TimerHandle` / `asyncio.sleep`, cancelación de tareas previas no resueltas.
    - **Firma:** `class AsyncDebouncer: def __init__(self, wait_seconds: float); async def call(self, coro_func: callable, *args, **kwargs)`

18. **`train_38_thread_pool_barrier_synchronizer`**
    - **Problema:** Primitiva de sincronización tipo Barrier (barrera cíclica) usando `threading.Condition` que bloquea a un conjunto de $N$ threads hasta que todos hayan llegado al punto de encuentro.
    - **Distinción:** Fases cíclicas, reseteo seguro y timeouts.
    - **Firma:** `class CyclicBarrier: def __init__(self, parties: int); def wait(self, timeout: float = None) -> int`

---

### F. Refactorización y Arquitectura (`refactoring`) — 2 tareas

19. **`train_39_refactor_pipeline_middleware_chain`**
    - **Problema:** Refactorizar un procesamiento monolítico en una cadena de middlewares componibles (patrón Chain of Responsibility / Onion Pipeline) con soporte para paso de contexto y control de flujo (`next()`).
    - **Distinción:** Composición de funciones, inversión de control y aislamiento de mutaciones de contexto.
    - **Firma:** `class Pipeline: def use(self, middleware: callable) -> 'Pipeline'; def execute(self, initial_context: dict) -> dict`

20. **`train_40_refactor_specification_filter_engine`**
    - **Problema:** Motor de filtrado de colecciones de datos basado en el patrón Specification (combinadores booleanos `AndSpecification`, `OrSpecification`, `NotSpecification`, `AttributeEqualsSpecification`).
    - **Distinción:** Composición polimórfica de predicados desacoplada de la estructura de datos.
    - **Firma:** `class Specification: def is_satisfied_by(self, item) -> bool; def __and__(self, other); def __or__(self, other); def __invert__(self)`

---

## 3. Matriz de No-Contaminación con Benchmarks y Piloto

| ID Tarea Batch 01 | Concepto Nuclear | Tarea Más Cercana en Piloto / Eval | Diferenciador Algorítmico / Arquitectural |
|---|---|---|---|
| `train_21` | Diámetro Árbol Binario | `eval: task_08` (Cyclomatic) / `pilot: train_01` (Trie) | Árbol binario post-orden vs Trie de strings / complejidad ciclomática |
| `train_22` | K-Way Merge Streams | `gen: gen_06` (Task Pool) / `pilot: train_02` (MinHeap) | Generador perezoso streaming multi-fuente vs estructura heap estática |
| `train_23` | Sliding Window Maximum | `eval: task_02` (Rate Limiter) / `pilot: train_12` (Monotonic Stack) | Deque monótono de dos extremos en ventana fija vs stack de próximo mayor |
| `train_24` | Canonical JSON RFC 8785 | `eval: task_03` (Flatten JSON) / `gen: gen_02` (Deep Merge) | Ordenamiento canónico recursivo determinista vs aplanamiento con separador |
| `train_25` | Bloom Filter Bitarray | Ninguna | Estructura de datos probabilística con hashes criptográficos independientes |
| `train_26` | Flatten Tree Preorder | `pilot: train_09` (Cycle detection) | Mutación de punteros de árbol in-place a lista enlazada vs Floyd cycle |
| `train_27` | DAG Longest Path | `gen: gen_08` (Topological sort) | Programación dinámica sobre DAG pesado vs orden topológico simple |
| `train_28` | Exponential Backoff Jitter | `gen: gen_03` (Retry Decorator) | Backoff exponencial con jitter aleatorio y tope estricto de retardo |
| `train_29` | Transfer Lock Ordering | `pilot: train_17` (Bounded Queue) | Prevención de deadlocks por orden canónico de IDs de locks vs condición de cola |
| `train_30` | Fenwick Tree | Ninguna | Árbol binario indexado con operaciones `x & -x` para suma de prefijos $O(\log N)$ |
| `train_31` | Doubly Linked Deque | `gen: gen_07` (Circular buffer) | Punteros dobles con centinelas $O(1)$ sin tamaño fijo vs array circular estático |
| `train_32` | Radix Compressed Trie | `pilot: train_01` (Trie) | Trie comprimido por aristas compactadas vs Trie estándar carácter a carácter |
| `train_33` | Interval Tree Point Query | `pilot: train_05` (Interval Intersect) | Estructura de árbol de búsqueda de intervalos para puntos vs two-pointer en pares |
| `train_34` | SemVer Expression Matcher | `eval: task_07` (SemVer Comparator) | Evaluador de rangos complejos (`^`, `~`, `>= <`) vs comparación simple de 2 versiones |
| `train_35` | Safe Nested Path Extractor | `eval: task_03` (Flatten JSON) | Extractor de consultas con índices de array `[i]` vs flatten lineal completo |
| `train_36` | Cron Next Occurrence | Ninguna | Parser y proyector de calendario temporal en formato Cron de 5 campos |
| `train_37` | Async Debouncer | `eval: task_09` (Async Batcher) | Debounce con cancelación de timers y atraso dinámico vs batching paralelo |
| `train_38` | Cyclic Barrier Sync | `pilot: train_17` (Blocking Queue) | Barrera de sincronización multi-hilo con fases cíclicas vs cola FIFO de datos |
| `train_39` | Pipeline Middleware Chain | `pilot: train_19` (State Machine) | Cadena de responsabilidad Onion con control `next()` vs tabla de transiciones FSM |
| `train_40` | Specification Engine | `pilot: train_20` (Discount Engine) | Patrón de diseño Specification con álgebra booleana vs cálculo directo de reglas |

---
*Fin del inventario técnico y justificación de diversidad de Batch 01.*
