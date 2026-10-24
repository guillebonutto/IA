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

| Script | Propósito | Método de Inferencia |
| :--- | :--- | :--- |
| [`audit_prompt_ingestion.py`](audit_prompt_ingestion.py) | Barrido controlado de ingesta de prompts (256 a 4096 tokens). | Directo por C++ con `llama-bench.exe` en JSON. |
| [`benchmark_protocol.py`](benchmark_protocol.py) | Comparación de variables a 8 hilos (Flash Attention, formatos KV y contexto). | Servidor HTTP `llama-server.exe` en puerto 8082. |
| [`test_real_workload.py`](test_real_workload.py) | Medición de 4 cargas reales (chat corto, código, archivo de repo y multi-turno). | Servidor HTTP `llama-server.exe` en puerto 8089. |
| [`audit_ingestion_results.json`](audit_ingestion_results.json) | Resultados crudos con muestras en nanosegundos de la ingesta de prompts. | Salida JSON nativa de `llama-bench.exe`. |

---

## 3. Auditoría del Protocolo de Medición y Métricas

### A. Cómo se calcula `ttft_s` (Time to First Token)
* **En `test_real_workload.py`**:
  ```python
  ttft_s = prompt_ms / 1000.0 if prompt_ms > 0 else 0.0
  ```
* **Hallazgo metodológico**: Este valor proviene del campo `prompt_ms` devuelto internamente por `llama-server`. Representa **únicamente el tiempo de cálculo del prefill del prompt en el motor C++ (`llama_decode`)**.
* **Limitación**: Debido a que la llamada utilizó `"stream": False`, la conexión HTTP es sincrónica y bloqueante; el cliente no recibe el primer byte hasta que la respuesta entera ha sido generada. Por lo tanto, no mide el TTFT percibido por el usuario final (que en streaming incluiría la latencia de tokenización en servidor, serialización JSON y transmisión por socket TCP loopback).

### B. Cómo se obtienen `prompt_per_second` y `predicted_per_second`
* Son extraídos directamente del diccionario `timings` que `llama-server` incluye en la respuesta:
  $$\text{prompt\_per\_second} = \frac{\text{prompt\_n}}{\text{prompt\_ms} / 1000}$$
  $$\text{predicted\_per\_second} = \frac{\text{predicted\_n}}{\text{predicted\_ms} / 1000}$$
* En `llama-bench.exe`, los valores provienen del cálculo interno de GGML: `samples_ts` (tokens por segundo) y `samples_ns` (duración exacta en nanosegundos).

### C. Cómo se mide `total_elapsed`
* Se mide en Python envolviendo la llamada `urllib.request.urlopen`:
  ```python
  t0 = time.time()
  with urllib.request.urlopen(req, timeout=120) as resp:
      res = json.loads(resp.read().decode())
  total_elapsed = time.time() - t0
  ```
* Expresa en segundos de reloj de pared (`wall-clock time`) el tiempo total de la transacción HTTP.

### D. Reutilización de Caché KV en el Servidor (Slot Cache Reuse)
* `llama-server.exe` mantiene un caché de contexto en su ranura activa. Si una petición comparte un prefijo idéntico con la anterior (por ejemplo, el mensaje de sistema), el servidor **no reevalúa esos tokens**, sino que reutiliza los vectores ya calculados.
* **Sesgo detectado en Caso 1 de `test_real_workload.py`**:
  * En el Caso 1, el prompt textual tenía ~50 tokens, pero el servidor reportó `Prompt: 1 tokens` porque los tokens del mensaje de sistema ya estaban presentes en el caché del slot de una petición previa. Esto distorsionó el tiempo aparente de prefill de esa petición específica.
  * **Corrección**: En `llama-bench.exe`, cada repetición se ejecuta en un contexto limpio y prístino, eliminando cualquier sesgo de reutilización de caché.

### E. Conteo de Tokens en Archivos de Código
* En `test_real_workload.py`, el archivo de código se inyecta directamente como texto en el mensaje del usuario:
  ```python
  prompt_largo = f"Lee el siguiente codigo fuente del archivo watchdog.py y enumera las clases/funciones implementadas:\n\n```python\n{code_content}\n```"
  ```
* **No se asume equivalencia bytes = tokens**: El conteo real reportado por el tokenizador BPE de Qwen fue:
  * `agent/watchdog.py` (6.610 bytes en disco) = **1.509 tokens** totales procesados por el modelo (sumando plantilla ChatML y mensaje de sistema).
  * `agent/tools.py` (19.693 bytes en disco) = **~4.418 tokens** de código; al sumar el sistema y plantilla superó los 4.096 tokens configurados, arrojando `HTTP 400 Bad Request`.

