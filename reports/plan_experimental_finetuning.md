# AURA CORE — Plan Experimental de Evaluación y Preparación de Datos

**Fecha:** 2026-10-26  
**Fase:** Preparación y Diseño Experimental (Sin Ejecución de Entrenamiento)  
**Corpus de Datos Analizado:** 40 pares verificados (`datasets/training_pairs_pilot.json` + `datasets/training_pairs_batch_01.json`)  
**Hashes SHA-256 Verificados e Invariables:**
- Piloto: `7E1B43E291A2BF40023A5B78BFCDE2855EB48219678E28B2F92202DC38B8FB3B`
- Batch 01: `FEFBF971771FA9F441815B37CA04B7C81429288C807CCCAE954219C0CA8DB671`

---

## 1. Justificación y Recomendación Estratégica

Tras el análisis de compatibilidad de hardware y software documentado en [`reports/compatibilidad_entrenamiento_local.md`](file:///c:/Users/Guille/Downloads/IA/reports/compatibilidad_entrenamiento_local.md), se concluye que ejecutar un entrenamiento de pesos (LoRA/QLoRA o CPU) sobre el Ryzen 5 2400G carente de CUDA y con 40 ejemplos presenta un balance costo-beneficio marcadamente desfavorable:
- Requiere 12-16 GB de descargas (pesos FP16 + PyTorch CPU).
- Demoraría entre 14 y 28 horas de CPU al 100% de carga.
- Conlleva alto riesgo de olvido catastrófico y sobreajuste.

### Recomendación Central:
**Adoptar un enfoque de "Contract-Guided Contextual In-Context Learning (ICL) + Reparación Determinista":**
En lugar de modificar los pesos de la red, los 40 pares verificados se emplean como **banco canónico de contratos y patrones de implementación** inyectados dinámicamente en tiempo de inferencia según la similitud conceptual de la tarea solicitada. Esto preserva la fluidez general del modelo base Qwen 2.5 Coder 3B Instruct, elimina el riesgo de regresión en tareas no relacionadas y permite reversibilidad instantánea.

No obstante, para garantizar la máxima rigurosidad científica, este documento define formalmente:
1. El protocolo de conversión de datos hacia ChatML y Alpaca (en caso de autorización futura de entrenamiento).
2. El protocolo de evaluación experimental controlada para comparar el Baseline contra cualquier variante futura.

---

## 2. Preparación y Tratamiento de los 40 Pares de Datos

### 2.1. Preservación Estricta de las Fuentes
- Los archivos originales [`datasets/training_pairs_pilot.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_pilot.json) y [`datasets/training_pairs_batch_01.json`](file:///c:/Users/Guille/Downloads/IA/datasets/training_pairs_batch_01.json) **se mantienen 100% intactos**.
- No se realiza concatenación automática en caliente. La eventual generación de datasets de entrenamiento formateados se realizará hacia archivos nuevos claramente versionados (ej. `datasets/finetune_chatml_40.json`).

### 2.2. Esquema de Conversión Canónica (ChatML para Qwen 2.5)
Dado que Qwen 2.5 Coder fue pre-entrenado y ajustado con la plantilla ChatML (`<|im_start|>system...<|im_end|>`), el mapeo determinista para cada uno de los 40 pares se define así:

```json
{
  "messages": [
    {
      "role": "system",
      "content": "Eres un asistente de programación experto en Python. Tu objetivo es generar soluciones de alta calidad, robustas, eficientes y que cumplan estrictamente el contrato especificado, distinguiendo con precisión TypeError y ValueError, sin dependencias externas innecesarias."
    },
    {
      "role": "user",
      "content": "Implementa una solución en Python que cumpla estrictamente el siguiente contrato e interfaz:\n\n{contract}\n\nFirma esperada:\n```python\n{input_signature}\n```"
    },
    {
      "role": "assistant",
      "content": "```python\n{reference_solution}\n```"
    }
  ]
}
```

#### Reglas de Higiene de Datos:
1. **Exclusión Absoluta de Metadatos Internos:** Los campos `tests`, `verification_status`, `source`, `verified_at_iso` y descripciones de mutantes **nunca** se incluyen en el contenido de entrada o salida para evitar fuga de aserciones de prueba o distorsión de la distribución de entrenamiento.
2. **Cero Plagio de Benchmarks:** Los benchmarks `evals/coding_tasks.json` (12 tareas) y `evals/generalization_tasks.json` (8 tareas) están estrictamente excluidos de los datos de entrenamiento.

### 2.3. Estrategia de Partición (Train / Validation)
Con 40 ejemplos totales, una partición clásica (ej. 80/20) arroja 32 ejemplos de entrenamiento y 8 de validación interna:
- La validación sobre 8 ejemplos del mismo banco sintético es útil para monitorear convergencia de función de pérdida (`loss`), pero **no demuestra generalización algorítmica**.
- Por ello, la evaluación de generalización real debe recaer obligatoriamente sobre suites no vistas (`generalization_tasks.json`).

---

## 3. Protocolo de Evaluación Experimental Controlada

Para evaluar de forma justa y reproducible cualquier variante (sea Fine-Tuning LoRA o In-Context Retrieval) frente al Baseline, se fija el siguiente protocolo:

### 3.1. Grupos de Comparación
1. **Grupo A — Baseline:**
   - Modelo: `qwen2.5-coder-3b-instruct-q4_k_m.gguf` original sin modificar.
   - Prompt: Prompt V2 / Contract-Guided Prompt estándar.
   - Parámetros: Temperatura 0.2, Top-P 0.95, Max Tokens 2048, Contexto 8192, Seed fija (42).
2. **Grupo B — Variante Experimental (Fine-Tuning o Retrieval):**
   - Mismas condiciones de inferencia, mismo seed, mismo servidor (`llama-server`), mismos límites de tiempo (timeout 10.0s) y mismo evaluador AST/sandbox WSL2 (`isolated_runner.py`).

### 3.2. Métricas y Desglose por Fases
Para evitar conclusiones engañosas basadas en pequeñas fluctuaciones de 1 o 2 aciertos en suites pequeñas:
1. **Tasa de Acierto en Generación Inicial (Pass@1 Initial):** Medida en el primer intento sin asistencia.
2. **Tasa de Reparación Guiada (Repair Success Rate):** Porcentaje de tareas inicialmente fallidas que se corrigen con el segundo intento estructurado.
3. **Tasa de Acierto Final (Pass@Final):** Rendimiento total tras el presupuesto máximo de 2 intentos.
4. **Desglose por Categorías:** Reporte segmentado (`code_generation`, `debugging`, `edge_cases`, `refactoring`, `concurrency`, `data_structures`).
5. **Índice de Generalización:** Tasa de éxito específica en `evals/generalization_tasks.json` (8 tareas no vistas) para verificar si la intervención produce mejoras transferibles o meramente sobreajuste local.

### 3.3. Criterios Objetivos para Decidir si Vale la Pena el Fine-Tuning
Un experimento de fine-tuning solo se considerará exitoso y digno de ser adoptado si cumple conjuntamente:
- **No-Regresión en Tareas Básicas:** Cero degradación en las tareas que el baseline ya resolvía correctamente.
- **Mejora Estadísticamente Apreciable:** Incremento neto de al menos $\ge 2$ tareas adicionales resueltas en la suite de generalización sin requerir reparación.
- **Preservación de Explicaciones y Formato:** El modelo no debe colapsar generando bucles infinitos, código truncado o perdiendo la capacidad de seguir instrucciones complejas.

---

## 4. Comandos de Ejecución Futura (Solo si se autoriza entrenamiento)

Si en el futuro se dispusiera de una máquina con GPU dedicada (ej. NVIDIA RTX con CUDA) o se resolviera ejecutar en CPU con plena conciencia de los tiempos:

```bash
# 1. Preparar dataset formateado en JSONL ChatML
python scratch/format_dataset_chatml.py --input-pilot datasets/training_pairs_pilot.json --input-batch datasets/training_pairs_batch_01.json --output datasets/training_pairs_chatml_40.jsonl

# 2. Comando conceptual de entrenamiento LoRA (en entorno con PyTorch y GPU):
# python -m trl.sft_trainer \
#   --model_name_or_path "Qwen/Qwen2.5-Coder-3B-Instruct" \
#   --train_dataset_path "datasets/training_pairs_chatml_40.jsonl" \
#   --learning_rate 2e-4 \
#   --lora_r 16 \
#   --lora_alpha 32 \
#   --lora_target_modules "q_proj,k_proj,v_proj,o_proj,gate_proj,up_proj,down_proj" \
#   --per_device_train_batch_size 1 \
#   --gradient_accumulation_steps 4 \
#   --num_train_epochs 3 \
#   --output_dir "models/checkpoints_lora_qwen_3b"

# 3. Evaluación comparativa automática en AURA CORE:
python evals/run_comparative_experiment.py --baseline-port 8089 --experimental-port 8083 --eval-suite evals/generalization_tasks.json
```

---
*Fin del plan experimental de preparación. No se han iniciado entrenamientos ni modificado archivos de producción.*
