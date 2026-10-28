# AURA CORE — Evaluación y Diseño de la Recuperación Selectiva de Ejemplos (RAG / ICL)

**Fecha:** 2026-10-26  
**Fase:** Implementación y Verificación Aislada del Recuperador de Ejemplos (Pre-Evaluación)  
**Módulo Implementado:** [`evals/selective_retriever.py`](file:///c:/Users/Guille/Downloads/IA/evals/selective_retriever.py)  
**Suite de Pruebas Unitarias:** [`evals/test_selective_retriever.py`](file:///c:/Users/Guille/Downloads/IA/evals/test_selective_retriever.py) (7/7 tests PASS)  
**Script Experimental A/B Preparado:** [`scratch/run_ab_selective_experiment.py`](file:///c:/Users/Guille/Downloads/IA/scratch/run_ab_selective_experiment.py)  
**Hashes SHA-256 Verificados e Invariables de los Datasets:**
- `datasets/training_pairs_pilot.json`: `7E1B43E291A2BF40023A5B78BFCDE2855EB48219678E28B2F92202DC38B8FB3B`
- `datasets/training_pairs_batch_01.json`: `FEFBF971771FA9F441815B37CA04B7C81429288C807CCCAE954219C0CA8DB671`

---

## 1. Resumen de la Implementación Aislada

En cumplimiento de las directivas técnicas, se desarrolló un recuperador determinista e interpretable de ejemplos canónicos basado en **BM25 con ponderación por categorías y descarte de términos genéricos** (`SelectiveExampleRetriever`), diseñado para operar como puente de In-Context Learning (ICL) sin modificar pesos ni requerir fine-tuning.

### Características Clave de la Arquitectura:
1. **Determinista y Libre de Cajas Negras:** No requiere bases de datos vectoriales opacas (evitando dependencias pesadas como ChromaDB, FAISS o modelos de embeddings adicionales). Emplea cálculo léxico-estructural con ponderación TF-IDF/BM25 optimizada para sintaxis de Python y contratos formales.
2. **Penalización por Divergencia de Dominio:** Modula los puntajes léxicos con un multiplicador de categoría ($1.35\times$ para alineación de problema, $0.80\times$ para penalizar falsos amigos que comparten palabras genéricas como `append`, `pop`, `dict` pero resuelven problemas dispares).
3. **Higiene Estricta de Prompts:** El contexto inyectado expone **exclusivamente** el contrato, la firma canónica y la solución de referencia verificada. Se excluyen rigurosamente las pruebas unitarias, código de mutantes, metadatos internos (`source`, `verified_at_iso`) y cualquier elemento de los benchmarks de evaluación.
4. **Acotamiento del Presupuesto de Contexto:** Límite configurable de ejemplos ($K \le 2-3$) y longitud máxima de caracteres (~3,500 caracteres, ~875 tokens), asegurando que el modelo mantenga amplio margen dentro de su ventana de contexto (8,192 tokens) para la generación de código y el diagnóstico.
5. **Interruptor de Reversibilidad Inmediata (Toggle):** La opción `enabled=False` desactiva instantáneamente la inyección, retornando al comportamiento Baseline sin costo de latencia.

---

## 2. Resultados de las Pruebas Unitarias del Recuperador

Se ejecutó la suite [`evals/test_selective_retriever.py`](file:///c:/Users/Guille/Downloads/IA/evals/test_selective_retriever.py), validando:
- **Carga de Corpus:** 40/40 pares cargados e indexados limpiamente desde los dos JSON originales.
- **Higiene de Contexto:** 0 apariciones de `test_`, `unittest`, `mutant` o metadatos internos en el bloque de contexto generado.
- **Prevención de Auto-Recuperación (Self-Retrieval):** Verificado que `exclude_task_id` impide que una tarea se recupere a sí misma.
- **Inmutabilidad Criptográfica:** Los hashes SHA-256 de los dos datasets originales se mantuvieron idénticos antes y después de todas las pruebas.
- **Resultado:** **7 / 7 pruebas aprobadas (100% OK, 0.034s).**

---

## 3. Diseño del Experimento A/B Controlado

El protocolo experimental queda implementado en [`scratch/run_ab_selective_experiment.py`](file:///c:/Users/Guille/Downloads/IA/scratch/run_ab_selective_experiment.py) para su ejecución cuando el usuario lo autorice:

### 3.1. Condiciones Idénticas de Control
- **Modelo:** `qwen2.5-coder-3b-instruct-q4_k_m.gguf` servido en el puerto experimental 8083.
- **Temperatura:** 0.0 (determinista).
- **Parámetros:** Max Tokens 1024, Contexto 8192, Prompt de Sistema V2.
- **Sandbox:** Ejecución y análisis AST exclusivamente en Debian 13 WSL2 (`isolated_runner.py`).
- **Suites de Prueba:**
  1. `evals/coding_tasks.json` (12 tareas de referencia).
  2. `evals/generalization_tasks.json` (8 tareas de generalización no vistas).

### 3.2. Comparación A vs B
- **Variante A (Baseline):** Generación con Prompt V2 estándar y reintento guiado por diagnóstico de error.
- **Variante B (Experimental RAG/ICL):** Misma metodología, pero incorporando en el primer intento hasta 2 patrones de referencia canónicos recuperados selectivamente del banco de 40 pares.

---

## 4. Instrucciones para la Ejecución Futura

Cuando se decida ejecutar la evaluación comparativa, los pasos a seguir son:

```powershell
# 1. Asegurar que el servidor experimental en puerto 8083 esté activo con el modelo 3B
# (o iniciarlo en segundo plano si no estuviera corriendo):
.\bin\llama-server.exe -m models\qwen2.5-coder-3b-instruct-q4_k_m.gguf --port 8083 -c 8192 -ngl 0

# 2. Ejecutar Variante A (Baseline) sobre la suite de codificación:
python scratch/run_ab_selective_experiment.py --mode A --tasks evals/coding_tasks.json --output experiments/ab_baseline_results.json

# 3. Ejecutar Variante B (Experimental ICL) sobre la suite de codificación:
python scratch/run_ab_selective_experiment.py --mode B --tasks evals/coding_tasks.json --output experiments/ab_icl_results.json

# 4. Repetir la comparación sobre la suite de generalización:
python scratch/run_ab_selective_experiment.py --mode A --tasks evals/generalization_tasks.json --output experiments/ab_gen_baseline_results.json
python scratch/run_ab_selective_experiment.py --mode B --tasks evals/generalization_tasks.json --output experiments/ab_gen_icl_results.json
```

---

## 5. Estado y Criterio de Cierre

- El módulo experimental independiente ha sido creado y probado rigurosamente.
- No se han modificado archivos de producción (`agent/`, `start_ai.bat`, `start.ps1`, puerto 8089).
- No se ha ejecutado la evaluación completa ni se han alterado los benchmarks.
- La ejecución se detiene a la espera de autorización explícita para lanzar el benchmark comparativo A/B.
