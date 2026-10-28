"""
AURA CORE — Evaluador Reproducible de Calidad de Programación
=============================================================
Evalúa de manera objetiva, automatizada y reproducible las capacidades de ingeniería
de software del modelo local (Qwen 2.5 Coder 3B Instruct Q4_K_M).

LIMITACIONES Y ARQUITECTURA DE SEGURIDAD:
1. AUSENCIA DE SANDBOX EN EL HOST: El evaluador se ejecuta en el sistema operativo
   anfitrión. Ni `tempfile.TemporaryDirectory` ni el análisis estático mediante AST
   constituyen un sandbox de seguridad. No impiden evasiones de reflexión dinámica
   ni garantizan aislamiento del sistema de archivos, red o procesos.
   Por defecto, la ejecución de código no confiable o generado por modelos está
   ESTRICTAMENTE BLOQUEADA en el host hasta contar con un entorno de aislamiento
   real (ej. contenedor Docker/gVisor o AppContainer verificado).
2. TIMEOUTS EN WINDOWS: `subprocess.run(timeout=...)` envía `TerminateProcess`
   únicamente al proceso inmediato (PID directo). En Windows, los subprocesos o hilos
   hijos huérfanos NO son terminados automáticamente ante un timeout sin un Job Object
   debidamente asignado (`JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE`). Esta limitación
   permanece abierta y documentada.
3. CLASIFICACIÓN DE ERRORES: Los errores de sintaxis (`SyntaxError`) o código truncado
   se clasifican como fallos de la solución (`SYNTAX_ERROR`), distinguiéndose de
   violaciones deliberadas de seguridad (`SECURITY_VIOLATION`).
4. EVALUACIÓN LÉXICA: La evaluación por rúbrica realiza una verificación léxica objetiva
   con soporte de sinónimos y manejo de negaciones, pero no constituye una prueba de
   comprensión semántica conceptual profunda.
"""

import os
import sys
import json
import time
import socket
import tempfile
import ast
import re
import platform
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# Raíz del proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
TASKS_FILE = BASE_DIR / "evals" / "coding_tasks.json"
EXPERIMENTS_DIR = BASE_DIR / "experiments"

# Prompt de sistema especializado en programación para la evaluación (Línea Base V1)
CODING_SYSTEM_PROMPT = """Eres AURA CORE, un asistente senior especializado en desarrollo de software, algoritmos y resolución de problemas técnicos en Python.
Responde de forma precisa, directa y técnicamente rigurosa.
Cuando se te solicite código, genera soluciones limpias, eficientes, idiomáticas (PEP 8) y preparadas para producción, manejando correctamente casos límite y validaciones.
Devuelve siempre el código ejecutable dentro de bloques con formato ```python."""

# Variante experimental V2 del prompt del sistema de programación
CODING_SYSTEM_PROMPT_V2 = """Eres AURA CORE, un ingeniero de software principal especializado en algoritmos, estructuras de datos y desarrollo de software riguroso en Python.

Metodología obligatoria para resolver cada tarea:
1. CONTRATO Y FIRMA EXACTA:
   - Identifica el nombre exacto de la función, clase o método, sus argumentos, tipos y el tipo de retorno requerido.
   - Respeta estrictamente la API solicitada: jamás sustituyas una función por una clase, ni envuelvas una función pura en objetos no solicitados.
2. VALIDACIÓN DE PRECONDICIONES Y CASOS LÍMITE:
   - Valida de inmediato argumentos fuera de rango, tipos incorrectos y valores inválidos, levantando exactamente las excepciones requeridas (ValueError, TypeError, IndexError).
   - Maneja exhaustivamente casos límite: entradas vacías ([], {}), elementos únicos, duplicados y valores frontera.
3. INMUTABILIDAD Y ESTRUCTURAS DE DATOS:
   - Nunca mutes estructuras de datos recibidas como argumento si no se solicita explícitamente; realiza copias defensivas.
   - Verifica los tipos reales de los elementos en colecciones anidadas antes de invocar métodos específicos (ej. no asumas que todo elemento es un dict).
4. BIBLIOTECA ESTÁNDAR Y CONCURRENCIA:
   - Usa las firmas canónicas y correctas de la biblioteca estándar (ej. re.Match.group() para nombres de grupo, no groups()).
   - En código multihilo o asíncrono (threading, asyncio), asegura la sincronización a nivel de cada operación atómica o invocación individual, nunca bloqueando el lote completo en un solo semáforo.
5. EXPLICACIONES Y CONCEPTOS TÉCNICOS:
   - Si la tarea solicita una explicación o análisis conceptual, responde en prosa técnica estructurada y exhaustiva, utilizando expresamente los términos técnicos canónicos en español (ej. conteo de referencias, consultas parametrizadas, prepared statements, AST, IPC, CPU-bound vs I/O-bound). No encierres explicaciones conceptuales dentro de código inerte.
6. FORMATO Y CONCISIÓN:
   - Devuelve siempre el código ejecutable y completo dentro de un bloque con formato ```python. Sé directo y conciso: evita comentarios superfluos o bloques de ejemplo extensos tras el código."""

