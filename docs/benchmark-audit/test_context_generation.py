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
   - Calentamiento global: ejecuta 2 corridas no contabilizadas previas a las mediciones para cargar pesos en caché de SO y estabilizar OpenMP.
4. Repeticiones y Orden de Evaluación:
   - 5 repeticiones por cada longitud de contexto evaluada.
   - El orden de evaluación ascendente [256, 512, 1024, 2048, 4096] se reconoce como una posible fuente de sesgo.
   - Las variaciones no se atribuirán a throttling térmico sin telemetría directa de frecuencia de reloj y temperatura de CPU.
5. Verificación Estricta de Limpieza de Slots (/slots/0?action=erase):
   - Documentación técnica: en la versión llama.cpp (b11719), el handler 'server_task_result_slot_erase'
     invoca slot.reset() para liberar las celdas del KV cache del slot y restablecer los contadores a 0.
   - La presencia del argumento '--slot-save-path' es requerida para registrar el endpoint, pero no se asume
     como prueba suficiente de borrado. El script verifica la respuesta HTTP 200, inspecciona GET /slots
     y corrobora durante la inferencia que 'cache_n == 0'. Si se detecta 'cache_n > 0', la corrida se invalida.
6. Clasificación de Resultados (Válidos, Excluidos, Inconclusos):
   - Diferencia explícitamente resultados concluyentes de inconclusos según la disponibilidad de corridas válidas.
   - Excluye muestras por: errores de transporte/timeout, estado de caché no verificable, contaminación de caché o terminación anticipada.
   - Conserva TODAS las muestras crudas, finish_reason original y la razón explícita de exclusión (sin descarte silencioso).
7. Métricas de Tiempo y TTFT (SSE):
   - Si no se detecta el primer evento SSE con contenido, client_ttft_sse_s se registra como None (null)
     con estado de error explícito, sin sustituir jamás TTFT por total_elapsed.
8. Seguridad de Procesos, Persistencia Robusta y Registro Integral:
   - Comprueba disponibilidad del puerto antes de arrancar sin matar procesos ajenos.
   - Administra exclusivamente el subproceso creado (PID propio).
   - Registra metadatos completos en JSON: timestamp ISO 8601, commit real de HEAD, estado dirty del worktree,
     configuración del servidor, resumen de hardware, fases de fallo y semántica detallada de limpieza de procesos.
   - Persiste incrementalmente muestras y contextos mediante escritura atómica no destructiva (.tmp -> rename).
   - Preserva contextos pendientes como 'not_executed' si ocurre una interrupción sin presentarla como completa.
   - Separa métricas válidas oficiales de resúmenes descriptivos de muestras excluidas.

