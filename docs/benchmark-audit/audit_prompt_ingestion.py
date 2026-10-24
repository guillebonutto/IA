"""
Auditoría Controlada de Ingesta de Prompts en Ryzen 5 2400G
Evalúa longitudes: 256, 512, 1024, 2048, 4096 tokens
Constantes: Qwen 3B Q4_K_M, 8 hilos, FP16 KV-Cache, -fa 0, -b 512, -ub 128
3 repeticiones por longitud, separando procesamiento de prompt y generación.

Almacenamiento de Datos:
- Conserva muestras crudas íntegras (samples_ns, samples_ts) directamente de llama-bench.
- Separa claramente 'raw_samples' de 'summary_statistics'.
"""

import os
import sys
import json
import subprocess
import statistics

def find_workspace_root(start_path: str = None) -> str:
    """
    Localiza la raíz del repositorio ascendiendo hasta encontrar marcadores conocidos
    (.git, start_ai.bat, bin/llama-server.exe, agent/watchdog.py).
    Si los marcadores no están presentes (ej. exportación limpia sin binarios ni .git),
    aplica un fallback estructural determinista según la ruta relativa conocida.
    """
    if start_path is None:
        start_path = os.path.dirname(os.path.abspath(__file__))
    else:
        start_path = os.path.abspath(start_path)

    curr = start_path
    while curr and os.path.dirname(curr) != curr:
        if (os.path.exists(os.path.join(curr, ".git")) or
            os.path.exists(os.path.join(curr, "start_ai.bat")) or
            os.path.exists(os.path.join(curr, "bin", "llama-server.exe")) or
            os.path.exists(os.path.join(curr, "agent", "watchdog.py"))):
            return curr
        curr = os.path.dirname(curr)

    parts = os.path.normpath(start_path).split(os.sep)
    if len(parts) >= 2 and parts[-2:] == ["docs", "benchmark-audit"]:
        return os.path.abspath(os.path.join(start_path, "..", ".."))
    elif len(parts) >= 1 and parts[-1] in ("scratch", "docs"):
        return os.path.abspath(os.path.join(start_path, ".."))
    return os.path.abspath(os.path.join(start_path, ".."))

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
WORKSPACE = find_workspace_root()

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
    if not os.path.exists(BIN_PATH) or not os.path.exists(MODEL_PATH):
        print(f"[ERROR] Binario o modelo no encontrado en las rutas esperadas.")
        print(f"  Binario buscado: {BIN_PATH}")
        print(f"  Modelo buscado: {MODEL_PATH}")
        sys.exit(1)

    print("=" * 80)
    print("       AUDITORÍA RIGUROSA DE INGESTA DE PROMPTS (LLAMA-BENCH JSON)")
    print("=" * 80)

    audit_data = []

    for length in PROMPT_LENGTHS:
        p_rec, g_rec = run_bench_for_length(length)
        if not p_rec:
            print(f"[ERROR] No se pudo obtener registro para {length}")
            continue

        p_runs_tps = p_rec["samples_ts"]
        p_runs_ns = p_rec["samples_ns"]
        p_runs_ms = [ns / 1e6 for ns in p_runs_ns]
        p_med_tps = statistics.median(p_runs_tps)
        p_std_tps = p_rec["stddev_ts"]
        p_med_time_s = statistics.median(p_runs_ms) / 1000.0

        g_runs_tps = g_rec["samples_ts"] if g_rec else []
        g_runs_ns = g_rec["samples_ns"] if g_rec else []
        g_med_tps = statistics.median(g_runs_tps) if g_runs_tps else 0.0
        g_std_tps = g_rec["stddev_ts"] if g_rec else 0.0

        print(f"  > Prompt ({length} tok):")
        print(f"    - Corridas (t/s): {[round(x, 2) for x in p_runs_tps]}")
        print(f"    - Mediana: {p_med_tps:.2f} t/s | Desv Std: ±{p_std_tps:.2f} t/s")
        print(f"    - Tiempo Mediano de Ingesta: {p_med_time_s:.2f} seg")
        if g_runs_tps:
            print(f"  > Generacion de referencia (n_prompt=0, n_gen=16):")
            print(f"    - Corridas (t/s): {[round(x, 2) for x in g_runs_tps]}")
            print(f"    - Mediana: {g_med_tps:.2f} t/s | Desv Std: ±{g_std_tps:.2f} t/s")

        entry = {
            "target_prompt_tokens": length,
            "raw_samples": {
                "prompt_samples_ns": p_runs_ns,
                "prompt_samples_ts": p_runs_tps,
                "gen_samples_ns": g_runs_ns,
                "gen_samples_ts": g_runs_tps
            },
            "summary_statistics": {
                "prompt_median_tps": p_med_tps,
                "prompt_avg_tps": p_rec.get("avg_ts", p_med_tps),
                "prompt_stddev_tps": p_std_tps,
                "prompt_median_duration_s": p_med_time_s,
                "gen_reference_median_tps": g_med_tps,
                "gen_reference_stddev_tps": g_std_tps
            },
            "metadata": {
                "note_on_generation": "La prueba de generacion de llama-bench se ejecuta con n_prompt=0 y no mide degradacion tras evaluar el prompt."
            }
        }
        audit_data.append(entry)

    print("\n\n" + "=" * 90)
    print("                    TABLA CONSOLIDADA DE LA AUDITORÍA DE INGESTA")
    print("=" * 90)
    print(f"{'Longitud':<10} | {'Ingesta Mediana':<18} | {'Corridas [1, 2, 3] (t/s)':<25} | {'Tiempo Ingesta':<16} | {'Gen (n_prompt=0)':<16}")
    print("-" * 90)
    for s in audit_data:
        stats = s["summary_statistics"]
        raw = s["raw_samples"]
        runs_str = f"[{raw['prompt_samples_ts'][0]:.1f}, {raw['prompt_samples_ts'][1]:.1f}, {raw['prompt_samples_ts'][2]:.1f}]"
        print(f"{s['target_prompt_tokens']:<10} | {stats['prompt_median_tps']:>6.2f} ± {stats['prompt_stddev_tps']:<5.2f} t/s | {runs_str:<25} | {stats['prompt_median_duration_s']:>6.2f} seg        | {stats['gen_reference_median_tps']:>5.2f} t/s")
    print("=" * 90)

    res_path = os.path.join(SCRIPT_DIR, "audit_ingestion_results.json")
    with open(res_path, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)
    print(f"\nResultados y muestras crudas guardados en: {res_path}")

if __name__ == "__main__":
    main()