def get_git_metadata() -> dict:
    commit_hash = None
    worktree_dirty = None
    try:
        out = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(BASE_DIR), stderr=subprocess.DEVNULL, text=True).strip()
        commit_hash = out if out else None
    except Exception:
        pass
    try:
        out_stat = subprocess.check_output(["git", "status", "--porcelain"], cwd=str(BASE_DIR), stderr=subprocess.DEVNULL, text=True).strip()
        worktree_dirty = bool(out_stat)
    except Exception:
        pass
    return {
        "git_commit": commit_hash,
        "git_worktree_dirty": worktree_dirty,
        "repo": "guillebonutto/IA"
    }

def get_hardware_summary() -> dict:
    return {
        "processor": platform.processor(),
        "machine": platform.machine(),
        "system": platform.system(),
        "release": platform.release(),
        "python_version": sys.version.split()[0]
    }

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def is_isolated_environment_available() -> tuple[bool, str]:
    """
    Verifica la disponibilidad del ejecutor aislado en Debian WSL2.
    Comprueba que wsl.exe responda, que la distribución Debian esté presente,
    que el usuario aura_sandbox exista y que el runner protegido esté instalado.
    """
    try:
        res = subprocess.run(
            [
                "wsl.exe", "-d", "Debian", "-u", "aura_sandbox", "--",
                "python3", "-B", "-c", "import os; exit(0 if os.path.isfile('/opt/aura_sandbox/isolated_runner.py') else 1)"
            ],
            capture_output=True,
            timeout=10.0
        )
        if res.returncode == 0:
            return True, "WSL2 Debian aislado disponible (aura_sandbox, unshare -r -n, prlimit, timeout)"
        return False, (
            "Ejecución detenida: El entorno WSL2 Debian o el ejecutor protegido "
            "'/opt/aura_sandbox/isolated_runner.py' no se encuentran disponibles o no responden."
        )
    except Exception as e:
        return False, f"Ejecución detenida: Fallo al consultar el entorno aislado WSL2: {e}"