---

## 4. Resultados del Benchmark Controlado de Ingesta (llama-bench)

Prueba ejecutada con [`audit_prompt_ingestion.py`](audit_prompt_ingestion.py) con **8 hilos constantes**, **FP16 KV-Cache**, **Flash Attention OFF (`-fa 0`)**, **`-b 512`** y **`-ub 128`** (3 repeticiones por longitud):

| Longitud Prompt | Corridas Ingesta `[1, 2, 3]` | Mediana Ingesta | Desv. Estándar | Tiempo Mediano Ingesta | Generación (16 tok) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| **256 tokens** | `[31.03, 29.29, 34.79] t/s` | **31.03 t/s** | ±2.81 t/s | **8.25 seg** | **13.51 t/s** (±0.37) |
| **512 tokens** | `[33.15, 34.25, 33.52] t/s` | **33.52 t/s** | ±0.56 t/s | **15.27 seg** | **14.74 t/s** (±0.23) |
| **1024 tokens** | `[32.74, 32.19, 31.79] t/s` | **32.19 t/s** | ±0.48 t/s | **31.82 seg** | **14.78 t/s** (±0.82) |
| **2048 tokens** | `[30.23, 29.82, 30.30] t/s` | **30.23 t/s** | ±0.26 t/s | **67.74 seg** | **14.08 t/s** (±1.36) |
| **4096 tokens** | `[26.83, 26.79, 19.36] t/s` | **26.79 t/s** | ±4.30 t/s | **152.89 seg** | **10.89 t/s** (±0.31) |

### Verificación Matemática
* 256 tokens / 8.25 seg = **31.03 t/s** (coincidencia exacta).
* 512 tokens / 15.27 seg = **33.53 t/s** (coincidencia con 33.52 ± 0.56 t/s).
* 1024 tokens / 31.82 seg = **32.18 t/s** (coincidencia con 32.19 ± 0.48 t/s).
* 2048 tokens / 67.74 seg = **30.23 t/s** (coincidencia exacta).
* 4096 tokens / 152.89 seg = **26.79 t/s** (coincidencia exacta).

### Hallazgo de la Ingesta
1. Hasta 1024 tokens, la ingesta es sumamente consistente a **~32-33 t/s**.
2. A partir de 2048 y 4096 tokens, la tasa decae a **~26.8 t/s** y la velocidad de generación posterior disminuye de **14.7 t/s a 10.9 t/s (-26%)**, debido a la mayor carga de atención sobre 4096 vectores previos.

---

## 5. Instrucciones para Reproducir las Pruebas

Para reproducir estas mediciones en cualquier máquina con Windows 10 y `llama.cpp`:

### Reproducir Ingesta Controlada (llama-bench)
```cmd
python scratch/audit_prompt_ingestion.py
```
*El script invoca `bin/llama-bench.exe` en formato JSON y guarda los resultados crudos en `scratch/audit_ingestion_results.json`.*

### Reproducir Protocolo de Comparación de Servidor (8 hilos, FA, KV-Cache)
```cmd
python scratch/benchmark_protocol.py
```

### Reproducir Evaluación de Cargas Reales
1. Iniciar el servidor local:
   ```cmd
   bin\llama-server.exe -m models\qwen2.5-coder-3b-instruct-q4_k_m.gguf -c 4096 -t 8 -tb 8 -b 512 -ub 128 -fa off -np 1 --port 8089 --host 127.0.0.1
   ```
2. Ejecutar el evaluador:
   ```cmd
   python scratch/test_real_workload.py
   ```

---

## 6. Recomendación Técnica: `-c 4096` frente a `-c 8192`

* **Impacto en RAM**:
  * `-c 4096`: **3.316 MB** de RAM residente (`WorkingSet`).
  * `-c 8192`: **3.420 MB** de RAM residente (`WorkingSet`).
  * El incremento es de apenas **104 MB de RAM**, completamente asumible en un sistema con 32 GB.
* **Riesgo Operativo**:
  * Un servidor con `-c 4096` fallará con `HTTP 400 Bad Request` al intentar inspeccionar archivos de código de más de ~3.000 tokens (como `tools.py` que requiere ~4.400 tokens + margen de respuesta).
* **Conclusión**:
  * Se recomienda configurar **`-c 8192`** en los lanzadores para garantizar compatibilidad con archivos de código extensos.
  * Para el uso cotidiano, se recomienda estructurar las consultas para que los prompts no superen los 1000–1500 tokens siempre que sea posible, evitando tiempos de prefill superiores a los 30–45 segundos.
