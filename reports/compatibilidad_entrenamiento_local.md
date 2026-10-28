# AURA CORE — Informe de Compatibilidad y Viabilidad de Entrenamiento Local

**Fecha:** 2026-10-26  
**Entorno Evaluado:** Windows 10 Pro (Host) / Debian 13 WSL2 (Sandbox de Ejecución)  
**Hardware Físico:** AMD Ryzen 5 2400G (4 núcleos / 8 hilos, arquitectura Zen 1 14nm), GPU integrada Radeon Vega 11 (VRAM compartida, sin aceleración CUDA nativa), 32 GB RAM DDR4, SSD C: con 31.6 GB libres.  
**Modelo en Inferencia:** `models/qwen2.5-coder-3b-instruct-q4_k_m.gguf` (2.10 GB) servido mediante `bin/llama-server.exe` (v0.7.0-dev build 11719).  
**Propósito:** Analizar la viabilidad técnica real de realizar fine-tuning con los 40 pares de datos verificados sin alterar el entorno operativo ni realizar suposiciones infundadas.

---

## 1. Auditoría del Entorno Técnico Real

### 1.1. Recursos de Hardware y Limitaciones Críticas
- **Procesador (CPU):** AMD Ryzen 5 2400G. Cuenta con 4 núcleos físicos y 8 hilos de ejecución. Carece de instrucciones AVX-512 (soporta AVX2, FMA3, SSE4.2). Su capacidad de procesamiento en punto flotante FP32/BF16 para backpropagation profundo es limitada.
- **Memoria RAM del Sistema:** 32 GB instalados (~30 GB visibles, ~10 GB libres en Windows en tiempo de reposo, ampliable cerrando aplicaciones a ~22 GB). En Debian WSL2 se dispone de hasta 23 GB de memoria asignada dinámicamente y 6 GB de swap.
- **Unidad Gráfica (GPU) y Aceleración:** La GPU Radeon Vega 11 carece de soporte CUDA. ROCm/HIP de AMD no tiene soporte oficial estable ni binarios precompilados de PyTorch para APUs Raven Ridge (gfx902) bajo Windows ni WSL2. Todo cálculo de gradientes debería ejecutarse obligatoriamente en CPU.
- **Espacio en Disco:** Unidad `C:\` con 31.6 GB disponibles. Descargar pesos completos en precisión estándar (FP16/BF16 ~6-7 GB), librerías de entrenamiento (~4-6 GB) y checkpoints intermedios consumiría entre el 40% y el 60% del espacio libre restante en disco.

### 1.2. Estado del Software y Formato de Pesos
- **Entorno Python en Windows:** Python 3.14.0 instalado (`C:\Users\Guille\AppData\Local\Programs\Python\Python314\python.exe`). PyTorch, Transformers y PEFT carecen actualmente de binarios oficiales estables para Python 3.14 (requieren típicamente Python 3.10 a 3.12).
- **Paquetes de Machine Learning:** `torch`, `transformers`, `peft`, `trl`, `datasets`, `bitsandbytes`, `unsloth` y `accelerate` **NO están instalados** ni en Windows ni en Debian WSL2.
- **Binarios de `llama.cpp`:** La carpeta `bin/` contiene binarios compilados de inferencia (`llama-server.exe`, `llama-cli.exe`, `llama-quantize.exe`, `llama-perplexity.exe`). **NO contiene el binario `llama-finetune.exe`**.
- **Formato del Modelo Actual:** `qwen2.5-coder-3b-instruct-q4_k_m.gguf` es un archivo cuantizado en enteros de 4 bits por bloque.
  > [!IMPORTANT]
  > **Incompatibilidad fundamental de entrenamiento:** Un modelo cuantizado en formato GGUF de 4 bits **no puede someterse a backpropagation de gradientes directamente** con las herramientas estándar de entrenamiento. El backpropagation requiere calcular y acumular gradientes en coma flotante (FP16, BF16 o FP32). QLoRA carga modelos en 4 bits pero utiliza el formato safetensors/Hugging Face mediante la librería `bitsandbytes` (la cual depende de GPU NVIDIA con CUDA). En CPU pura, no existe soporte de optimizadores cuantizados en 4 bits para entrenamiento.

---

## 2. Comparación Exhaustiva de Estrategias

A continuación se contrastan las 3 alternativas técnicas consideradas:

| Dimensión de Análisis | Alternativa 1: LoRA / QLoRA en CPU | Alternativa 2: llama.cpp `finetune` en CPU | Alternativa 3: Inferencia Guiada por Contrato + RAG + Reparación |
|---|---|---|---|
| **Mecanismo Central** | PEFT / LoRA sobre PyTorch CPU | Herramienta nativa C++ de `llama.cpp` | Inferencia congelada + Contexto estructurado + Loop de reparación |
| **Formato de Pesos Requerido** | Hugging Face safetensors (FP16/BF16, ~6.5 GB) | GGUF des-cuantizado a FP16/FP32 (~6.5 GB) | GGUF Q4_K_M actual (2.10 GB, ya instalado) |
| **Requisitos de Software Faltantes** | Python 3.11/3.12, PyTorch CPU, Transformers, PEFT (~4 GB) | Binario `llama-finetune.exe` compilado | **Ninguno** (entorno operativo 100% listo) |
| **Soporte de Cuantización (4 bits)** | **No** (QLoRA con `bitsandbytes` requiere CUDA) | **No** (`llama-finetune` requiere modelo base FP16/FP32) | **Sí** (usa el modelo Q4_K_M existente) |
| **Memoria RAM Estimada** | 16 - 22 GB RAM | 12 - 18 GB RAM | 3.5 - 4.5 GB RAM |
| **Tiempo de Entrenamiento Estimado** | ~14 - 28 horas (40 ejemplos, 3-5 épocas en Ryzen 2400G) | ~8 - 16 horas en CPU | **0 segundos** (cero entrenamiento) |
| **Riesgo de Regresión Catastrófica** | **Alto** (sobreajuste severo con 40 ejemplos) | **Alto** (divergencia de gradientes o pérdida de fluidez) | **Cero** (los pesos base permanecen intactos) |
| **Reversibilidad** | Media (requiere exportar LoRA y re-cuantizar) | Media (genera adaptador GGUF LoRA) | **100% Inmediata** (rollback por configuración) |
| **Impacto en Espacio en Disco** | -12 a -16 GB (pesos FP16 + venv + checkpoints) | -8 a -10 GB (pesos FP16 + checkpoint) | **0 GB adicionales** |

---

## 3. Análisis de Factibilidad y Cuellos de Botella

### 3.1. Cuello de Botella 1: Inexistencia de Hardware de Aceleración (No-CUDA)
Todo el ecosistema moderno de QLoRA (`bitsandbytes`, `unsloth`, FlashAttention-2) está estrictamente optimizado y vinculado a GPUs NVIDIA con núcleos Tensor. Entrenar en un Ryzen 5 2400G (CPU 4 núcleos) implica una tasa de procesamiento estimada inferior a 0.5 - 1.5 tokens/segundo durante la pasada hacia adelante y hacia atrás, lo que convierte cualquier ciclo de ajuste iterativo en un proceso prohibitivamente lento y propenso a inestabilidad térmica.

### 3.2. Cuello de Botella 2: Tamaño de Muestra Pequeño (40 Ejemplos)
El fine-tuning de un modelo de 3.000 millones de parámetros con solo 40 ejemplos presenta un **riesgo extremo de sobreajuste memorístico (overfitting)**:
- El modelo tiende a memorizar cadenas léxicas específicas de los 40 contratos en lugar de adquirir razonamiento algorítmico inductivo.
- Existe un riesgo elevado de **olvido catastrófico (catastrophic forgetting)**, donde el modelo degrada su capacidad de seguir instrucciones generales, redactar explicaciones o estructurar sintaxis variada.

### 3.3. Cuello de Botella 3: Dependencias y Espacio en Disco
El entorno host opera con Python 3.14 (incompatible con PyTorch compilado a la fecha) y 31.6 GB de disco libre. Configurar un entorno secundario con Python 3.11, PyTorch CPU y los pesos base FP16 de Qwen 2.5 Coder 3B dejaría la unidad de almacenamiento en niveles de espacio libre inferiores al 5%, comprometiendo la estabilidad del sistema operativo.

---

## 4. Conclusión Técnica

La ejecución de fine-tuning local (sea mediante PEFT/LoRA o `llama-finetune`) **no es recomendable ni técnicamente aconsejable en la configuración de hardware actual**.

Por el contrario, la estrategia más sólida, científicamente controlable y de cero riesgo para AURA CORE consiste en:
1. **Mantener los pesos del modelo intactos** en su cuantización óptima Q4_K_M.
2. **Utilizar los 40 pares verificados como banco de conocimiento y recuperación de patrones (Few-Shot / Contract-Guided Reasoning)** inyectados dinámicamente en el contexto del prompt según la categoría o similitud de la tarea.
3. **Continuar aprovechando el ciclo de reparación guiada por contrato**, que ya demostró mejoras sustanciales en las evaluaciones anteriores sin alterar un solo parámetro de la red.
