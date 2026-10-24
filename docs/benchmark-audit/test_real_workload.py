"""
Script de Evaluación con Cargas de Trabajo Reales para Qwen 2.5 Coder 3B (Ryzen 5 2400G)
Mide:
1. Conversacion corta (saludo / explicacion breve)
2. Tarea de programacion (generacion de codigo puro)
3. Inspeccion de archivo largo (ingesta de codigo real del repo)
4. Conversacion acumulada multi-turn (contexto largo acumulado)

Captura: TTFT (Time to First Token / Prompt Eval Time), Prompt t/s, Gen t/s, y tiempo total.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.error

API_BASE = "http://127.0.0.1:8089"

def send_chat(messages, max_tokens=300):
    payload = {
        "model": "qwen3b",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})
    
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=120) as resp:
        res = json.loads(resp.read().decode())
    total_elapsed = time.time() - t0
    
    timings = res.get("timings", {})
    prompt_n = timings.get("prompt_n", 0)
    prompt_ms = timings.get("prompt_ms", 0.0)
    prompt_per_second = timings.get("prompt_per_second", 0.0)
    
    predicted_n = timings.get("predicted_n", 0)
    predicted_ms = timings.get("predicted_ms", 0.0)
    predicted_per_second = timings.get("predicted_per_second", 0.0)
    
    content = res["choices"][0]["message"]["content"]
    
    # TTFT aproximado = tiempo de prefill del prompt en segundos
    ttft_s = prompt_ms / 1000.0 if prompt_ms > 0 else 0.0
    
    return {
        "content": content,
        "prompt_n": prompt_n,
        "predicted_n": predicted_n,
        "ttft_s": ttft_s,
        "prompt_tps": prompt_per_second,
        "gen_tps": predicted_per_second,
        "total_elapsed": total_elapsed
    }

def main():
    print("=================================================================")
    print("      EVALUACION DE CARGAS DE TRABAJO REALES (QWEN 3B)")
    print("=================================================================")
    
    # 1. Conversacion corta
    print("\n[Caso 1] Conversacion corta (latencia y respuesta rapida)...")
    c1 = send_chat([
        {"role": "system", "content": "Sos un asistente de programacion conciso y directo."},
        {"role": "user", "content": "Hola, decime en dos oraciones que es un stop loss y por que es critico en trading."}
    ], max_tokens=100)
    print(f" -> Prompt: {c1['prompt_n']} tokens | Gen: {c1['predicted_n']} tokens")
    print(f" -> TTFT (prefill): {c1['ttft_s']:.2f}s | Prompt tps: {c1['prompt_tps']:.1f} t/s | Gen tps: {c1['gen_tps']:.2f} t/s | Total: {c1['total_elapsed']:.2f}s")
    
    # 2. Tarea de programacion (generacion de codigo puro)
    print("\n[Caso 2] Tarea de programacion (generacion de codigo)...")
    c2 = send_chat([
        {"role": "system", "content": "Sos un ingeniero Python senior. Escribe solo codigo limpio y conciso."},
        {"role": "user", "content": "Escribe una funcion en Python para calcular el ratio de Sharpe anualizado dado un array de retornos diarios y una tasa libre de riesgo. Incluye validaciones."}
    ], max_tokens=250)
    print(f" -> Prompt: {c2['prompt_n']} tokens | Gen: {c2['predicted_n']} tokens")
    print(f" -> TTFT (prefill): {c2['ttft_s']:.2f}s | Prompt tps: {c2['prompt_tps']:.1f} t/s | Gen tps: {c2['gen_tps']:.2f} t/s | Total: {c2['total_elapsed']:.2f}s")
    
    # 3. Lectura de archivo largo (ingesta de codigo real del repo)
    print("\n[Caso 3] Lectura de archivo de codigo (analisis de archivo real, watchdog.py)...")
    tools_file = os.path.join(r"C:\Users\Guille\Downloads\IA", "agent", "watchdog.py")
    with open(tools_file, "r", encoding="utf-8") as f:
        code_content = f.read()
    
    prompt_largo = f"Lee el siguiente codigo fuente del archivo watchdog.py y enumera las clases/funciones implementadas y posibles mejoras:\n\n```python\n{code_content}\n```"
    c3 = send_chat([
        {"role": "system", "content": "Sos un revisor de codigo de alta eficiencia. Se directo."},
        {"role": "user", "content": prompt_largo}
    ], max_tokens=200)
    print(f" -> Prompt: {c3['prompt_n']} tokens | Gen: {c3['predicted_n']} tokens")
    print(f" -> TTFT (prefill): {c3['ttft_s']:.2f}s | Prompt tps: {c3['prompt_tps']:.1f} t/s | Gen tps: {c3['gen_tps']:.2f} t/s | Total: {c3['total_elapsed']:.2f}s")
    
    # 4. Conversacion acumulada multi-turn (contexto largo acumulado)
    print("\n[Caso 4] Conversacion acumulada multi-turn (4 turnos)...")
    history = [
        {"role": "system", "content": "Sos un asistente de programacion Python."},
        {"role": "user", "content": "Crea una clase simple de Trade con symbol, entry_price, size y timestamp."},
        {"role": "assistant", "content": "class Trade:\n    def __init__(self, symbol: str, entry_price: float, size: float, timestamp: float):\n        self.symbol = symbol\n        self.entry_price = entry_price\n        self.size = size\n        self.timestamp = timestamp"},
        {"role": "user", "content": "Ahora agrega un metodo para calcular el PnL no realizado dado un current_price."},
        {"role": "assistant", "content": "    def unrealized_pnl(self, current_price: float) -> float:\n        return (current_price - self.entry_price) * self.size"},
        {"role": "user", "content": "Perfecto, ahora agrega soporte para operaciones Short (donde ganar si el precio baja)."}
    ]
    c4 = send_chat(history, max_tokens=200)
    print(f" -> Prompt: {c4['prompt_n']} tokens | Gen: {c4['predicted_n']} tokens")
    print(f" -> TTFT (prefill): {c4['ttft_s']:.2f}s | Prompt tps: {c4['prompt_tps']:.1f} t/s | Gen tps: {c4['gen_tps']:.2f} t/s | Total: {c4['total_elapsed']:.2f}s")
    
    print("\n" + "="*85)
    print("                    RESUMEN DE PRUEBAS EN CARGAS REALES")
    print("="*85)
    print(f"{'Caso de Uso':<32} | {'Tokens In/Out':<16} | {'TTFT (Prefill)':<15} | {'Ingesta':<12} | {'Generacion':<12}")
    print("-" * 95)
    print(f"{'1. Conversacion Corta':<32} | {c1['prompt_n']} / {c1['predicted_n']:<10} | {c1['ttft_s']:>5.2f} seg       | {c1['prompt_tps']:>5.1f} t/s  | {c1['gen_tps']:>5.2f} t/s")
    print(f"{'2. Generacion de Codigo':<32} | {c2['prompt_n']} / {c2['predicted_n']:<10} | {c2['ttft_s']:>5.2f} seg       | {c2['prompt_tps']:>5.1f} t/s  | {c2['gen_tps']:>5.2f} t/s")
    print(f"{'3. Archivo Largo (tools.py)':<32} | {c3['prompt_n']} / {c3['predicted_n']:<10} | {c3['ttft_s']:>5.2f} seg       | {c3['prompt_tps']:>5.1f} t/s  | {c3['gen_tps']:>5.2f} t/s")
    print(f"{'4. Contexto Acumulado (4 turnos)':<32} | {c4['prompt_n']} / {c4['predicted_n']:<10} | {c4['ttft_s']:>5.2f} seg       | {c4['prompt_tps']:>5.1f} t/s  | {c4['gen_tps']:>5.2f} t/s")
    print("="*85)

if __name__ == "__main__":
    main()
