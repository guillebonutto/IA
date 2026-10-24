"""
Benchmark de Contexto Real: Evaluación de Generación tras Ingesta de Contextos Variables
AURA CORE / llama.cpp - Ryzen 5 2400G (Windows 10)

Protocolo Científico:
1. Mantiene constantes:
   - Modelo: Qwen 2.5 Coder 3B Instruct Q4_K_M
   - Hilos: 8 hilos físicos/lógicos (-t 8 -tb 8)
   - Batch & UBatch: -b 512 -ub 128
   - Tipo de KV Cache: FP16 (-ctk f16 -ctv f16)
   - Flash Attention: OFF (-fa off)
   - Contexto CONFIGURADO: -c 8192 (reserva de memoria constante en todas las pruebas)
   - Tokens Objetivo a GENERAR: 64 tokens (temperatura 0.0)
2. Variable independiente:
   - Contexto REALMENTE PROCESADO: 256, 512, 1024, 2048, 4096 tokens de prompt
3. Protocolo de Calentamiento (Warmup):
   - Ejecuta 2 corridas no contabilizadas previas a las mediciones para cargar pesos en caché de SO y estabilizar OpenMP.
4. Repeticiones:
   - Al menos 5 repeticiones por longitud de contexto evaluada.
5. Verificación Estricta de Limpieza de Slots (/slots/0?action=erase):
   - Documentación técnica: en la versión llama.cpp (b11719), el handler 'server_task_result_slot_erase'
     invoca slot.reset() para liberar las celdas del KV cache del slot y restablecer los contadores a 0.
   - La presencia del argumento '--slot-save-path' es requerida para registrar el endpoint, pero no se asume
     como prueba suficiente de borrado. El script verifica la respuesta HTTP 200, inspecciona GET /slots
     y corrobora durante la inferencia que 'cache_n == 0'. Si se detecta 'cache_n > 0', la corrida se invalida.
6. Separación Estricta de Corridas Válidas y Exclusiones:
   - No se asume que temperature=0.0 genere siempre 64 tokens. Se inspecciona finish_reason ('length', 'stop').
   - Se separan las corridas válidas para comparar generación de aquellas que terminaron anticipadamente
     o sufrieron reutilización de caché.
   - Se conservan TODAS las muestras crudas, finish_reason original y la razón explícita de exclusión (sin descarte silencioso).
7. Métricas de Tiempo y TTFT (SSE):
   - Si no se detecta el primer evento SSE con contenido, client_ttft_sse_s se registra como None (null)
     con estado de error explícito, sin sustituir jamás TTFT por total_elapsed.
8. Seguridad de Procesos:
   - Comprueba disponibilidad del puerto antes de arrancar.
   - Administra exclusivamente el subproceso creado (PID propio).
   - Redirige logs del servidor a 'context_server.log'.

ESTADO: DISEÑADO - NO EJECUTAR HASTA REVISIÓN Y AUTORIZACIÓN EXPRESA.
"""

import os
import sys
import time
import json
import socket
import shutil
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
LOG_PATH = os.path.join(SCRIPT_DIR, "context_server.log")
RESULTS_PATH = os.path.join(SCRIPT_DIR, "context_generation_results.json")
SLOT_SAVE_PATH = os.path.join(SCRIPT_DIR, ".slot_cache_temp")

PORT = 8083  # Puerto aislado para benchmark de contexto
API_BASE = f"http://127.0.0.1:{PORT}"

CONFIGURED_CTX = 8192
EVALUATED_PROMPT_LENGTHS = [256, 512, 1024, 2048, 4096]
TARGET_GEN_TOKENS = 64
WARMUP_RUNS = 2
REPETITIONS = 5

