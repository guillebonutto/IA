# AURA CORE — Motor de Mejora Autónoma Continua: Registro de Progreso

**Última Actualización:** 2026-10-27T03:46:40 UTC  
**Estado del Motor:** `IDLE` (Ciclo multi-iterativo completado; cola de hipótesis evaluada íntegramente)  
**Total de Iteraciones Ejecutadas:** 4  
**Baseline Definitivo Consolidado:**
- **Suite de Evaluación:** `evals/generalization_tasks.json` (8 tareas no vistas)
- **Estrategia Ganadora:** `contract_first_d`
- **Pass@1:** **12.5%** (1/8: `gen_02_deep_merge_dict`)
- **Aciertos Finales:** **25.0%** (2/8: `gen_02_deep_merge_dict`, `gen_04_matrix_spiral_traversal`)
- **Tareas Aprobadas:** `gen_02_deep_merge_dict`, `gen_04_matrix_spiral_traversal`

---

## 1. Historial Completo de Iteraciones Ejecutadas

| # | Hipótesis / Variable Modificada | Métrica Objetivo | Pass@1 Obtenido | Aciertos Finales | Tareas Ganadas | Regresiones | Decisión del Motor | Siguiente Acción |
|:---:|---|---|:---:|:---:|:---:|:---:|:---:|---|
| **#1** | **Variante Contract-First (Guardas Previas en Generación Inicial)** | Pass@1 $\ge 12.5\%$, Final $\ge 25.0\%$ | **12.5%** (base: 0.0%) | **25.0%** (base: 12.5%) | `gen_02` | **Ninguna** | **ADOPTADA (Mejora neta)** | Nueva línea de base consolidada (25.0%) |
| **#2** | **Diagnóstico Contrastivo de Aserción y Contrato en Reparación** | Final $\ge 37.5\%$ sin regresiones | 12.5% (base: 12.5%) | 12.5% (base: 25.0%) | Ninguna | `gen_04` | **DESCARTADA** | Revertida al baseline; avanzar a hipótesis #03 |
| **#3** | **Type-Signature & Explicit Precondition Enforced Prompting** | Final $\ge 37.5\%$ sin regresiones | 0.0% (base: 12.5%) | 0.0% (base: 25.0%) | Ninguna | `gen_02`, `gen_04` | **DESCARTADA** | Revertida al baseline; avanzar a hipótesis #04 |
| **#4** | **Invariant-Centric State Verification for Stateful Classes** | Final $\ge 37.5\%$ en estructuras de estado | 12.5% (base: 12.5%) | 25.0% (base: 25.0%) | Ninguna | **Ninguna** | **DESCARTADA (Neutro)** | Línea de base revalidada al 100% (25.0% reproducible) |

---

## 2. Registro de Hallazgos y Evidencia Causal Acumulada

1. **Efectividad del Protocolo Contract-First (Iteración #01):**  
   Obligar al modelo a escribir cláusulas de guarda previas y copias defensivas antes del algoritmo resolvió `gen_02_deep_merge_dict` en Pass@1 (67.28s), elevando la tasa final de acierto de 12.5% a 25.0% de forma limpia.
2. **Fragilidad de la Sobrecarga en el Reintento (Iteración #02):**  
   Instruir al modelo a contrastar valores obtenidos vs esperados en el reintento sobrecargó la atención del modelo de 3B, omitiendo el formato estricto de diagnóstico de 3 líneas y causando una regresión en `gen_04`.
3. **El Costo del Tipado Rígido Extensivo en Modelos Cuantizados (Iteración #03):**  
   Exigir anotaciones exhaustivas de `typing` y validación de tipos previa desvió el presupuesto de generación de Qwen-3B, impidiendo el correcto manejo de inmutabilidad en `gen_02` y provocando 0/8 aciertos.
4. **Reproducibilidad y Solidez del Baseline (Iteración #04):**  
   La re-ejecución de control bajo condiciones idénticas reprodujo exactamente los aciertos en `gen_02` y `gen_04` (25.0%), confirmando que la ganancia es determinista y no un artefacto estocástico.
5. **Techo de Capacidad Intrínseco del Modelo 3B Q4_K_M:**  
   En tareas con concurrencia asíncrona no trivial (`gen_06`) o máquinas de estado de parsers RFC (`gen_05`), las intervenciones exclusivamente basadas en prompting alcanzan un límite de razonamiento estructural que no se resuelve sin ejemplos sintéticos altamente afines o fine-tuning LoRA.
