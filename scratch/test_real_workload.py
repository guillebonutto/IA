"""
Script de Evaluación con Cargas de Trabajo Reales para Qwen 2.5 Coder 3B (Ryzen 5 2400G)
Mide:
1. Conversación corta (saludo / explicación breve)
2. Tarea de programación (generación de código puro)
3. Inspección de archivo de código (análisis de archivo real: watchdog.py)
4. Conversación acumulada multi-turn (contexto acumulado de 4 turnos)

Métricas Separadas y Rigurosas:
- Tiempo interno de prefill (prompt_ms): cálculo puro de GGML decode en CPU reportado por el servidor.
- TTFT real de cliente (streaming SSE): latencia desde el envío del request hasta la recepción del primer token.
  Si no se detecta contenido en el stream SSE, client_ttft_sse_s se registra como None (null) con estado de error,
  sin sustituir jamás el TTFT por el tiempo total de la conexión (total_elapsed).
- Velocidad de generación (gen_tps): tokens generados por segundo calculados sobre el tiempo de decodificación.
- Tiempo total HTTP: duración completa de la conexión de red (wall-clock time).
- Tokens en caché (cache_n) vs nuevos tokens evaluados (prompt_n) para detectar reuso de slot.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error

def find_workspace_root() -> str:
    """Localiza de forma robusta la raíz del repositorio ascendiendo hasta encontrar .git o bin/llama-server.exe."""
    curr = os.path.dirname(os.path.abspath(__file__))
    while curr and os.path.dirname(curr) != curr:
        if os.path.exists(os.path.join(curr, ".git")) or os.path.exists(os.path.join(curr, "bin", "llama-server.exe")):
            return curr
        curr = os.path.dirname(curr)
    return os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = find_workspace_root()

PORT = 8089
API_BASE = f"http://127.0.0.1:{PORT}"

def send_chat_stream(messages, max_tokens=300):
    payload = {
        "model": "qwen3b",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": True,
        "stream_options": {"include_usage": True}
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})

    t0 = time.time()
    first_token_time = None
    timings = {}
    content_chunks = []

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line or not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue

                if "timings" in chunk and chunk["timings"]:
                    timings = chunk["timings"]

                choices = chunk.get("choices", [])
                if choices and "delta" in choices[0]:
                    delta = choices[0]["delta"]
                    text = delta.get("content")
                    if text:
                        if first_token_time is None:
                            first_token_time = time.time() - t0
                        content_chunks.append(text)
    except urllib.error.URLError as e:
        raise RuntimeError(f"Error al conectar con llama-server en {API_BASE}: {e}")

    total_elapsed = time.time() - t0

    prompt_n = timings.get("prompt_n", 0)
    cache_n = timings.get("cache_n", 0)
    prompt_ms = timings.get("prompt_ms", 0.0)
    prompt_tps = timings.get("prompt_per_second", 0.0)

    predicted_n = timings.get("predicted_n", 0)
    predicted_ms = timings.get("predicted_ms", 0.0)
    predicted_tps = timings.get("predicted_per_second", 0.0)

    prefill_compute_s = prompt_ms / 1000.0 if prompt_ms > 0 else 0.0

    # Si no se detectó el primer evento SSE con contenido, registrar como None con condición explícita de error.
    # NUNCA sustituir TTFT por total_elapsed.
    if first_token_time is not None:
        client_ttft_s = first_token_time
        ttft_status = "ok"
    else:
        client_ttft_s = None
        ttft_status = "error_no_content_received"

    if predicted_tps == 0.0 and predicted_ms > 0:
        predicted_tps = predicted_n / (predicted_ms / 1000.0)

    return {
        "content": "".join(content_chunks),
        "prompt_n": prompt_n,
        "cache_n": cache_n,
        "predicted_n": predicted_n,
        "prefill_compute_s": prefill_compute_s,
        "client_ttft_s": client_ttft_s,
        "ttft_status": ttft_status,
        "prompt_tps": prompt_tps,
        "gen_tps": predicted_tps,
        "total_elapsed": total_elapsed
    }

def format_ttft(val, status):
    if val is not None:
        return f"{val:>6.3f} seg"
    return f"N/A ({status})"

def main():
    print("=========================================================================================")
    print("        EVALUACION DE CARGAS DE TRABAJO REALES CON METRICAS SEPARADAS (QWEN 3B)")
    print("=========================================================================================")
    print(f"Servidor destino: {API_BASE}")
    print(f"Directorio raíz de trabajo: {WORKSPACE}\n")

    # 1. Conversacion corta
    print("[Caso 1] Conversacion corta (latencia y respuesta rapida)...")
    c1 = send_chat_stream([
        {"role": "system", "content": "Sos un asistente de programacion conciso y directo."},
        {"role": "user", "content": "Hola, decime en dos oraciones que es un stop loss y por que es critico en trading."}
    ], max_tokens=100)
    ttft_str1 = f"{c1['client_ttft_s']:.3f}s" if c1['client_ttft_s'] is not None else f"N/A ({c1['ttft_status']})"
    print(f" -> Tokens: Evaluados={c1['prompt_n']} | En Cache={c1['cache_n']} | Generados={c1['predicted_n']}")
    print(f" -> Prefill Interno: {c1['prefill_compute_s']:.3f}s | TTFT Real SSE: {ttft_str1} | Gen: {c1['gen_tps']:.2f} t/s | Total HTTP: {c1['total_elapsed']:.3f}s\n")

    # 2. Tarea de programacion (generacion de codigo puro)
    print("[Caso 2] Tarea de programacion (generacion de codigo)...")
    c2 = send_chat_stream([
        {"role": "system", "content": "Sos un ingeniero Python senior. Escribe solo codigo limpio y conciso."},
        {"role": "user", "content": "Escribe una funcion en Python para calcular el ratio de Sharpe anualizado dado un array de retornos diarios y una tasa libre de riesgo. Incluye validaciones."}
    ], max_tokens=250)
    ttft_str2 = f"{c2['client_ttft_s']:.3f}s" if c2['client_ttft_s'] is not None else f"N/A ({c2['ttft_status']})"
    print(f" -> Tokens: Evaluados={c2['prompt_n']} | En Cache={c2['cache_n']} | Generados={c2['predicted_n']}")
    print(f" -> Prefill Interno: {c2['prefill_compute_s']:.3f}s | TTFT Real SSE: {ttft_str2} | Gen: {c2['gen_tps']:.2f} t/s | Total HTTP: {c2['total_elapsed']:.3f}s\n")

    # 3. Lectura de archivo de codigo (analisis de archivo real: watchdog.py)
    print("[Caso 3] Lectura de archivo de codigo real (agent/watchdog.py)...")
    watchdog_file = os.path.join(WORKSPACE, "agent", "watchdog.py")
    if not os.path.exists(watchdog_file):
        print(f"  [ERROR] No se encontró el archivo: {watchdog_file}")
        sys.exit(1)

    with open(watchdog_file, "r", encoding="utf-8") as f:
        code_content = f.read()

    prompt_largo = f"Lee el siguiente codigo fuente del archivo watchdog.py y enumera las clases/funciones implementadas y posibles mejoras:\n\n```python\n{code_content}\n```"
    c3 = send_chat_stream([
        {"role": "system", "content": "Sos un revisor de codigo de alta eficiencia. Se directo."},
        {"role": "user", "content": prompt_largo}
    ], max_tokens=200)
    ttft_str3 = f"{c3['client_ttft_s']:.3f}s" if c3['client_ttft_s'] is not None else f"N/A ({c3['ttft_status']})"
    print(f" -> Tokens: Evaluados={c3['prompt_n']} | En Cache={c3['cache_n']} | Generados={c3['predicted_n']}")
    print(f" -> Prefill Interno: {c3['prefill_compute_s']:.3f}s | TTFT Real SSE: {ttft_str3} | Gen: {c3['gen_tps']:.2f} t/s | Total HTTP: {c3['total_elapsed']:.3f}s\n")

    # 4. Conversacion acumulada multi-turn (contexto largo acumulado)
    print("[Caso 4] Conversacion acumulada multi-turn (4 turnos)...")
    history = [
        {"role": "system", "content": "Sos un asistente de programacion Python."},
        {"role": "user", "content": "Crea una clase simple de Trade con symbol, entry_price, size y timestamp."},
        {"role": "assistant", "content": "class Trade:\n    def __init__(self, symbol: str, entry_price: float, size: float, timestamp: float):\n        self.symbol = symbol\n        self.entry_price = entry_price\n        self.size = size\n        self.timestamp = timestamp"},
        {"role": "user", "content": "Ahora agrega un metodo para calcular el PnL no realizado dado un current_price."},
        {"role": "assistant", "content": "    def unrealized_pnl(self, current_price: float) -> float:\n        return (current_price - self.entry_price) * self.size"},
        {"role": "user", "content": "Perfecto, ahora agrega soporte para operaciones Short (donde ganar si el precio baja)."}
    ]
    c4 = send_chat_stream(history, max_tokens=200)
    ttft_str4 = f"{c4['client_ttft_s']:.3f}s" if c4['client_ttft_s'] is not None else f"N/A ({c4['ttft_status']})"
    print(f" -> Tokens: Evaluados={c4['prompt_n']} | En Cache={c4['cache_n']} | Generados={c4['predicted_n']}")
    print(f" -> Prefill Interno: {c4['prefill_compute_s']:.3f}s | TTFT Real SSE: {ttft_str4} | Gen: {c4['gen_tps']:.2f} t/s | Total HTTP: {c4['total_elapsed']:.3f}s\n")

    print("\n" + "=" * 110)
    print("                    RESUMEN DE PRUEBAS EN CARGAS REALES (MÉTRICAS SEPARADAS)")
    print("=" * 110)
    print(f"{'Caso de Uso':<32} | {'Tokens Eval/Gen':<16} | {'Prefill C++':<12} | {'TTFT Real SSE':<16} | {'Gen t/s':<10} | {'Total HTTP':<10}")
    print("-" * 110)
    print(f"{'1. Conversacion Corta':<32} | {c1['prompt_n']:>5} / {c1['predicted_n']:<8} | {c1['prefill_compute_s']:>6.3f} seg   | {format_ttft(c1['client_ttft_s'], c1['ttft_status']):<16} | {c1['gen_tps']:>6.2f} t/s | {c1['total_elapsed']:>6.3f} seg")
    print(f"{'2. Generacion de Codigo':<32} | {c2['prompt_n']:>5} / {c2['predicted_n']:<8} | {c2['prefill_compute_s']:>6.3f} seg   | {format_ttft(c2['client_ttft_s'], c2['ttft_status']):<16} | {c2['gen_tps']:>6.2f} t/s | {c2['total_elapsed']:>6.3f} seg")
    print(f"{'3. Archivo de Codigo (watchdog.py)':<32} | {c3['prompt_n']:>5} / {c3['predicted_n']:<8} | {c3['prefill_compute_s']:>6.3f} seg   | {format_ttft(c3['client_ttft_s'], c3['ttft_status']):<16} | {c3['gen_tps']:>6.2f} t/s | {c3['total_elapsed']:>6.3f} seg")
    print(f"{'4. Contexto Acumulado (4 turnos)':<32} | {c4['prompt_n']:>5} / {c4['predicted_n']:<8} | {c4['prefill_compute_s']:>6.3f} seg   | {format_ttft(c4['client_ttft_s'], c4['ttft_status']):<16} | {c4['gen_tps']:>6.2f} t/s | {c4['total_elapsed']:>6.3f} seg")
    print("=" * 110)
    print("Nota Metodológica:")
    print("  - 'Prefill C++': tiempo de cálculo interno devuelto por llama.cpp en prompt_ms.")
    print("  - 'TTFT Real SSE': tiempo medido por el cliente desde el envío HTTP hasta el primer evento SSE con contenido.")
    print("    Si no se recibe contenido en el stream, se registra como None (null) con error explícito sin sustituirlo por el tiempo total.")
    print("  - 'Total HTTP': duración completa de la petición HTTP (no utilizar como divisor para velocidad de generación).")
    print("  - 'Gen t/s': calculado estrictamente sobre el tiempo de decodificación autoregresiva.")

if __name__ == "__main__":
    main()