def is_port_in_use(port: int) -> bool:
    """Verifica si el puerto local está en uso sin interferir con otros procesos."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0

def wait_for_server(timeout=35) -> bool:
    """Espera activamente a que el servidor responda con HTTP 200 en /health."""
    url = f"{API_BASE}/health"
    start = time.time()
    while time.time() - start < timeout:
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def count_tokens_online(text: str) -> int:
    """Obtiene la cantidad exacta de tokens usando el endpoint /tokenize del servidor."""
    url = f"{API_BASE}/tokenize"
    data = json.dumps({"content": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return len(res.get("tokens", []))

def get_slot_info(slot_id: int = 0) -> dict:
    """Consulta el estado y contadores de la ranura especificada a través de GET /slots."""
    url = f"{API_BASE}/slots"
    req = urllib.request.Request(url)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            slots = json.loads(resp.read().decode("utf-8"))
            for s in slots:
                if s.get("id") == slot_id:
                    return s
    except Exception:
        pass
    return {}

def verify_slot_erase_capability():
    """
    Comprueba si el servidor admite la limpieza explícita de ranura (/slots/0?action=erase).
    La versión de llama.cpp requiere haber iniciado con '--slot-save-path'.
    Verifica que la llamada devuelva HTTP 200 y que los contadores de slot queden reseteados.
    Si falla, lanza RuntimeError para evitar mediciones inválidas por reuso involuntario de caché.
    """
    url = f"{API_BASE}/slots/0?action=erase"
    req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Respuesta inesperada al verificar limpieza de slots: HTTP {resp.status}")
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8") if hasattr(e, "read") else str(e)
        raise RuntimeError(
            f"Fallo crítico: El endpoint '/slots/0?action=erase' no es admitido o devolvió error (HTTP {e.code}): {err_msg}. "
            "Para admitir borrado de slots, llama-server debe configurarse con '--slot-save-path'. "
            "El benchmark aborta de forma segura para no producir resultados inválidos con caché contaminado."
        )
    except Exception as e:
        raise RuntimeError(f"No se pudo verificar la limpieza de slots en el servidor: {e}")

    # Verificación secundaria: comprobar contadores de slot en GET /slots
    slot_info = get_slot_info(0)
    cached_tokens = slot_info.get("n_prompt_tokens_cache", 0)
    if cached_tokens > 0:
        raise RuntimeError(f"Fallo de limpieza: el slot reporta {cached_tokens} tokens residuales en caché tras el borrado.")
    return True

def clear_slot_cache():
    """
    Limpia el caché del slot 0, registra el resultado y comprueba contadores.
    Si la operación falla, lanza RuntimeError.
    """
    url = f"{API_BASE}/slots/0?action=erase"
    req = urllib.request.Request(url, data=b"{}", headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            if resp.status != 200:
                raise RuntimeError(f"Error al limpiar slot: HTTP {resp.status}")
    except Exception as e:
        raise RuntimeError(f"Fallo de limpieza de slot de contexto antes de la corrida: {e}")

    slot_info = get_slot_info(0)
    return {
        "erase_verified": True,
        "reported_cache_tokens_in_slot": slot_info.get("n_prompt_tokens_cache", 0),
        "slot_is_processing": slot_info.get("is_processing", False)
    }

def build_prompt_with_token_target(target_tokens: int) -> str:
    """Construye un prompt de código estructurado ajustado a la cantidad objetivo de tokens."""
    base_unit = (
        "def compute_trade_metrics_stage(step_index: int, alpha_val: float, beta_val: float) -> float:\n"
        "    # Realiza calculo ponderado de senal financiera y retorno acumulado\n"
        "    signal_accumulator = (alpha_val * 1.054) - (beta_val * 0.982)\n"
        "    normalized_variance = signal_accumulator / (abs(alpha_val) + 1e-6)\n"
        "    return round(normalized_variance, 6)\n\n"
    )

    current_text = base_unit
    current_tokens = count_tokens_online(current_text)

    multiplier = max(1, target_tokens // current_tokens)
    text = base_unit * multiplier
    tokens = count_tokens_online(text)

    while tokens < target_tokens:
        text += base_unit
        tokens = count_tokens_online(text)

    while tokens > target_tokens and len(text) > 10:
        text = text[:-10]
        tokens = count_tokens_online(text)

    while tokens < target_tokens:
        text += " #"
        tokens = count_tokens_online(text)

    return text

def send_chat_completion(prompt_text: str, target_gen: int = TARGET_GEN_TOKENS):
    """
    Envía solicitud de chat con streaming SSE y registra exhaustivamente la telemetría:
    - prompt_n: tokens de prompt realmente evaluados reportados por llama.cpp.
    - cache_n: tokens reutilizados del caché (debe ser 0 tras el borrado verificado).
    - predicted_n: tokens reales generados.
    - prompt_ms: tiempo interno de prefill.
    - predicted_ms: tiempo interno de decodificación.
    - client_ttft_s: TTFT medido por SSE; si no hay contenido o hubo error de transporte, se registra como None (null).
    - total_elapsed: tiempo total HTTP de la conexión.
    - finish_reason: motivo de culminación ('length', 'stop', etc.).
    - transport_error: detalle del error de transporte/red/timeout si ocurrió, de lo contrario None.
    """
    payload = {
        "model": "qwen3b",
        "messages": [
            {"role": "system", "content": "Sos un evaluador de codigo estricto y conciso."},
            {"role": "user", "content": f"Analiza brevemente la complejidad computacional del siguiente codigo:\n\n{prompt_text}"}
        ],
        "max_tokens": target_gen,
        "temperature": 0.0,
        "stream": True,
        "stream_options": {"include_usage": True}
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(f"{API_BASE}/v1/chat/completions", data=data, headers={"Content-Type": "application/json"})

    t0 = time.time()
    first_token_time = None
    timings = {}
    content_chunks = []
    finish_reason = None
    transport_error = None

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
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
                if choices:
                    c0 = choices[0]
                    if c0.get("finish_reason"):
                        finish_reason = c0["finish_reason"]
                    delta = c0.get("delta", {})
                    text = delta.get("content")
                    if text:
                        if first_token_time is None:
                            first_token_time = time.time() - t0
                        content_chunks.append(text)
    except Exception as e:
        transport_error = f"{type(e).__name__}: {str(e)}"

    total_elapsed = time.time() - t0

    prompt_n = timings.get("prompt_n", 0)
    if "cache_n" in timings and isinstance(timings["cache_n"], (int, float)):
        cache_n = int(timings["cache_n"])
    elif "n_prompt_tokens_cache" in timings and isinstance(timings["n_prompt_tokens_cache"], (int, float)):
        cache_n = int(timings["n_prompt_tokens_cache"])
    else:
        cache_n = None
    prompt_ms = timings.get("prompt_ms", 0.0)
    prompt_tps = timings.get("prompt_per_second", 0.0)

    predicted_n = timings.get("predicted_n", len(content_chunks))
    predicted_ms = timings.get("predicted_ms", 0.0)
    predicted_tps = timings.get("predicted_per_second", 0.0)

    if predicted_tps == 0.0 and predicted_ms > 0:
        predicted_tps = predicted_n / (predicted_ms / 1000.0)

    # Registro estricto de TTFT: None si hubo error de transporte o no hubo contenido; jamás sustituir por total_elapsed
    if transport_error:
        client_ttft_s = None
        ttft_status = f"transport_error ({transport_error})"
        if not finish_reason:
            finish_reason = "transport_error"
    elif first_token_time is not None:
        client_ttft_s = first_token_time
        ttft_status = "ok"
    else:
        client_ttft_s = None
        ttft_status = "error_no_content_received"

    return {
        "prompt_n": prompt_n,
        "cache_n": cache_n,
        "predicted_n": predicted_n,
        "prompt_ms": prompt_ms,
        "predicted_ms": predicted_ms,
        "prompt_tps": prompt_tps,
        "gen_tps": predicted_tps,
        "client_ttft_s": client_ttft_s,
        "ttft_status": ttft_status,
        "total_elapsed": total_elapsed,
        "finish_reason": finish_reason or "unknown",
        "transport_error": transport_error
    }

def run_warmup_protocol():
    """Ejecuta 2 corridas no contabilizadas previas a las mediciones oficiales."""
    print(f"--- Protocolo de Calentamiento ({WARMUP_RUNS} corridas no contabilizadas) ---")
    for w in range(1, WARMUP_RUNS + 1):
        clear_slot_cache()
        time.sleep(1)
        w_text = "def warmup_step(): return 1 + 1\n" * 15
        res = send_chat_completion(w_text, target_gen=16)
        print(f"  Warmup {w}/{WARMUP_RUNS}: Prompt={res['prompt_n']} tok, Gen={res['predicted_n']} tok (completado)")
    clear_slot_cache()
    time.sleep(1)
    print("Calentamiento finalizado. Iniciando mediciones oficiales.\n")

def run_benchmark():
    if not os.path.exists(BIN_PATH) or not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"Binario o modelo no encontrado en: {BIN_PATH}, {MODEL_PATH}")

    if is_port_in_use(PORT):
        raise RuntimeError(
            f"El puerto {PORT} está ocupado por otro proceso. "
            "No se cerrará ningún proceso externo automáticamente. "
            "Libera el puerto o cambia la variable PORT para continuar de forma segura."
        )

    os.makedirs(SLOT_SAVE_PATH, exist_ok=True)

    server_cmd = [
        BIN_PATH,
        "-m", MODEL_PATH,
        "-c", str(CONFIGURED_CTX),
        "-t", "8",
        "-tb", "8",
        "-b", "512",
        "-ub", "128",
        "-fa", "off",
        "-ctk", "f16",
        "-ctv", "f16",
        "--port", str(PORT),
        "--host", "127.0.0.1",
        "-np", "1",
        "-lm", "mmap",
        "--slot-save-path", SLOT_SAVE_PATH
    ]

    print("=" * 115)
    print("      BENCHMARK DE CONTEXTO REAL: GENERACIÓN TRAS INGESTA DE CONTEXTO")
    print("=" * 115)
    print(f"Contexto Configurado (-c): {CONFIGURED_CTX} tokens")
    print(f"Tokens Objetivo a Generar: {TARGET_GEN_TOKENS} tokens")
    print(f"Hilos: 8 | KV-Cache: FP16 | Flash Attention: OFF | Repeticiones: {REPETITIONS}")
    print(f"Calentamiento: {WARMUP_RUNS} corridas | Log del servidor: {LOG_PATH}\n")

    with open(LOG_PATH, "a", encoding="utf-8") as lf:
        lf.write(f"\n--- INICIO BENCHMARK CONTEXTO: {' '.join(server_cmd)} ---\n")
        lf.flush()
        proc = subprocess.Popen(server_cmd, stdout=lf, stderr=subprocess.STDOUT)

    try:
        print("Iniciando servidor de prueba en puerto 8083...", flush=True)
        if not wait_for_server(timeout=35):
            raise TimeoutError(f"El servidor no respondió en el tiempo límite. Revisa {LOG_PATH}")

        print("Servidor listo. Verificando compatibilidad de limpieza de slots (/slots/0?action=erase)...", flush=True)
        verify_slot_erase_capability()
        print("Verificación de limpieza de slots EXITOSA.\n", flush=True)

        # Ejecución del protocolo de calentamiento
        run_warmup_protocol()

        benchmark_results = []

        for target_ctx in EVALUATED_PROMPT_LENGTHS:
            print(f">>> Evaluando Longitud Objetivo: ~{target_ctx} tokens de contexto...")
            prompt_body = build_prompt_with_token_target(target_ctx)

            runs_detail = []

            for rep in range(1, REPETITIONS + 1):
                slot_erase_res = clear_slot_cache()
                time.sleep(1)

                res = send_chat_completion(prompt_body, target_gen=TARGET_GEN_TOKENS)

                # Evaluación estricta de validez distinguiendo categorías de exclusión
                is_valid = True
                error_category = "none"  # "none" | "transport_or_timeout_error" | "model_early_termination" | "cache_contamination"
                exclusions = []

                if res.get("transport_error") or res["client_ttft_s"] is None or res["ttft_status"] != "ok":
                    is_valid = False
                    error_category = "transport_or_timeout_error"
                    exclusions.append(f"transport_or_timeout_error ({res['ttft_status']})")
                elif res["cache_n"] is None:
                    is_valid = False
                    error_category = "unverified_cache_state"
                    exclusions.append("unverified_cache_state (cache_n ausente o invalido en timings; no se asume 0)")
                elif res["cache_n"] > 0:
                    is_valid = False
                    error_category = "cache_contamination"
                    exclusions.append(f"cache_contamination (reported cache_n={res['cache_n']} > 0)")
                elif res["predicted_n"] < TARGET_GEN_TOKENS or res["finish_reason"] in ("stop", "eos"):
                    is_valid = False
                    error_category = "model_early_termination"
                    exclusions.append(f"model_early_termination (reported {res['predicted_n']}/{TARGET_GEN_TOKENS} tokens, finish_reason='{res['finish_reason']}')")
                elif res["finish_reason"] != "length":
                    is_valid = False
                    error_category = "model_early_termination"
                    exclusions.append(f"non_length_finish_reason (finish_reason='{res['finish_reason']}')")

                exclusion_reason = "; ".join(exclusions) if exclusions else None

                run_entry = {
                    "repetition": rep,
                    "target_prompt_tokens": target_ctx,
                    "reported_prompt_n": res["prompt_n"],
                    "reported_cache_n": res["cache_n"],
                    "target_gen_tokens": TARGET_GEN_TOKENS,
                    "reported_predicted_n": res["predicted_n"],
                    "prompt_ms": res["prompt_ms"],
                    "predicted_ms": res["predicted_ms"],
                    "prompt_tps": res["prompt_tps"],
                    "gen_tps": res["gen_tps"],
                    "client_ttft_sse_s": res["client_ttft_s"],
                    "ttft_status": res["ttft_status"],
                    "total_http_s": res["total_elapsed"],
                    "finish_reason": res["finish_reason"],
                    "slot_erase_verified": slot_erase_res["erase_verified"],
                    "is_valid_for_gen_comparison": is_valid,
                    "error_category": error_category,
                    "exclusion_reason": exclusion_reason
                }

                runs_detail.append(run_entry)

                status_label = "[VALIDA]" if is_valid else f"[EXCLUIDA: {error_category} - {exclusion_reason}]"
                ttft_dsp = f"{res['client_ttft_s']:.2f}s" if res['client_ttft_s'] is not None else f"N/A ({res['ttft_status']})"
                print(
                    f"  Corrida {rep}/{REPETITIONS} {status_label}: "
                    f"Prompt={res['prompt_n']} tok (obj {target_ctx}) @ {res['prompt_tps']:.1f} t/s | "
                    f"Gen={res['predicted_n']} tok (obj {TARGET_GEN_TOKENS}) @ {res['gen_tps']:.2f} t/s | "
                    f"TTFT={ttft_dsp} | HTTP Total={res['total_elapsed']:.2f}s"
                )

            valid_runs = [r for r in runs_detail if r["is_valid_for_gen_comparison"]]
            valid_count = len(valid_runs)
            early_terminations_count = sum(1 for r in runs_detail if r["error_category"] == "model_early_termination")
            transport_errors_count = sum(1 for r in runs_detail if r["error_category"] == "transport_or_timeout_error")
            cache_reuse_count = sum(1 for r in runs_detail if r["error_category"] == "cache_contamination")
            excluded_count = len(runs_detail) - valid_count

            valid_gen_tps = [r["gen_tps"] for r in valid_runs]
            all_gen_tps = [r["gen_tps"] for r in runs_detail]
            all_prompt_tps = [r["prompt_tps"] for r in runs_detail]
            all_prompt_ms = [r["prompt_ms"] for r in runs_detail]
            all_ttft = [r["client_ttft_sse_s"] for r in runs_detail if r["client_ttft_sse_s"] is not None]
            all_total_s = [r["total_http_s"] for r in runs_detail]

            entry = {
                "target_prompt_tokens": target_ctx,
                "configured_context_window": CONFIGURED_CTX,
                "target_gen_tokens": TARGET_GEN_TOKENS,
                "raw_samples": {
                    "runs": runs_detail,
                    "runs_prompt_n": [r["reported_prompt_n"] for r in runs_detail],
                    "runs_predicted_n": [r["reported_predicted_n"] for r in runs_detail],
                    "runs_prompt_ms": all_prompt_ms,
                    "runs_prompt_tps": all_prompt_tps,
                    "runs_gen_ms": [r["predicted_ms"] for r in runs_detail],
                    "runs_gen_tps": all_gen_tps,
                    "runs_client_ttft_s": [r["client_ttft_sse_s"] for r in runs_detail],
                    "runs_total_http_s": all_total_s,
                    "runs_validity": [r["is_valid_for_gen_comparison"] for r in runs_detail],
                    "runs_error_categories": [r["error_category"] for r in runs_detail]
                },
                "summary_statistics": {
                    "total_runs": REPETITIONS,
                    "valid_runs_count": valid_count,
                    "early_terminations_count": early_terminations_count,
                    "transport_errors_count": transport_errors_count,
                    "cache_reuse_count": cache_reuse_count,
                    "excluded_runs_count": excluded_count,
                    "reported_prompt_n_median": statistics.median([r["reported_prompt_n"] for r in runs_detail]),
                    "reported_predicted_n_median": statistics.median([r["reported_predicted_n"] for r in runs_detail]),
                    "median_prompt_tps": statistics.median(all_prompt_tps) if all_prompt_tps else 0.0,
                    "stddev_prompt_tps": statistics.stdev(all_prompt_tps) if len(all_prompt_tps) > 1 else 0.0,
                    "median_prompt_duration_s": statistics.median(all_prompt_ms) / 1000.0 if all_prompt_ms else 0.0,
                    "median_gen_tps_valid": statistics.median(valid_gen_tps) if valid_gen_tps else None,
                    "stddev_gen_tps_valid": (statistics.stdev(valid_gen_tps) if len(valid_gen_tps) > 1 else 0.0) if valid_gen_tps else None,
                    "all_runs_gen_tps_median": statistics.median(all_gen_tps) if all_gen_tps else 0.0,
                    "median_client_ttft_s": statistics.median(all_ttft) if all_ttft else None,
                    "median_total_http_s": statistics.median(all_total_s) if all_total_s else 0.0,
                    "exclusions_detail": [
                        {
                            "repetition": r["repetition"],
                            "error_category": r["error_category"],
                            "reason": r["exclusion_reason"],
                            "reported_predicted_n": r["reported_predicted_n"],
                            "finish_reason": r["finish_reason"]
                        }
                        for r in runs_detail if not r["is_valid_for_gen_comparison"]
                    ]
                }
            }
            benchmark_results.append(entry)
            print()

        print("=" * 130)
        print("              TABLA CONSOLIDADA: GENERACIÓN VS LONGITUD DE CONTEXTO")
        print("=" * 130)
        print(f"{'Prompt (Obj/Real)':<18} | {'Ctx Config':<12} | {'Ingesta Mediana':<16} | {'TTFT Real':<12} | {'Gen (Obj/Real)':<16} | {'Gen t/s (Válidas)':<18} | {'Válidas (Early/Net/Cache)':<26}")
        print("-" * 130)
        for b in benchmark_results:
            stats = b["summary_statistics"]
            p_str = f"{b['target_prompt_tokens']} / {int(stats['reported_prompt_n_median'])}"
            g_str = f"{b['target_gen_tokens']} / {int(stats['reported_predicted_n_median'])}"
            if stats["median_gen_tps_valid"] is not None:
                tps_str = f"{stats['median_gen_tps_valid']:.2f} ± {stats['stddev_gen_tps_valid']:.2f}"
            else:
                tps_str = f"N/A (sin válidas: {stats['all_runs_gen_tps_median']:.2f} global)"
            ttft_str = f"{stats['median_client_ttft_s']:.2f} seg" if stats['median_client_ttft_s'] is not None else "N/A"
            ratio_str = f"{stats['valid_runs_count']}/{stats['total_runs']} (E:{stats['early_terminations_count']} N:{stats['transport_errors_count']} C:{stats['cache_reuse_count']})"
            print(f"{p_str:<18} | {b['configured_context_window']:>5} tokens  | {stats['median_prompt_tps']:>6.2f} ± {stats['stddev_prompt_tps']:<4.2f} t/s | {ttft_str:>6}   | {g_str:<16} | {tps_str:<18} | {ratio_str:<26}")
        print("=" * 130)

        with open(RESULTS_PATH, "w", encoding="utf-8") as rf:
            json.dump(benchmark_results, rf, indent=2)
        print(f"\nResultados completos y muestras crudas guardados en: {RESULTS_PATH}")

    finally:
        if proc and proc.poll() is None:
            print("Cerrando servidor de benchmark de forma segura...", flush=True)
            try:
                proc.terminate()
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                    proc.wait(timeout=3)
                except Exception:
                    pass
        if os.path.exists(SLOT_SAVE_PATH):
            try:
                shutil.rmtree(SLOT_SAVE_PATH, ignore_errors=True)
            except Exception:
                pass
        time.sleep(1)

def main():
    print("AVISO: Este script define el benchmark de contexto real (5 repeticiones + 2 warmups).")
    print("Por directiva estricta de auditoría, NO se ejecuta automáticamente.")
    print("Para ejecutar en el futuro cuando sea autorizado: python test_context_generation.py --run")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--run":
        run_benchmark()
    else:
        main()
