"""
Script de Automatización del Protocolo Científico de Benchmarks para Ryzen 5 2400G
Evalúa:
1. Flash Attention (ON vs OFF)
2. KV Cache a 8 hilos constantes (FP16 vs Q8_0 vs Q4_0)
3. Ventana de Contexto (4096 vs 8192)

Seguridad de Procesos:
- No mata procesos ajenos ni globales por nombre de imagen.
- Verifica disponibilidad del puerto antes de iniciar.
- Administra exclusivamente el subproceso creado (PID propio).
- Redirige y conserva los logs del servidor en un archivo de registro para inspección.
"""

import os
import sys
import time
import json
import socket
import statistics
import subprocess
import urllib.request
import urllib.error

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

BIN_PATH = os.path.join(WORKSPACE, "bin", "llama-server.exe")
MODEL_PATH = os.path.join(WORKSPACE, "models", "qwen2.5-coder-3b-instruct-q4_k_m.gguf")
LOG_PATH = os.path.join(SCRIPT_DIR, "benchmark_server.log")

PORT = 8082
API_BASE = f"http://127.0.0.1:{PORT}"

PROMPT_TEXT = (
    "Escribe una clase en Python para gestionar una cartera de trading con control de riesgo, "
    "incluyendo calculo de position sizing con regla del 2%, stop loss y take profit. "
    "Incluye comentarios explicativos en cada metodo."
)

