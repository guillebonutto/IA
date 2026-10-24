"""
Auditoría Controlada de Ingesta de Prompts en Ryzen 5 2400G
Evalúa longitudes: 256, 512, 1024, 2048, 4096 tokens
Constantes: Qwen 3B Q4_K_M, 8 hilos, FP16 KV-Cache, -fa 0, -b 512, -ub 128
3 repeticiones por longitud, separando procesamiento de prompt y generación.
"""

import os
import sys
import json
import subprocess
import statistics

WORKSPACE = r"C:\Users\Guille\Downloads\IA"
BIN_PATH = os.path.join(WORKSPACE, "bin", "llama-bench.exe")
MODEL_PATH = os.path.join(WORKSPACE, "models", "qwen2.5-coder-3b-instruct-q4_k_m.gguf")

PROMPT_LENGTHS = [256, 512, 1024, 2048, 4096]

def run_bench_for_length(n_prompt: int):
    print(f"\n--- Evaluando n_prompt = {n_prompt} tokens (3 repeticiones) ---", flush=True)
    cmd = [
        BIN_PATH,
        "-m", MODEL_PATH,
        "-p", str(n_prompt),
        "-n", "16",
        "-t", "8",
        "-b", "512",
        "-ub", "128",
        "-fa", "0",
        "-r", "3",
        "-o", "json"
    ]
    
    out = subprocess.check_output(cmd, text=True, cwd=WORKSPACE)
    
    # Extraer el bloque JSON de la salida
    json_start = out.find("[")
    if json_start == -1:
        raise RuntimeError(f"No se encontró salida JSON en: {out}")
    data = json.loads(out[json_start:])
    
    prompt_record = None
    gen_record = None
    
    for item in data:
        if item.get("n_prompt", 0) == n_prompt and item.get("n_gen", 0) == 0:
            prompt_record = item
        elif item.get("n_prompt", 0) == 0 and item.get("n_gen", 0) > 0:
            gen_record = item
            
    return prompt_record, gen_record

def main():
    print("=" * 80)
    print("       AUDITORÍA RIGUROSA DE INGESTA DE PROMPTS (LLAMA-BENCH JSON)")
    print("=" * 80)
    
    summary = []
    
    for length in PROMPT_LENGTHS:
        p_rec, g_rec = run_bench_for_length(length)
        if not p_rec:
            print(f"[ERROR] No se pudo obtener registro para {length}")
            continue
            
        p_runs_tps = p_rec["samples_ts"]
        p_runs_ms = [ns / 1e6 for ns in p_rec["samples_ns"]]
        p_med_tps = statistics.median(p_runs_tps)
        p_std_tps = p_rec["stddev_ts"]
        p_med_time_s = statistics.median(p_runs_ms) / 1000.0
        
        g_runs_tps = g_rec["samples_ts"] if g_rec else []
        g_med_tps = statistics.median(g_runs_tps) if g_runs_tps else 0.0
        g_std_tps = g_rec["stddev_ts"] if g_rec else 0.0
        
        print(f"  > Prompt ({length} tok):")
        print(f"    - Corridas (t/s): {[round(x, 2) for x in p_runs_tps]}")
        print(f"    - Mediana: {p_med_tps:.2f} t/s | Desv Std: ±{p_std_tps:.2f} t/s")
        print(f"    - Tiempo Mediano de Ingesta: {p_med_time_s:.2f} seg")
        if g_runs_tps:
            print(f"  > Generacion (16 tok):")
            print(f"    - Corridas (t/s): {[round(x, 2) for x in g_runs_tps]}")
            print(f"    - Mediana: {g_med_tps:.2f} t/s | Desv Std: ±{g_std_tps:.2f} t/s")
            
        summary.append({
            "tokens": length,
            "p_runs_tps": p_runs_tps,
            "p_med_tps": p_med_tps,
            "p_std_tps": p_std_tps,
            "p_med_time_s": p_med_time_s,
            "g_med_tps": g_med_tps,
            "g_std_tps": g_std_tps
        })
        
    print("\n\n" + "=" * 90)
    print("                    TABLA CONSOLIDADA DE LA AUDITORÍA DE INGESTA")
    print("=" * 90)
    print(f"{'Longitud':<10} | {'Ingesta Mediana':<18} | {'Corridas [1, 2, 3] (t/s)':<25} | {'Tiempo Ingesta':<16} | {'Gen Mediana':<12}")
    print("-" * 90)
    for s in summary:
        runs_str = f"[{s['p_runs_tps'][0]:.1f}, {s['p_runs_tps'][1]:.1f}, {s['p_runs_tps'][2]:.1f}]"
        print(f"{s['tokens']:<10} | {s['p_med_tps']:>6.2f} ± {s['p_std_tps']:<5.2f} t/s | {runs_str:<25} | {s['p_med_time_s']:>6.2f} seg        | {s['g_med_tps']:>5.2f} t/s")
    print("=" * 90)
    
    # Guardar resultados en JSON para persistencia
    res_path = os.path.join(WORKSPACE, "scratch", "audit_ingestion_results.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nResultados guardados en: {res_path}")

if __name__ == "__main__":
    main()