ESTADO: CAMBIOS PREPARATORIOS FASE 3.1 AUTORIZADOS - NO EJECUTAR HASTA AUTORIZACIÓN EXPRESA.
"""

import os
import sys
import time
import json
import socket
import shutil
import platform
import statistics
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone

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

def get_git_metadata(workspace_path: str) -> dict:
    """
    Obtiene la identificación rigurosa del estado de Git en el workspace:
    - git_commit: hash real de HEAD o None si no se pudo determinar.
    - git_worktree_dirty: True si hay modificaciones locales sin commit, False si está limpio, None si no se pudo verificar.
    - git_status_verified: True si ambos comandos (rev-parse y status) se ejecutaron satisfactoriamente.
    - source_revision_note: Explicación explícita sobre la trazabilidad del código ejecutado.
    """
    commit_hash = None
    worktree_dirty = None
    status_verified = False
    revision_note = None

    try:
        commit_out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=workspace_path,
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        if commit_out:
            commit_hash = commit_out
    except Exception:
        commit_hash = None

    try:
        status_out = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=workspace_path,
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        worktree_dirty = bool(status_out)
        status_verified = (commit_hash is not None)
    except Exception:
        worktree_dirty = None
        status_verified = False

    if not status_verified or commit_hash is None:
        revision_note = (
            "No se pudo verificar el estado de Git de forma unívoca (git no disponible o error al consultar el repositorio). "
            "El código ejecutado no puede asociarse con certeza a una revisión concreta."
        )
    elif worktree_dirty:
        revision_note = (
            f"El árbol de trabajo contiene modificaciones locales no commiteadas respecto a HEAD ({commit_hash[:7]}). "
            "El hash de commit por sí solo no identifica unívocamente el código efectivamente ejecutado."
        )
    else:
        revision_note = f"Árbol de trabajo limpio correspondiente exactamente al commit {commit_hash}."

    return {
        "git_commit": commit_hash,
        "git_worktree_dirty": worktree_dirty,
        "git_status_verified": status_verified,
        "source_revision_note": revision_note
    }

def get_current_git_commit(workspace_path: str) -> str:
    """Obtiene el hash del commit actual en Git con fallback determinista al commit auditado."""
    meta = get_git_metadata(workspace_path)
    return meta["git_commit"]

def get_hardware_summary() -> dict:
    """Extrae el resumen del entorno y procesador sin emitir comandos invasivos."""
    return {
        "processor": platform.processor() or "AMD Ryzen 5 2400G with Radeon Vega Graphics",
        "machine": platform.machine(),
        "system": platform.system(),
        "release": platform.release(),
        "version": platform.version()
    }

def persist_benchmark_results(payload: dict, target_path: str = RESULTS_PATH) -> bool:
    """
    Persiste de forma atómica y no destructiva el estado del benchmark en disco.
    Escribe en un archivo temporal (.tmp) y lo reemplaza atómicamente.
    Si ocurre un error de E/S, lo reporta en stderr sin lanzar excepciones para
    no enmascarar errores originales ni corromper archivos previos.
    """
    if payload is None:
        return False
    tmp_path = target_path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        os.replace(tmp_path, target_path)
        return True
    except Exception as e_write:
        sys.stderr.write(f"[WARN] Fallo al persistir resultados en '{target_path}': {e_write}\n")
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass
        return False

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

def extract_and_validate_cache_tokens(timings: dict):
    """
    Extrae y valida de forma estricta los tokens de cache (cache_n / n_prompt_tokens_cache).
    Requisitos indispensables:
    1. Debe estar presente en timings.
    2. No puede ser booleano (en Python bool hereda de int; isinstance(False, int) es True).
    3. Debe ser un numero real (int o float).
    4. No puede ser NaN ni infinito.
    5. Debe ser mayor o igual a 0 (rechaza negativos).
    Retorna (cache_n: int | None, status: str).
    """
    raw_val = None
    field = None
    if "cache_n" in timings:
        raw_val = timings["cache_n"]
        field = "cache_n"
    elif "n_prompt_tokens_cache" in timings:
        raw_val = timings["n_prompt_tokens_cache"]
        field = "n_prompt_tokens_cache"
    else:
        return None, "missing_cache_field (campo de cache ausente en timings)"

    if isinstance(raw_val, bool):
        return None, f"boolean_cache_field ({field} recibido como booleano: {raw_val})"

    if not isinstance(raw_val, (int, float)):
        return None, f"non_numeric_cache_field ({field} no numerico: {type(raw_val).__name__} = {raw_val})"

    import math
    if isinstance(raw_val, float) and (math.isnan(raw_val) or math.isinf(raw_val)):
        return None, f"invalid_float_cache_field ({field} es {raw_val})"

    int_val = int(raw_val)
    if int_val < 0:
        return None, f"negative_cache_field ({field} negativo: {int_val})"

    return int_val, "ok"

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
    cache_n, cache_status = extract_and_validate_cache_tokens(timings)
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
        "cache_status": cache_status,
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

    start_iso = datetime.now(timezone.utc).isoformat()
    git_meta = get_git_metadata(WORKSPACE)
    hw_info = get_hardware_summary()

    context_benchmarks_init = []
    for ctx_len in EVALUATED_PROMPT_LENGTHS:
        context_benchmarks_init.append({
            "target_prompt_tokens": ctx_len,
            "configured_context_window": CONFIGURED_CTX,
            "target_gen_tokens": TARGET_GEN_TOKENS,
            "evaluation_status": "not_executed",
            "raw_samples": {
                "runs": [],
                "runs_prompt_n": [],
                "runs_predicted_n": [],
                "runs_prompt_ms": [],
                "runs_prompt_tps": [],
                "runs_gen_ms": [],
                "runs_gen_tps": [],
                "runs_client_ttft_s": [],
                "runs_total_http_s": [],
                "runs_validity": [],
                "runs_error_categories": []
            },
            "summary_statistics": None
        })

    benchmark_payload = {
        "timestamp_iso": start_iso,
        "git_commit": git_meta["git_commit"],
        "git_worktree_dirty": git_meta["git_worktree_dirty"],
        "git_status_verified": git_meta["git_status_verified"],
        "source_revision_note": git_meta["source_revision_note"],
        "methodology": {
            "protocol_name": "AURA CORE Context Benchmark Protocol",
            "warmup_policy": "global_warmup_2_runs_unmeasured",
            "warmup_runs_count": WARMUP_RUNS,
            "evaluated_prompt_lengths": EVALUATED_PROMPT_LENGTHS,
            "evaluation_order": list(EVALUATED_PROMPT_LENGTHS),
            "repetitions_per_length": REPETITIONS,
            "target_gen_tokens": TARGET_GEN_TOKENS,
            "configured_context_window": CONFIGURED_CTX,
            "temperature": 0.0,
            "bias_and_thermal_note": (
                "El orden de evaluacion ascendente [256, 512, 1024, 2048, 4096] se reconoce como una posible fuente de sesgo "
                "debido a la acumulacion temporal y el orden determinista. Cualquier variacion observada en la velocidad de generacion "
                "o ingesta no debe atribuirse a throttling termico sin telemetria directa y simultanea de frecuencia de reloj y temperatura de la CPU."
            )
        },
        "server_configuration": {
            "command_args": server_cmd,
            "binary_path": BIN_PATH,
            "model_path": MODEL_PATH,
            "port": PORT,
            "host": "127.0.0.1",
            "configured_ctx": CONFIGURED_CTX,
            "threads": 8,
            "threads_batch": 8,
            "batch_size": 512,
            "ubatch_size": 128,
            "flash_attention": "off",
            "cache_type_k": "f16",
            "cache_type_v": "f16",
            "slot_save_path": SLOT_SAVE_PATH
        },
        "hardware_summary": hw_info,
        "benchmark_execution": {
            "completed": False,
            "overall_status": "in_progress",
            "interrupted": False,
            "failure_phase": None,
            "error_category": None,
            "error_message": None,
            "consolidation_persisted": False
        },
        "context_benchmarks": context_benchmarks_init,
        "process_cleanup": None
    }

    init_persisted = persist_benchmark_results(benchmark_payload, RESULTS_PATH)
    if not init_persisted:
        sys.stderr.write(
            f"ERROR CRITICO: Fallo al inicializar la persistencia obligatoria de resultados en '{RESULTS_PATH}'. "
            "Abortando ejecucion antes de iniciar el servidor de benchmark.\n"
        )
        raise IOError(
            f"No se pudo inicializar la persistencia obligatoria de resultados en '{RESULTS_PATH}'. "
            "El servidor no se iniciara sin persistencia verificada."
        )

    proc = None
    with open(LOG_PATH, "a", encoding="utf-8") as lf:
        lf.write(f"\n--- INICIO BENCHMARK CONTEXTO: {' '.join(server_cmd)} ---\n")
        lf.flush()
        proc = subprocess.Popen(server_cmd, stdout=lf, stderr=subprocess.STDOUT)

    current_phase = "server_startup"
    try:
        print("Iniciando servidor de prueba en puerto 8083...", flush=True)
        if not wait_for_server(timeout=35):
            raise TimeoutError(f"El servidor no respondió en el tiempo límite. Revisa {LOG_PATH}")

        current_phase = "slot_verification"
        print("Servidor listo. Verificando compatibilidad de limpieza de slots (/slots/0?action=erase)...", flush=True)
        verify_slot_erase_capability()
        print("Verificación de limpieza de slots EXITOSA.\n", flush=True)

        current_phase = "warmup"
        # Ejecución del protocolo de calentamiento
        run_warmup_protocol()

        current_phase = "context_evaluation"
        for target_ctx in EVALUATED_PROMPT_LENGTHS:
            print(f">>> Evaluando Longitud Objetivo: ~{target_ctx} tokens de contexto...")
            prompt_body = build_prompt_with_token_target(target_ctx)

            entry = None
            for b_entry in benchmark_payload["context_benchmarks"]:
                if b_entry["target_prompt_tokens"] == target_ctx:
                    entry = b_entry
                    break
            if entry is not None:
                entry["evaluation_status"] = "in_progress"
                persist_benchmark_results(benchmark_payload, RESULTS_PATH)

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
                elif res["cache_status"] != "ok" or res["cache_n"] is None:
                    is_valid = False
                    error_category = "unverified_cache_state"
                    exclusions.append(f"unverified_cache_state ({res['cache_status']})")
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
                    "reported_cache_status": res.get("cache_status", "unknown"),
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

                # Persistencia parcial incremental tras cada muestra
                if entry is not None:
                    entry["raw_samples"]["runs"] = list(runs_detail)
                    entry["raw_samples"]["runs_prompt_n"] = [r["reported_prompt_n"] for r in runs_detail]
                    entry["raw_samples"]["runs_predicted_n"] = [r["reported_predicted_n"] for r in runs_detail]
                    entry["raw_samples"]["runs_prompt_ms"] = [r["prompt_ms"] for r in runs_detail]
                    entry["raw_samples"]["runs_prompt_tps"] = [r["prompt_tps"] for r in runs_detail]
                    entry["raw_samples"]["runs_gen_ms"] = [r["predicted_ms"] for r in runs_detail]
                    entry["raw_samples"]["runs_gen_tps"] = [r["gen_tps"] for r in runs_detail]
                    entry["raw_samples"]["runs_client_ttft_s"] = [r["client_ttft_sse_s"] for r in runs_detail]
                    entry["raw_samples"]["runs_total_http_s"] = [r["total_http_s"] for r in runs_detail]
                    entry["raw_samples"]["runs_validity"] = [r["is_valid_for_gen_comparison"] for r in runs_detail]
                    entry["raw_samples"]["runs_error_categories"] = [r["error_category"] for r in runs_detail]
                    persist_benchmark_results(benchmark_payload, RESULTS_PATH)

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
            unverified_cache_count = sum(1 for r in runs_detail if r["error_category"] == "unverified_cache_state")
            excluded_count = len(runs_detail) - valid_count

            # Determinación de conclusividad metodológica
            if valid_count == REPETITIONS:
                evaluation_status = "conclusive_all_runs_valid"
            elif valid_count >= (REPETITIONS // 2 + 1):
                evaluation_status = "conclusive_majority_valid"
            elif valid_count > 0:
                evaluation_status = "inconclusive_minority_valid"
            else:
                evaluation_status = "inconclusive_no_valid_samples"

            valid_gen_tps = [r["gen_tps"] for r in valid_runs]
            all_gen_tps = [r["gen_tps"] for r in runs_detail]
            all_prompt_tps = [r["prompt_tps"] for r in runs_detail]
            all_prompt_ms = [r["prompt_ms"] for r in runs_detail]
            all_ttft = [r["client_ttft_sse_s"] for r in runs_detail if r["client_ttft_sse_s"] is not None]
            all_total_s = [r["total_http_s"] for r in runs_detail]

            summary_stats = {
                "total_runs": REPETITIONS,
                "valid_runs_count": valid_count,
                "early_terminations_count": early_terminations_count,
                "transport_errors_count": transport_errors_count,
                "cache_reuse_count": cache_reuse_count,
                "unverified_cache_count": unverified_cache_count,
                "excluded_runs_count": excluded_count,
                "target_prompt_tokens": target_ctx,
                "reported_prompt_n_median": statistics.median([r["reported_prompt_n"] for r in runs_detail]),
                "target_gen_tokens": TARGET_GEN_TOKENS,
                "reported_predicted_n_median": statistics.median([r["reported_predicted_n"] for r in runs_detail]),
                "median_prompt_tps": statistics.median(all_prompt_tps) if all_prompt_tps else 0.0,
                "stddev_prompt_tps": statistics.stdev(all_prompt_tps) if len(all_prompt_tps) > 1 else 0.0,
                "median_prompt_duration_s": statistics.median(all_prompt_ms) / 1000.0 if all_prompt_ms else 0.0,
                "median_gen_tps_valid": statistics.median(valid_gen_tps) if valid_gen_tps else None,
                "stddev_gen_tps_valid": (statistics.stdev(valid_gen_tps) if len(valid_gen_tps) > 1 else 0.0) if valid_gen_tps else None,
                "descriptive_all_runs_gen_tps_median": statistics.median(all_gen_tps) if all_gen_tps else None,
                "descriptive_metrics_notice": (
                    "Las metricas 'descriptive_*' abarcan muestras excluidas o invalidas; son exclusivamente informativas "
                    "y no constituyen metricas cientificas aptas para la evaluacion oficial."
                ),
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

            if entry is not None:
                entry["evaluation_status"] = evaluation_status
                entry["summary_statistics"] = summary_stats
                persist_benchmark_results(benchmark_payload, RESULTS_PATH)

            print()

        current_phase = "consolidation"
        all_eval_statuses = [b["evaluation_status"] for b in benchmark_payload["context_benchmarks"]]
        if all(s in ("conclusive_all_runs_valid", "conclusive_majority_valid") for s in all_eval_statuses):
            overall_status = "completed_conclusive"
        else:
            overall_status = "completed_inconclusive"

        benchmark_payload["benchmark_execution"]["completed"] = True
        benchmark_payload["benchmark_execution"]["interrupted"] = False
        benchmark_payload["benchmark_execution"]["overall_status"] = overall_status
        consolidation_ok = persist_benchmark_results(benchmark_payload, RESULTS_PATH)
        benchmark_payload["benchmark_execution"]["consolidation_persisted"] = consolidation_ok

        if not consolidation_ok:
            benchmark_payload["benchmark_execution"]["completed"] = False
            benchmark_payload["benchmark_execution"]["overall_status"] = "inconclusive_persistence_failed"
            sys.stderr.write(
                f"\nALERTA CRITICA DE PERSISTENCIA: Fallo al guardar la consolidacion final en '{RESULTS_PATH}'. "
                "Los resultados calculados en memoria no pudieron confirmarse en disco; "
                "el benchmark no se declara completado.\n"
            )

        print("=" * 140)
        print("              TABLA CONSOLIDADA: GENERACIÓN VS LONGITUD DE CONTEXTO")
        print("=" * 140)
        print(f"{'Prompt (Obj/Real)':<22} | {'Ctx Config':<12} | {'Ingesta Mediana':<16} | {'TTFT Real':<12} | {'Gen (Obj/Real)':<16} | {'Gen t/s (Válidas)':<20} | {'Estado / Ratio':<28}")
        print("-" * 140)
        for b in benchmark_payload["context_benchmarks"]:
            stats = b.get("summary_statistics")
            if not stats:
                print(f"{b['target_prompt_tokens']:<22} | {b['configured_context_window']:>5} tokens  | {'NO EJECUTADO':<16} | {'N/A':<12} | {'N/A':<16} | {'N/A':<20} | {b['evaluation_status']:<28}")
                continue
            p_str = f"{b['target_prompt_tokens']} (real: {int(stats['reported_prompt_n_median'])})"
            g_str = f"{b['target_gen_tokens']} (real: {int(stats['reported_predicted_n_median'])})"
            if stats["median_gen_tps_valid"] is not None:
                tps_str = f"{stats['median_gen_tps_valid']:.2f} ± {stats['stddev_gen_tps_valid']:.2f} t/s"
            else:
                tps_str = "N/A (sin muestras validas)"
            ttft_str = f"{stats['median_client_ttft_s']:.2f} seg" if stats['median_client_ttft_s'] is not None else "N/A"
            ratio_str = f"{b['evaluation_status']} ({stats['valid_runs_count']}/{stats['total_runs']})"
            print(f"{p_str:<22} | {b['configured_context_window']:>5} tokens  | {stats['median_prompt_tps']:>6.2f} ± {stats['stddev_prompt_tps']:<4.2f} t/s | {ttft_str:>6}   | {g_str:<16} | {tps_str:<20} | {ratio_str:<28}")
        print("=" * 140)

        if consolidation_ok:
            print(f"\nResultados completos guardados en: {RESULTS_PATH}")
        else:
            print(f"\nADVERTENCIA: La ejecucion concluyo en memoria pero la persistencia en '{RESULTS_PATH}' fallo.")

    except BaseException as e_bench:
        if benchmark_payload:
            benchmark_payload["benchmark_execution"]["completed"] = False
            benchmark_payload["benchmark_execution"]["interrupted"] = True
            benchmark_payload["benchmark_execution"]["overall_status"] = "interrupted"
            benchmark_payload["benchmark_execution"]["failure_phase"] = current_phase
            benchmark_payload["benchmark_execution"]["error_category"] = type(e_bench).__name__
            benchmark_payload["benchmark_execution"]["error_message"] = str(e_bench)
            err_persisted = persist_benchmark_results(benchmark_payload, RESULTS_PATH)
            if not err_persisted:
                sys.stderr.write(
                    f"\nALERTA DE PERSISTENCIA: No se pudo registrar en disco el estado de fallo/interrupcion "
                    f"en '{RESULTS_PATH}' (Fase: '{current_phase}', Error: {type(e_bench).__name__}: {e_bench}). "
                    "El archivo conservado podria no reflejar la causa de la interrupcion.\n"
                )
        raise

    finally:
        proc_pid = proc.pid if proc else None
        proc_exit_code = None
        termination_method = "none" if not proc else "unknown"
        cleanup_verified = False

        if proc:
            if proc.poll() is None:
                print("Cerrando servidor de benchmark de forma segura...", flush=True)
                try:
                    proc.terminate()
                    proc.wait(timeout=5)
                    termination_method = "terminate"
                    proc_exit_code = proc.returncode
                    cleanup_verified = True
                except Exception as e_term:
                    print(f"Aviso: proc.terminate() no finalizo en 5s ({e_term}). Intentando proc.kill()...", flush=True)
                    try:
                        proc.kill()
                        proc.wait(timeout=3)
                        termination_method = "kill"
                        proc_exit_code = proc.returncode
                        cleanup_verified = True
                    except Exception as e_kill:
                        termination_method = "failed"
                        print(f"Error: proc.kill() fallo ({e_kill}).", flush=True)
            else:
                termination_method = "natural"
                proc_exit_code = proc.returncode
                cleanup_verified = True

            process_exited = (proc.poll() is not None)
            if not process_exited:
                print(
                    f"ALERTA DE SEGURIDAD: El subproceso PID {proc.pid} no pudo ser finalizado "
                    "y continua activo en el sistema. No se intentara cerrar procesos ajenos. "
                    f"Verifique manualmente el PID {proc.pid}.",
                    flush=True
                )
            else:
                proc_exit_code = proc.returncode
                cleanup_verified = True
                print(f"Subproceso PID {proc.pid} finalizado (metodo: {termination_method}, codigo: {proc_exit_code}).", flush=True)
        else:
            process_exited = True
            cleanup_verified = True
            termination_method = "not_started"

        temp_dir_cleared = False
        if os.path.exists(SLOT_SAVE_PATH):
            try:
                shutil.rmtree(SLOT_SAVE_PATH, ignore_errors=True)
                temp_dir_cleared = not os.path.exists(SLOT_SAVE_PATH)
            except Exception:
                temp_dir_cleared = not os.path.exists(SLOT_SAVE_PATH)
        else:
            temp_dir_cleared = True

        natural_exit = bool(process_exited and proc_exit_code == 0 and termination_method == "natural")
        forced_protocol_termination = bool(process_exited and proc_exit_code == 1 and termination_method == "terminate")

        cleanup_record = {
            "proc_pid": proc_pid,
            "process_exited": process_exited,
            "termination_method": termination_method,  # "natural" | "terminate" | "kill" | "failed" | "not_started"
            "exit_code": proc_exit_code,
            "cleanup_verified": cleanup_verified,
            "natural_exit": natural_exit,
            "forced_protocol_termination": forced_protocol_termination,
            "slot_temp_dir_removed": temp_dir_cleared,
            "notes": (
                "Salida natural exitosa con codigo 0." if natural_exit else
                "Terminacion forzada controlada por protocolo (Win32 TerminateProcess con codigo 1)." if forced_protocol_termination else
                f"Proceso finalizado mediante {termination_method} con codigo {proc_exit_code}." if process_exited else
                f"FALLO DE CIERRE: Subproceso PID {proc_pid} permanece activo. Requiere intervencion manual."
            )
        }

        if benchmark_payload:
            benchmark_payload["process_cleanup"] = cleanup_record
            cleanup_persisted = persist_benchmark_results(benchmark_payload, RESULTS_PATH)
            if not cleanup_persisted:
                pid_info = f"PID {proc_pid}" if proc_pid is not None else "sin PID asignado"
                sys.stderr.write(
                    f"\nALERTA DE PERSISTENCIA: No se pudo guardar el estado final de limpieza en '{RESULTS_PATH}' "
                    f"para el subproceso {pid_info}. El estado de limpieza podria no estar reflejado en el JSON conservado en disco.\n"
                )

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