def is_port_in_use(port: int) -> bool:
    """Comprueba si un puerto TCP local está ocupado sin alterar ningún proceso."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def get_ram_usage(pid: int):
    """Obtiene WorkingSet (RAM residente) y PrivateBytes (Memoria privada) en MB usando PowerShell."""
    try:
        out = subprocess.check_output(["powershell", "-NoProfile", "-Command",
            f"$p = Get-Process -Id {pid} -ErrorAction Stop; Write-Output ('{0};{1}' -f [math]::Round($p.WorkingSet64/1MB,1), [math]::Round($p.PrivateMemorySize64/1MB,1))"
        ], text=True).strip()
        ws_str, pm_str = out.split(";")
        ws = float(ws_str.replace(",", "."))
        pm = float(pm_str.replace(",", "."))
        return ws, pm
    except Exception:
        return 0.0, 0.0

def wait_for_server(timeout=30):
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(f"{API_BASE}/health")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    data = json.loads(resp.read().decode())
                    if data.get("status") == "ok":
                        return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def run_single_inference(prompt: str, max_tokens: int = 200):
    """Envía un prompt a llama-server y extrae las métricas exactas de timings."""
    payload = {
        "model": "qwen3b",
        "messages": [
            {"role": "system", "content": "You are a professional Python engineer. Answer in clean Python code."},
            {"role": "user", "content": prompt}
        ],
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})

    t0 = time.time()
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode())
    elapsed = time.time() - t0

    timings = result.get("timings", {})
    pp_speed = timings.get("prompt_per_second", 0.0)
    tg_speed = timings.get("predicted_per_second", 0.0)
    tokens_gen = timings.get("predicted_n", 0)

    if tg_speed == 0.0 and tokens_gen > 0 and elapsed > 0:
        tg_speed = tokens_gen / elapsed

    return pp_speed, tg_speed, tokens_gen

def test_configuration(name: str, args: list):
    print(f"\n========================================================")
    print(f"  Iniciando: {name}")
    print(f"  Comando: llama-server {' '.join(args)}")
    print(f"========================================================")

    # Comprobar que el puerto esté libre antes de arrancar, sin matar procesos ajenos
    if is_port_in_use(PORT):
        raise RuntimeError(
            f"El puerto {PORT} está ocupado por otro proceso. "
            "No se cerrará ningún proceso externo automáticamente. "
            "Libera el puerto o cambia la variable PORT para continuar de forma segura."
        )

    full_cmd = [BIN_PATH, "-m", MODEL_PATH, "--port", str(PORT), "--host", "127.0.0.1"] + args

    with open(LOG_PATH, "a", encoding="utf-8") as log_file:
        log_file.write(f"\n\n--- INICIO CONFIGURACIÓN: {name} ---\nComando: {' '.join(full_cmd)}\n")
        log_file.flush()
        proc = subprocess.Popen(full_cmd, stdout=log_file, stderr=subprocess.STDOUT)

    try:
        if not wait_for_server(timeout=25):
            print(f"  [ERROR] El servidor no respondió en el tiempo límite. Revisa {LOG_PATH}")
            return None

        idle_ws, idle_pm = get_ram_usage(proc.pid)
        print(f"  [RAM Reposo] Residente: {idle_ws:.1f} MB | Privada: {idle_pm:.1f} MB")

        pp_speeds = []
        tg_speeds = []
        peak_ws_list = []
        peak_pm_list = []

        for i in range(3):
            print(f"  -> Corrida {i+1}/3 ...", end="", flush=True)
            pp_s, tg_s, n_tokens = run_single_inference(PROMPT_TEXT, max_tokens=200)
            ws, pm = get_ram_usage(proc.pid)
            pp_speeds.append(pp_s)
            tg_speeds.append(tg_s)
            peak_ws_list.append(ws)
            peak_pm_list.append(pm)
            print(f" Gen: {tg_s:.2f} t/s | Prompt: {pp_s:.2f} t/s | RAM: {ws:.1f} MB")
            time.sleep(1)

        med_pp = statistics.median(pp_speeds)
        med_tg = statistics.median(tg_speeds)
        med_ws = statistics.median(peak_ws_list)
        med_pm = statistics.median(peak_pm_list)

        print(f"  [MEDIANA] Gen: {med_tg:.2f} t/s (Corridas: {[round(x,2) for x in tg_speeds]})")
        print(f"            Prompt: {med_pp:.2f} t/s | RAM Residente: {med_ws:.1f} MB | Privada: {med_pm:.1f} MB")

        return {
            "name": name,
            "runs_tg": tg_speeds,
            "med_tg": med_tg,
            "med_pp": med_pp,
            "idle_ws": idle_ws,
            "peak_ws": med_ws,
            "idle_pm": idle_pm,
            "peak_pm": med_pm
        }
    finally:
        # Administrar exclusivamente el subproceso generado por este script
        if proc and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception as e_term:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception as e_kill:
                    pass

            if proc.poll() is None:
                print(
                    f"ALERTA DE SEGURIDAD: El subproceso PID {proc.pid} no pudo ser finalizado. "
                    "No se intentara cerrar procesos ajenos. Verifique manualmente.",
                    flush=True
                )
        time.sleep(1)

def main():
    if not os.path.exists(BIN_PATH) or not os.path.exists(MODEL_PATH):
        print(f"[ERROR] Binario o modelo no encontrado en las rutas esperadas.")
        print(f"  Binario buscado: {BIN_PATH}")
        print(f"  Modelo buscado: {MODEL_PATH}")
        sys.exit(1)

    print("Iniciando Protocolo Científico (8 Hilos Constantes) en Ryzen 5 2400G...")
    print(f"Logs del servidor se guardan en: {LOG_PATH}")

    common_8t = ["-t", "8", "-tb", "8", "-b", "512", "-ub", "128", "--prio", "0", "-lm", "mmap"]

    tests = [
        ("Exp 1.1: Flash Attention ON  (-fa on)", common_8t + ["-c", "4096", "--cache-type-k", "f16", "--cache-type-v", "f16", "-fa", "on"]),
        ("Exp 1.2: Flash Attention OFF (-fa off)", common_8t + ["-c", "4096", "--cache-type-k", "f16", "--cache-type-v", "f16", "-fa", "off"]),
        ("Exp 2.1: KV Cache FP16 (Nativo, 8 hilos)", common_8t + ["-c", "4096", "--cache-type-k", "f16", "--cache-type-v", "f16", "-fa", "on"]),
        ("Exp 2.2: KV Cache Q8_0 (8 hilos)", common_8t + ["-c", "4096", "--cache-type-k", "q8_0", "--cache-type-v", "q8_0", "-fa", "on"]),
        ("Exp 2.3: KV Cache Q4_0 (8 hilos)", common_8t + ["-c", "4096", "--cache-type-k", "q4_0", "--cache-type-v", "q4_0", "-fa", "on"]),
        ("Exp 3.1: Contexto 4096 tokens", common_8t + ["-c", "4096", "--cache-type-k", "f16", "--cache-type-v", "f16", "-fa", "on"]),
        ("Exp 3.2: Contexto 8192 tokens", common_8t + ["-c", "8192", "--cache-type-k", "f16", "--cache-type-v", "f16", "-fa", "on"])
    ]

    results = []
    for name, args in tests:
        res = test_configuration(name, args)
        if res:
            results.append(res)

    print("\n\n" + "="*95)
    print("                    TABLA FINAL: PROTOCOLO AISLADO (8 HILOS CONSTANTES)")
    print("="*95)
    print(f"{'Experimento':<38} | {'Gen Med (t/s)':<14} | {'Corridas [1, 2, 3]':<20} | {'RAM Residente':<14} | {'RAM Privada':<12}")
    print("-" * 105)

    for r in results:
        runs_str = f"[{r['runs_tg'][0]:.1f}, {r['runs_tg'][1]:.1f}, {r['runs_tg'][2]:.1f}]"
        print(f"{r['name']:<38} | {r['med_tg']:>5.2f} t/s      | {runs_str:<20} | {r['peak_ws']:>6.1f} MB      | {r['peak_pm']:>6.1f} MB")

    print("="*95)

if __name__ == "__main__":
    main()