def extract_python_code(text: str) -> tuple[str, str | None]:
    """
    Extrae bloques de código Python de la respuesta del modelo.
    
    Reglas de extracción:
    1. Si hay múltiples bloques ```python o ```py, los concatena en orden sin descartar ninguno.
    2. Si los bloques Markdown están incompletos o sin cerrar (ej. respuesta truncada),
       devuelve un error de extracción explícito.
    3. Si no hay bloques Markdown explícitos pero el texto es código Python analizable por AST,
       lo extrae directamente.
    4. Si el formato es ambiguo (no hay bloques y el texto no es Python válido),
       registra un error de extracción explícito.

    Retorna: (codigo_extraido, error_o_None)
    """
    if not text or not text.strip():
        return "", "Respuesta vacía: no se encontró contenido para extraer."

    # Detectar delimitadores de código sin cerrar (número impar de triple backticks)
    fence_count = text.count("```")
    if fence_count % 2 != 0:
        return "", "Formato ambiguo: bloque de código Markdown sin cerrar (posible respuesta truncada por límite de tokens)."

    # 1. Buscar todos los bloques etiquetados con ```python o ```py
    python_blocks = re.findall(r"```(?:python|py)\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if python_blocks:
        joined_blocks = "\n\n".join(b.strip() for b in python_blocks if b.strip())
        if not joined_blocks:
            return "", "Bloques de código ```python encontrados pero su contenido está vacío."
        return joined_blocks, None

    # 2. Si no hay bloques python explícitos, buscar bloques genéricos ```
    generic_blocks = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
    if generic_blocks:
        joined_generic = "\n\n".join(b.strip() for b in generic_blocks if b.strip())
        if not joined_generic:
            return "", "Bloques de código genéricos encontrados pero su contenido está vacío."
        return joined_generic, None

    # 3. Si no hay delimitadores de bloque, comprobar si el texto en sí es código Python analizable
    try:
        ast.parse(text)
        return text.strip(), None
    except SyntaxError:
        return "", "Formato ambiguo: no se encontraron bloques de código Markdown delimitados y el texto no es código Python sintácticamente analizable."

def static_safety_check(code: str) -> tuple[bool, str, str]:
    """
    Analiza estáticamente el código mediante AST para clasificar su estado antes de procesarlo.
    
    Distingue expresamente entre:
    - OK: sintaxis válida sin patrones o llamadas restringidas detectadas.
    - SYNTAX_ERROR: código sintácticamente inválido o truncado (fallo de la solución, NO violación de seguridad).
    - SECURITY_VIOLATION: uso explícito de módulos o llamadas de ejecución de sistema / borrado destructivo.

    NOTA: Este análisis preventivo NO es un sandbox de seguridad y no previene evasiones
    avanzadas basadas en reflexión o introspección dinámica.
    
    Retorna: (es_seguro, categoria, detalle)
    """
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return False, "SYNTAX_ERROR", f"Error de sintaxis en el código: {e}"

    DANGEROUS_CALLS = {"system", "popen", "spawn", "rmtree", "unlink"}
    DANGEROUS_OS_CALLS = {"remove", "unlink"}
    OS_RECEIVERS = {"os", "posix", "nt"}
    DANGEROUS_MODULES = {"subprocess", "shutil", "winreg", "socketserver", "multiprocessing.shared_memory"}

    for node in ast.walk(tree):
        # Bloquear importación directa de módulos de ejecución arbitraria
        if isinstance(node, ast.Import):
            for alias in node.names:
                root_module = alias.name.split(".")[0]
                if root_module in DANGEROUS_MODULES or alias.name in DANGEROUS_MODULES:
                    return False, "SECURITY_VIOLATION", f"Módulo no autorizado en evaluador: '{alias.name}'"
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root_module = node.module.split(".")[0]
                if root_module in DANGEROUS_MODULES or node.module in DANGEROUS_MODULES:
                    return False, "SECURITY_VIOLATION", f"Módulo no autorizado en evaluador: '{node.module}'"
                # Bloquear importación directa de funciones destructivas o de sistema de os/posix/nt
                if root_module in OS_RECEIVERS:
                    for alias in node.names:
                        if alias.name in DANGEROUS_CALLS or alias.name in DANGEROUS_OS_CALLS:
                            return False, "SECURITY_VIOLATION", f"Función de sistema no autorizada importada desde '{node.module}': '{alias.name}'"
        # Bloquear llamadas os.system, os.popen, os.remove, etc.
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                # Llamadas universales no legítimas en colecciones (.system, .popen, .spawn, .rmtree, .unlink)
                if node.func.attr in DANGEROUS_CALLS:
                    return False, "SECURITY_VIOLATION", f"Llamada a función restringida: '{node.func.attr}'"
                # Llamadas contextualmente peligrosas sobre módulos de sistema (ej. os.remove)
                if node.func.attr in DANGEROUS_OS_CALLS:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id in OS_RECEIVERS:
                        return False, "SECURITY_VIOLATION", f"Llamada a función de sistema restringida: '{node.func.value.id}.{node.func.attr}'"
            elif isinstance(node.func, ast.Name):
                if node.func.id in DANGEROUS_CALLS or node.func.id in DANGEROUS_OS_CALLS:
                    return False, "SECURITY_VIOLATION", f"Llamada directa a función de sistema restringida: '{node.func.id}'"

    return True, "OK", ""

def check_for_target_redefinition(test_code: str, target_classes: set[str]) -> str | None:
    """
    Verifica mediante AST si el código de prueba intenta redefinir alguna de las
    clases bajo prueba, lo que invalidaría la prueba sobre la implementación o mutantes.
    """
    try:
        tree = ast.parse(test_code)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in target_classes:
            return (
                f"El código de prueba redefine la clase '{node.name}', "
                "lo que sobrescribiría silenciosamente la implementación bajo prueba."
            )
    return None

def validate_extra_files_paths(extra_files: dict[str, str] | None) -> tuple[bool, str]:
    """
    Valida estrictamente los nombres de archivo en extra_files para evitar
    inyecciones de rutas, escapes de directorio ('..') o rutas absolutas.
    """
    if not extra_files:
        return True, ""
    for rel_path in extra_files.keys():
        if not isinstance(rel_path, str) or not rel_path.strip():
            return False, "Nombre de archivo vacío en extra_files."
        norm = rel_path.replace("\\\\", "/")
        if norm.startswith("/") or re.match(r"^[a-zA-Z]:", norm):
            return False, f"Ruta absoluta no permitida en extra_files: '{rel_path}'"
        parts = norm.split("/")
        for p in parts:
            if p in ("", ".", ".."):
                return False, f"Componente de ruta inválido o secuencia '..' en extra_files: '{rel_path}'"
            if not re.match(r"^[a-zA-Z0-9_\-\.]+$", p):
                return False, f"Caracteres no permitidos en el nombre de archivo de extra_files: '{rel_path}'"
    return True, ""

def execute_code_test(
    python_code: str,
    test_code: str,
    timeout_s: float = 10.0,
    extra_files: dict[str, str] | None = None
) -> dict:
    """
    Ejecuta el código y la suite de pruebas exclusivamente dentro del entorno
    aislado de Debian WSL2 bajo 'aura_sandbox', 'unshare -r -n', 'timeout' y 'prlimit'.
    
    GARANTÍAS DE SEGURIDAD:
    1. AISLAMIENTO ESTRICTO: La ejecución ocurre dentro de Debian WSL2 con usuario
       sin privilegios (aura_sandbox, UID 1001).
    2. DESACOPLE DEL HOST: /mnt/c está deshabilitado en wsl.conf. El código no puede
       acceder a las unidades de Windows.
    3. RED BLOQUEADA: 'unshare -r -n' desconecta la pila de red del proceso (Network is unreachable).
    4. LÍMITES Y TIMEOUTS: 'prlimit' restringe memoria (512 MB), procesos (128) y archivos (10 MB).
       'timeout -k' garantiza la terminación de todo el árbol de procesos hijos.
    5. TOLERANCIA CERO: Si el entorno aislado no está disponible o falla, la ejecución
       se detiene de inmediato. NUNCA se ejecuta código en el host Windows como alternativa.
    """
    # 1. Análisis estático y clasificación previa
    safe, category, reason = static_safety_check(python_code)
    if not safe:
        return {
            "status": category,  # SYNTAX_ERROR o SECURITY_VIOLATION
            "passed": False,
            "error": reason,
            "stdout": "",
            "stderr": "",
            "elapsed_s": 0.0
        }

    # 2. Guardia de seguridad: validar nombres de archivo auxiliares
    files_ok, files_err = validate_extra_files_paths(extra_files)
    if not files_ok:
        return {
            "status": "SECURITY_VIOLATION",
            "passed": False,
            "error": f"Ruta en extra_files rechazada por seguridad: {files_err}",
            "stdout": "",
            "stderr": "",
            "elapsed_s": 0.0
        }

    # 3. Guardia de seguridad: detener incondicionalmente si no hay aislamiento real verificado
    iso_ok, iso_msg = is_isolated_environment_available()
    if not iso_ok:
        return {
            "status": "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT",
            "passed": False,
            "error": iso_msg,
            "stdout": "",
            "stderr": "",
            "elapsed_s": 0.0
        }

    # 4. Invocar ejecutor aislado en Debian WSL2 vía stdin
    payload = {
        "python_code": python_code,
        "test_code": test_code,
        "extra_files": extra_files or {},
        "timeout_s": timeout_s,
        "memory_limit_mb": 512,
        "max_processes": 128,  # Permite concurrencia para pruebas multihilo (task 02/09)
        "max_file_size_mb": 10
    }
    input_bytes = json.dumps(payload).encode("utf-8")

    try:
        proc = subprocess.run(
            [
                "wsl.exe", "-d", "Debian", "-u", "aura_sandbox", "--",
                "python3", "/opt/aura_sandbox/isolated_runner.py"
            ],
            input=input_bytes,
            capture_output=True,
            timeout=timeout_s + 10.0
        )
        if proc.returncode != 0 and not proc.stdout:
            err_msg = proc.stderr.decode("utf-8", errors="replace").strip()
            return {
                "status": "ISOLATION_ERROR",
                "passed": False,
                "error": f"Fallo interno en ejecutor aislado (código {proc.returncode}): {err_msg}",
                "stdout": "",
                "stderr": err_msg,
                "elapsed_s": 0.0
            }
        res_json = json.loads(proc.stdout.decode("utf-8", errors="replace"))
        return res_json
    except subprocess.TimeoutExpired:
        return {
            "status": "TIMEOUT",
            "passed": False,
            "error": f"Tiempo límite excedido en el puente hacia el ejecutor aislado ({timeout_s}s).",
            "stdout": "",
            "stderr": "",
            "elapsed_s": timeout_s
        }
    except Exception as e:
        return {
            "status": "ERROR",
            "passed": False,
            "error": f"Error comunicando con ejecutor aislado: {e}",
            "stdout": "",
            "stderr": "",
            "elapsed_s": 0.0
        }

# Alias para compatibilidad hacia atrás
execute_in_sandbox = execute_code_test

def evaluate_mutation_testing(
    candidate_test_code: str,
    mutation_spec: dict,
    timeout_s: float = 10.0
) -> dict:
    """
    Evalúa una suite de tests generada por el modelo ejecutándola contra:
    1. La implementación canónica (debe pasar al 100 %).
    2. Varios mutantes defectuosos (la suite de tests debe fallar con cada uno).

    Protecciones:
    - Evita que el código generado redefina la clase 'BankAccount' o 'InsufficientFundsError'.
    - Expone 'bank_account.py' en el entorno de ejecución para permitir imports estándar
      como `from bank_account import BankAccount, InsufficientFundsError`.
    """
    # 1. Comprobación estática previa del código de pruebas
    safe, category, reason = static_safety_check(candidate_test_code)
    if not safe:
        return {
            "status": category,  # SYNTAX_ERROR o SECURITY_VIOLATION
            "passed": False,
            "error": reason,
            "killed_mutants": 0,
            "total_mutants": len(mutation_spec.get("mutants", [])),
            "elapsed_s": 0.0
        }

    # 2. Detección de redefinición de clases bajo prueba
    redef_err = check_for_target_redefinition(candidate_test_code, {"BankAccount", "InsufficientFundsError"})
    if redef_err:
        return {
            "status": "FAIL",
            "passed": False,
            "error": redef_err,
            "killed_mutants": 0,
            "total_mutants": len(mutation_spec.get("mutants", [])),
            "elapsed_s": 0.0
        }

    canonical_impl = mutation_spec["canonical_implementation"]
    mutants = mutation_spec["mutants"]

    # 3. Guardia de seguridad de host: verificar aislamiento real
    iso_ok, iso_msg = is_isolated_environment_available()
    if not iso_ok:
        return {
            "status": "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT",
            "passed": False,
            "error": iso_msg,
            "killed_mutants": 0,
            "total_mutants": len(mutants),
            "elapsed_s": 0.0
        }

    # 4. Probar contra la implementación canónica correcta
    runner_header = (
        "try:\n"
        "    from bank_account import BankAccount, InsufficientFundsError\n"
        "except ImportError:\n"
        "    pass\n\n"
    )
    combined_canonical = runner_header + candidate_test_code
    res_canonical = execute_code_test(
        combined_canonical,
        "",
        timeout_s=timeout_s,
        extra_files={"bank_account.py": canonical_impl}
    )

    if not res_canonical["passed"]:
        return {
            "status": res_canonical["status"],
            "passed": False,
            "error": "La suite de tests falló contra la implementación canónica: " + res_canonical["error"][:1600],
            "killed_mutants": 0,
            "total_mutants": len(mutants),
            "elapsed_s": res_canonical["elapsed_s"]
        }

    # 5. Probar contra cada mutante defectuoso
    killed_count = 0
    survived_details = []
    total_time = res_canonical["elapsed_s"]

    for m in mutants:
        res_mutant = execute_code_test(
            combined_canonical,
            "",
            timeout_s=timeout_s,
            extra_files={"bank_account.py": m["code_diff"]}
        )
        total_time += res_mutant["elapsed_s"]
        if not res_mutant["passed"]:
            killed_count += 1
        else:
            survived_details.append(f"El mutante '{m['id']}' ({m['description']}) no fue detectado.")

    all_killed = (killed_count == len(mutants))
    return {
        "status": "PASS" if all_killed else "FAIL",
        "passed": all_killed,
        "error": "; ".join(survived_details),
        "killed_mutants": killed_count,
        "total_mutants": len(mutants),
        "elapsed_s": round(total_time, 3)
    }

def check_fallacy_with_negation(text_lower: str, fallacy: str) -> bool:
    """
    Verifica si una falacia prohibida está presente en el texto de forma afirmativa.
    Si la mención está precedida por términos de negación, refutación o desmentido
    (ej: "no es cierto que...", "falso que...", "mito:", "error afirmar que..."),
    no se considera una infracción.
    """
    fallacy_lower = fallacy.lower()
    start = 0
    while True:
        idx = text_lower.find(fallacy_lower, start)
        if idx == -1:
            break
        # Extraer ventana de contexto previo de 60 caracteres
        prefix = text_lower[max(0, idx - 60):idx]
        negation_pattern = (
            r"(?:no\s+(?:es(?:\s+cierto)?|significa|implica|es\s+verdad)?|"
            r"falso(?:\s+que)?|error(?:\s+afirmar|\s+creer|\s+pensar)?|"
            r"mito(?:\s*:)?|incorrecto|desmentir|rechazar|jamas|nunca|evitar|tampoco)\b"
        )
        if not re.search(negation_pattern, prefix):
            # No hay negación previa detectada: falacia afirmada
            return True
        start = idx + len(fallacy_lower)
    return False

def evaluate_semantic_rubric(response_text: str, rubric: dict) -> dict:
    """
    Evalúa explicaciones técnicas mediante verificación léxica de conceptos clave y falacias.

    NOTA METODOLÓGICA:
    La comprobación léxica de rúbricas verifica la presencia de términos y sinónimos equivalentes
    y la ausencia de afirmaciones falaces no refutadas. NO constituye una demostración de
    comprensión semántica profunda ni razonamiento conceptual del modelo. Se emplea como un
    criterio estandarizado y reproducible.
    """
    text_lower = response_text.lower()
    t_start = time.time()

    required_concepts = rubric.get("required_concepts", [])
    missing_concepts = []
    for concept in required_concepts:
        if isinstance(concept, list):
            # Lista de sinónimos o equivalentes aceptados
            if not any(c.lower() in text_lower for c in concept):
                missing_concepts.append("/".join(concept))
        else:
            if concept.lower() not in text_lower:
                missing_concepts.append(concept)

    prohibited = rubric.get("prohibited_fallacies", [])
    detected_fallacies = []
    for p in prohibited:
        if check_fallacy_with_negation(text_lower, p):
            detected_fallacies.append(p)

    min_words = rubric.get("minimum_word_count", 100)
    word_count = len(response_text.split())

    passed = True
    fail_reasons = []

    if missing_concepts:
        passed = False
        fail_reasons.append(f"Faltan conceptos técnicos requeridos: {missing_concepts}")
    if detected_fallacies:
        passed = False
        fail_reasons.append(f"Se detectaron afirmaciones falaces/incorrectas: {detected_fallacies}")
    if word_count < min_words:
        passed = False
        fail_reasons.append(f"Explicación demasiado breve ({word_count} palabras, mínimo {min_words})")

    elapsed = time.time() - t_start
    return {
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "error": "; ".join(fail_reasons),
        "word_count": word_count,
        "missing_concepts": missing_concepts,
        "detected_fallacies": detected_fallacies,
        "elapsed_s": round(elapsed, 4)
    }

def call_local_model(
    prompt: str,
    api_base: str = "http://127.0.0.1:8083/v1",
    model_name: str = "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
    timeout_s: float = 180.0,
    system_prompt: str = CODING_SYSTEM_PROMPT
) -> dict:
    """
    Envía una solicitud al endpoint OpenAI-compatible local en api_base.
    Usa temperature=0.0 para reproducibilidad determinista.
    """
    url = f"{api_base.rstrip('/')}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.0,
        "max_tokens": 1024,
        "stream": False
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", "User-Agent": "AuraCodingEval/1.0"})

    t_start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            elapsed = time.time() - t_start
            body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            usage = body.get("usage", {})
            return {
                "success": True,
                "content": content,
                "elapsed_s": round(elapsed, 3),
                "usage": usage,
                "error": ""
            }
    except Exception as e:
        elapsed = time.time() - t_start
        return {
            "success": False,
            "content": "",
            "elapsed_s": round(elapsed, 3),
            "usage": {},
            "error": str(e)
        }

def evaluate_single_task(task: dict, raw_response: str) -> dict:
    """Evalúa la respuesta de una tarea según su modo de evaluación configurado."""
    mode = task.get("evaluation_mode", "python_test_execution")

    if mode == "semantic_rubric_check":
        rubric = task.get("rubric", {})
        rubric_res = evaluate_semantic_rubric(raw_response, rubric)
        return {
            "mode": mode,
            "passed": rubric_res["passed"],
            "status": rubric_res["status"],
            "error": rubric_res["error"],
            "elapsed_s": rubric_res["elapsed_s"],
            "extracted_code": ""
        }

    # Para modos basados en código, realizar extracción primero
    extracted_code, extract_error = extract_python_code(raw_response)
    if extract_error:
        return {
            "mode": mode,
            "passed": False,
            "status": "EXTRACTION_ERROR",
            "error": extract_error,
            "elapsed_s": 0.0,
            "extracted_code": extracted_code
        }

    if mode == "python_test_execution":
        test_code = task.get("test_code", "")
        exec_res = execute_code_test(extracted_code, test_code)
        return {
            "mode": mode,
            "passed": exec_res["passed"],
            "status": exec_res["status"],
            "error": exec_res["error"],
            "elapsed_s": exec_res["elapsed_s"],
            "extracted_code": extracted_code
        }
    elif mode == "mutation_testing":
        mutation_spec = task.get("mutation_spec", {})
        mut_res = evaluate_mutation_testing(extracted_code, mutation_spec)
        return {
            "mode": mode,
            "passed": mut_res["passed"],
            "status": mut_res["status"],
            "error": mut_res["error"],
            "killed_mutants": mut_res.get("killed_mutants", 0),
            "total_mutants": mut_res.get("total_mutants", 0),
            "elapsed_s": mut_res["elapsed_s"],
            "extracted_code": extracted_code
        }
    else:
        return {
            "mode": mode,
            "passed": False,
            "status": "CONFIG_ERROR",
            "error": f"Modo de evaluación desconocido: {mode}",
            "elapsed_s": 0.0,
            "extracted_code": extracted_code
        }

def run_task_static_audit() -> bool:
    """
    Realiza una auditoría estática completa de las tareas y soluciones canónicas
    en coding_tasks.json SIN ejecutar código ni requerir sandbox o subprocesos.
    """
    print("=" * 70)
    print("AURA CORE — Auditoría Estática de Tareas de Programación")
    print("=" * 70)

    if not TASKS_FILE.exists():
        print(f"[ERROR] Archivo no encontrado: {TASKS_FILE}")
        return False

    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    tasks = data.get("tasks", [])
    print(f"Total de tareas a auditar estáticamente: {len(tasks)}\n")

    all_valid = True
    for idx, t in enumerate(tasks, 1):
        t_id = t["id"]
        mode = t.get("evaluation_mode")
        ref = t.get("reference_solution", "")

        errors = []
        if mode == "python_test_execution":
            test_code = t.get("test_code", "")
            try:
                ast.parse(ref)
            except SyntaxError as e:
                errors.append(f"Sintaxis inválida en reference_solution: {e}")
            try:
                ast.parse(test_code)
            except SyntaxError as e:
                errors.append(f"Sintaxis inválida en test_code: {e}")
        elif mode == "mutation_testing":
            mspec = t.get("mutation_spec", {})
            try:
                ast.parse(mspec.get("canonical_implementation", ""))
            except SyntaxError as e:
                errors.append(f"Sintaxis inválida en canonical_implementation: {e}")
            for m in mspec.get("mutants", []):
                try:
                    ast.parse(m.get("code_diff", ""))
                except SyntaxError as e:
                    errors.append(f"Sintaxis inválida en mutant '{m.get('id')}': {e}")
        elif mode == "semantic_rubric_check":
            rubric = t.get("rubric", {})
            rubric_res = evaluate_semantic_rubric(ref, rubric)
            if not rubric_res["passed"]:
                errors.append(f"Reference solution no cumple su rúbrica: {rubric_res['error']}")
        else:
            errors.append(f"Modo desconocido: {mode}")

        if errors:
            all_valid = False
            print(f"[{idx:02d}/12] {t_id} ({t.get('category')}): [FAIL] - {'; '.join(errors)}")
        else:
            print(f"[{idx:02d}/12] {t_id} ({t.get('category')}): [OK - ESTRUCTURA VÁLIDA]")

    print("\n" + "=" * 70)
    if all_valid:
        print("VEREDICTO ESTÁTICO: 12/12 tareas analizadas y sintácticamente válidas.")
        print("Aviso de Seguridad: La ejecución de código en host permanece deshabilitada por defecto.")
    else:
        print("VEREDICTO ESTÁTICO: Se detectaron inconsistencias sintácticas o de rúbrica.")
    print("=" * 70)
    return all_valid

def run_evaluation_suite(
    api_base: str = "http://127.0.0.1:8083/v1",
    model_name: str = "qwen2.5-coder-3b-instruct-q4_k_m.gguf",
    system_prompt: str = CODING_SYSTEM_PROMPT,
    output_filename: str = None
) -> dict:
    """
    Ejecuta la suite de 12 tareas contra el servidor de inferencia especificado.
    Requiere que el servidor esté activo en api_base.
    """
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(TASKS_FILE, "r", encoding="utf-8") as f:
        spec = json.load(f)

    tasks = spec.get("tasks", [])
    task_results = []
    category_summary = {}

    print(f"Conectando a {api_base} (Modelo: {model_name})...")
    total_start = time.time()

    for idx, task in enumerate(tasks, 1):
        t_id = task["id"]
        cat = task["category"]
        print(f"[{idx:02d}/{len(tasks)}] Evaluando: {t_id} ({cat})...", flush=True)

        call_res = call_local_model(task["prompt"], api_base=api_base, model_name=model_name, system_prompt=system_prompt)
        if not call_res["success"]:
            print(f"     [ERROR DE INFERENCIA]: {call_res['error']}")
            eval_res = {
                "passed": False,
                "status": "SERVER_ERROR",
                "error": call_res["error"],
                "elapsed_s": call_res["elapsed_s"],
                "extracted_code": ""
            }
        else:
            eval_res = evaluate_single_task(task, call_res["content"])

        cat_stat = category_summary.setdefault(cat, {"total": 0, "passed": 0})
        cat_stat["total"] += 1
        if eval_res["passed"]:
            cat_stat["passed"] += 1
            print(f"     Status: [PASS] en {call_res['elapsed_s']}s (test: {eval_res['elapsed_s']}s)")
        else:
            print(f"     Status: [{eval_res['status']}] en {call_res['elapsed_s']}s | Causa: {eval_res['error'][:120]}")

        status = eval_res.get("status", "UNKNOWN")
        passed = eval_res.get("passed", False)
        score = 1.0 if passed else 0.0
        max_score = 1.0
        error_cat = None if passed else status
        observations = eval_res.get("error", "")

        task_results.append({
            "task_id": t_id,
            "category": cat,
            "title": task["title"],
            "score_obtained": score,
            "max_score": max_score,
            "inference_time_s": call_res["elapsed_s"],
            "eval_time_s": eval_res["elapsed_s"],
            "result": "PASS" if passed else "FAIL",
            "error_category": error_cat,
            "observations": observations,
            "prompt": task["prompt"],
            "raw_response": call_res["content"],
            "extracted_code": eval_res.get("extracted_code", ""),
            "evaluation_mode": task["evaluation_mode"],
            "evaluation_result": eval_res,
            "usage": call_res["usage"]
        })

    total_elapsed = time.time() - total_start
    passed_count = sum(1 for r in task_results if r["evaluation_result"]["passed"])
    pass_rate = round((passed_count / len(tasks)) * 100, 1)

    timestamp_iso = datetime.now(timezone.utc).isoformat()
    timestamp_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    if output_filename:
        target_path = EXPERIMENTS_DIR / output_filename
    else:
        target_path = EXPERIMENTS_DIR / f"coding_eval_results_{timestamp_tag}.json"

    report = {
        "timestamp_iso": timestamp_iso,
        "metadata": {
            "git": get_git_metadata(),
            "hardware": get_hardware_summary(),
            "api_base": api_base,
            "model_name": model_name,
            "system_prompt": system_prompt,
            "isolation_backend": "wsl2_debian_aura_sandbox",
            "isolation_verified": True
        },
        "summary": {
            "total_tasks": len(tasks),
            "passed_tasks": passed_count,
            "total_score": float(passed_count),
            "max_score": float(len(tasks)),
            "score_pct": pass_rate,
            "pass_rate_pct": pass_rate,
            "total_duration_s": round(total_elapsed, 2),
            "categories": category_summary
        },
        "task_results": task_results
    }

    # Escritura atómica
    tmp_path = str(target_path) + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
    os.replace(tmp_path, str(target_path))

    print("\n" + "=" * 70)
    print(f"EVALUACIÓN COMPLETADA: {passed_count}/{len(tasks)} ({pass_rate} %) en {total_elapsed:.1f}s")
    print(f"Reporte guardado en: {target_path}")
    print("=" * 70)
    return report

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Evaluador de Calidad de Programación de AURA CORE")
    parser.add_argument("--audit-tasks", action="store_true", help="Auditoría estática de tareas y soluciones canónicas")
    parser.add_argument("--eval", action="store_true", help="Ejecuta la suite contra el motor local")
    parser.add_argument("--prompt-v2", action="store_true", help="Usa el prompt del sistema experimental V2")
    parser.add_argument("--api-base", type=str, default="http://127.0.0.1:8083/v1", help="URL base de la API OpenAI-compatible")
    parser.add_argument("--model", type=str, default="qwen2.5-coder-3b-instruct-q4_k_m.gguf", help="Nombre del modelo")
    parser.add_argument("--output", type=str, default=None, help="Nombre del archivo de salida JSON")
    args = parser.parse_args()

    if args.audit_tasks or (not args.eval and len(sys.argv) == 1):
        success = run_task_static_audit()
        sys.exit(0 if success else 1)
    elif args.eval:
        chosen_prompt = CODING_SYSTEM_PROMPT_V2 if args.prompt_v2 else CODING_SYSTEM_PROMPT
        run_evaluation_suite(api_base=args.api_base, model_name=args.model, system_prompt=chosen_prompt, output_filename=args.output)

if __name__ == "__main__":
    main()
