# Guía de Entorno Python, Inferencia Local y Resolución de Problemas

Este documento detalla las directrices del entorno de ejecución de AURA y Bot-08-09 en Windows 10/11 con PowerShell.

---

## 1. Reglas de Inferencia Local y llama.cpp
- **Servidor de Inferencia:** `llama-server.exe` corriendo en `http://127.0.0.1:8089/v1`.
- **Preservación de Caché KV:**
  - En llamadas multi-paso (llamada a herramienta + síntesis final), el parámetro `tools` debe mantenerse en la solicitud enviando `tool_choice="none"`.
  - Quitar `tools` destruye la caché KV y obliga a recomputar ~1200 tokens en CPU en cada paso, provocando demoras excesivas.
- **Formateo de Salida en la Síntesis:**
  - Tras la ejecución de `list_directory`, `read_file` o `run_command`, la IA debe presentar directamente los datos y directorios al usuario, evitando meta-comentarios sobre JSON o estructuras internas.

---

## 2. Codificación y Manejo de Caracteres en Windows (CP1252 vs UTF-8)
- La consola estándar de PowerShell en Windows opera frecuentemente bajo la página de códigos `cp1252`.
- Para evitar excepciones `UnicodeEncodeError` en Python al imprimir caracteres especiales o emojis, las cadenas impresas en consola deben utilizar caracteres ASCII/Markdown compatibles o configurar `PYTHONIOENCODING=utf-8`.

---

## 3. Seguridad de Procesos en Segundo Plano
- **Procesos protegidos:**
  - `main.py` y `paper_bot.py` (Bots de trading activos).
  - `PiBot_Terminal.pyw` (Interfaz GUI / terminal de control).
  - `llama-server.exe` (Motor de inferencia local).
- **Prohibición de comandos destructivos:**
  - Bloqueados de raíz: `rmdir /s`, `format`, `del /s /q`, y scripts batch destructivos.
