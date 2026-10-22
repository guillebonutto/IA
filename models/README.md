# Modelos GGUF (AURA CORE)

Esta carpeta está destinada a almacenar los modelos cuantizados en formato `.gguf` para inferencia local con `llama.cpp`.

Debido a su tamaño (>1 GB), los archivos `.gguf` no se almacenan directamente en el repositorio de Git.

### Modelos recomendados:
1. **Qwen 2.5 Coder 1.5B Instruct (Q4_K_M)** (~1.04 GB):
   - Archivo: `qwen2.5-coder-1.5b-instruct-q4_k_m.gguf`
   - Descarga desde Hugging Face: [Qwen2.5-Coder-1.5B-Instruct-GGUF](https://huggingface.co/Qwen/Qwen2.5-Coder-1.5B-Instruct-GGUF)

2. **Meta Llama 3.1 8B Instruct (Q4_K_M)** (~4.92 GB):
   - Archivo: `Meta-Llama-3.1-8B-Instruct-Q4_K_M.gguf`
   - Puedes descargarlo automáticamente ejecutando:
     ```bash
     python download_8b.py
     ```
