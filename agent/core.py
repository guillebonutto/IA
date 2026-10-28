"""
Núcleo del Agente Local Ultra-Optimizado (Zero-Bloat).
Compatible con la API de llama.cpp (llama-server local).
Utiliza llamadas a herramientas ultraligeras basadas en el formato nativo de Qwen.
Cero dependencias externas.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import re
import time
import logging
import math
import unicodedata
from contextvars import ContextVar
from pathlib import Path

logger = logging.getLogger(__name__)
MAX_MEMORY_CONTEXT_CHARS = 1200
MEMORY_CONTEXT_HEADER = "\n\n[CONOCIMIENTO TÉCNICO DESTILADO DE REFERENCIA]:\n"
MAX_VERIFICATION_ERROR_CHARS = 1600
MAX_HISTORY_CONTEXT_BYTES = 8192
DEFAULT_PROGRAMMING_MAX_TOKENS = 1024
MAX_PROGRAMMING_MAX_TOKENS = 3072
DEFAULT_MAX_CODE_REPAIRS = 2
MAX_CODE_REPAIRS = 2
DEFAULT_CHAT_MAX_TOKENS = 512
DEFAULT_CHAT_REQUEST_TIMEOUT_SECONDS = 120
MAX_PROGRAMMING_REQUEST_TIMEOUT_SECONDS = 480
MIN_GENERATION_TOKENS_PER_SECOND_FOR_TIMEOUT = 6.8
PROGRAMMING_TASK_GUIDANCE = (
    "\n\n[REVISIÓN BREVE DE LA TAREA DE PROGRAMACIÓN]\n"
    "- Antes de escribir, identifica los nombres públicos, firmas, retornos, excepciones, "
    "restricciones y formato que exige la solicitud.\n"
    "- Define propiedad y ciclo de vida del estado; copia entradas mutables cuando corresponda. "
    "Para callbacks retenidos, decide entre referencia viva y snapshot, y captura los valores "
    "inmutables por iteración después de calcular las invariantes. Si cada callback representa "
    "el estado del lote completo, finalízalo antes de crear los callbacks.\n"
    "- En recursión conserva los contenedores vacíos que exige el contrato y distingue "
    "contenedores de valores escalares. Para SemVer, separa core, pre-release y +build antes "
    "de dividir identificadores, compara números como enteros e identificadores mixtos según "
    "su regla de precedencia, ignora build al ordenar y normaliza el resultado a -1, 0 o 1.\n"
    "- En concurrencia separa orden de finalización del orden requerido. En pruebas, importa lo "
    "usado y verifica la API pública, sin asumir atributos no especificados; deriva resultados "
    "esperados y límites estrictos (>, >=) del contrato, incluidos todos los efectos secundarios.\n"
    "- En SQL usa consultas parametrizadas para los datos y no interpolación de valores.\n"
    "- Considera entradas vacías, límites, tipos inválidos y concurrencia solo cuando apliquen; "
    "antes de responder revisa imports, flujo y casos límite.\n"
    "- Mantén la solución simple. No muestres deliberación interna ni afirmes pruebas no ejecutadas."
)
KNOWN_VERIFICATION_STATUSES = {
    "PASS",
    "FAIL",
    "TIMEOUT",
    "SYNTAX_ERROR",
    "SECURITY_VIOLATION",
    "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT",
    "ISOLATION_ERROR",
    "ERROR",
}

try:
    from .tools import AgentTools
except Exception:
    try:
        from agent.tools import AgentTools
    except Exception:
        from tools import AgentTools

_user_name = os.getenv("USERNAME", "usuario")
_user_home = str(Path.home())
_downloads_dir = str(Path.home() / "Downloads")
_current_dir = str(Path.cwd())

SYSTEM_PROMPT = f"""Eres AURA CORE, un asistente y agente de programación autónomo que opera localmente en Windows 10.
Tienes herramientas locales conectadas para interactuar directamente con el sistema de archivos, leer código, escribir archivos y ejecutar comandos del sistema.

# Entorno real del sistema:
- Usuario de Windows: {_user_name}
- Directorio personal: {_user_home}
- Directorio de descargas y proyectos: {_downloads_dir}
- Directorio de trabajo: {_current_dir}

# Herramientas disponibles
<tools>
{{"type": "function", "function": {{"name": "list_directory", "description": "Lista el contenido de cualquier carpeta o directorio en el sistema. Úsala SIEMPRE para explorar, acceder o ver qué archivos contiene una carpeta.", "parameters": {{"type": "object", "properties": {{"dir_path": {{"type": "string", "description": "Ruta de la carpeta a listar (ej: '.', nombre de carpeta o ruta completa)"}}, "required": ["dir_path"]}}}}}}
{{"type": "function", "function": {{"name": "read_file", "description": "Lee el código o texto de un archivo.", "parameters": {{"type": "object", "properties": {{"file_path": {{"type": "string", "description": "Ruta del archivo a leer"}}, "start_line": {{"type": "integer"}}, "max_lines": {{"type": "integer"}}}}, "required": ["file_path"]}}}}}}
{{"type": "function", "function": {{"name": "write_file", "description": "Crea o sobrescribe un archivo con nuevo contenido.", "parameters": {{"type": "object", "properties": {{"file_path": {{"type": "string"}}, "content": {{"type": "string"}}}}, "required": ["file_path", "content"]}}}}}}
{{"type": "function", "function": {{"name": "run_command", "description": "Ejecuta un comando en PowerShell. Úsala solo para correr scripts de Python o pruebas de ejecución, NO para listar archivos.", "parameters": {{"type": "object", "properties": {{"command": {{"type": "string"}}}}, "required": ["command"]}}}}}}
{{"type": "function", "function": {{"name": "search_files", "description": "Busca archivos por patrón dentro de un directorio.", "parameters": {{"type": "object", "properties": {{"pattern": {{"type": "string"}}, "root_path": {{"type": "string"}}}}, "required": ["pattern"]}}}}}}
{{"type": "function", "function": {{"name": "get_system_stats", "description": "Consulta el uso actual de CPU, memoria RAM y almacenamiento.", "parameters": {{"type": "object", "properties": {{}}}}}}}}
{{"type": "function", "function": {{"name": "get_datetime", "description": "Devuelve la fecha y hora local actual, incluida la zona horaria.", "parameters": {{"type": "object", "properties": {{}}}}}}}}
</tools>

Para invocar una herramienta, responde con:
<tool_call>
{{"name": "<nombre_herramienta>", "arguments": {{<argumentos>}}}}
</tool_call>

Usa `get_datetime` cuando el usuario pregunte por la fecha u hora local actual.

Reglas obligatorias:
1. Para ver qué archivos o carpetas hay en cualquier directorio o proyecto (por ejemplo si el usuario dice "accede a X", "entra a X", "qué hay en X" o "mira X"), usa SIEMPRE la herramienta `list_directory` indicando la carpeta en `dir_path`. NO intentes usar PowerShell ni Get-ChildItem para explorar archivos.
2. NUNCA inventes nombres de usuarios ni rutas ficticias como C:\\Users\\AURA; utiliza nombres de carpeta directos o las rutas del entorno real indicado arriba.
3. NUNCA digas que no tienes acceso a archivos o que no puedes ejecutar código: tienes herramientas reales conectadas.
4. Tras recibir el resultado de una herramienta, responde de forma directa, técnica, concisa y en español."""

class LocalAgent:
    def __init__(
        self,
        api_base="http://127.0.0.1:8089/v1",
        model_name="local-model",
        workspace=None,
        memory=None,
        programming_max_tokens=DEFAULT_PROGRAMMING_MAX_TOKENS,
        max_code_repairs=DEFAULT_MAX_CODE_REPAIRS,
    ):
        if not isinstance(programming_max_tokens, int) or not (
            512 <= programming_max_tokens <= MAX_PROGRAMMING_MAX_TOKENS
        ):
            raise ValueError(
                f"programming_max_tokens debe estar entre 512 y {MAX_PROGRAMMING_MAX_TOKENS}."
            )
        if (
            not isinstance(max_code_repairs, int)
            or isinstance(max_code_repairs, bool)
            or not 0 <= max_code_repairs <= MAX_CODE_REPAIRS
        ):
            raise ValueError(
                f"max_code_repairs debe estar entre 0 y {MAX_CODE_REPAIRS}."
            )
        self.api_base = api_base.rstrip("/")
        self.model_name = model_name
        self.tools_handler = AgentTools(workspace_root=workspace)
        self.memory = memory
        self.programming_max_tokens = programming_max_tokens
        self.max_code_repairs = max_code_repairs
        self._request_metrics = ContextVar(f"agent_request_metrics_{id(self)}", default=None)
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def get_last_request_metrics(self):
        metrics = self._request_metrics.get()
        if metrics is None:
            return None
        return json.loads(json.dumps(metrics))

    def _record_request_duration(self, metric, elapsed_seconds):
        metrics = self._request_metrics.get()
        if metrics is not None:
            metrics[metric] = metrics.get(metric, 0.0) + elapsed_seconds

    def _record_model_call(self, call):
        metrics = self._request_metrics.get()
        if metrics is not None:
            metrics["model_calls"].append({
                "call_index": len(metrics["model_calls"]) + 1,
                **call,
            })

    @staticmethod
    def _sum_server_timing(model_calls, field):
        values = [
            call.get("server_timings", {}).get(field)
            for call in model_calls
            if isinstance(call.get("server_timings"), dict)
        ]
        values = [value for value in values if isinstance(value, (int, float))]
        return round(sum(values) / 1000, 4) if values else None

    @staticmethod
    def _generation_speed(model_calls):
        generated = 0
        generation_ms = 0
        for call in model_calls:
            timings = call.get("server_timings")
            if not isinstance(timings, dict):
                continue
            tokens = timings.get("predicted_n")
            elapsed_ms = timings.get("predicted_ms")
            if isinstance(tokens, (int, float)) and isinstance(elapsed_ms, (int, float)):
                generated += tokens
                generation_ms += elapsed_ms
        if generation_ms <= 0:
            return None
        return round(generated / (generation_ms / 1000), 2)

    def reset_conversation(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    @staticmethod
    def _message_requests_tool(message):
        return bool(message.get("tool_calls")) or (
            isinstance(message.get("content"), str)
            and "<tool_call>" in message["content"]
        )

    @staticmethod
    def _history_size_bytes(messages):
        serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        return len(serialized.encode("utf-8"))

    def _trim_history(self, max_messages=12, max_bytes=MAX_HISTORY_CONTEXT_BYTES):
        """Aplica al historial conversacional el límite de mensajes y bytes."""
        self.history = self._trim_messages(self.history, max_messages, max_bytes)

    @classmethod
    def _trim_messages(cls, history, max_messages=12, max_bytes=MAX_HISTORY_CONTEXT_BYTES):
        """Limita bytes UTF-8 serializados, no tokens; conserva sistema y turno actual completos."""
        valid_roles = {"system", "user", "assistant", "tool"}
        valid_messages = [
            message for message in history
            if (
                isinstance(message, dict)
                and isinstance(message.get("role"), str)
                and message["role"] in valid_roles
            )
        ]
        system_messages = [message for message in valid_messages if message["role"] == "system"]
        conversation = [message for message in valid_messages if message["role"] != "system"]

        turns = []
        current_turn = []
        for message in conversation:
            role = message["role"]
            if role == "user" and current_turn:
                previous = current_turn[-1]
                if previous["role"] != "assistant" or not cls._message_requests_tool(previous):
                    turns.append(current_turn)
                    current_turn = []
            elif role == "tool" and not current_turn:
                continue
            elif role == "assistant" and not current_turn:
                continue
            current_turn.append(message)
        if current_turn:
            turns.append(current_turn)

        retained_turns = list(turns)
        while len(retained_turns) > 1:
            messages = system_messages + [
                message for turn in retained_turns for message in turn
            ]
            if (
                len(messages) <= max_messages
                and cls._history_size_bytes(messages) <= max_bytes
            ):
                break
            retained_turns.pop(0)

        return system_messages + [
            message for turn in retained_turns for message in turn
        ]

    def is_server_online(self) -> bool:
        """Verifica si el servidor de inferencia llama.cpp está activo."""
        try:
            req = urllib.request.Request(f"{self.api_base}/models", headers={"User-Agent": "LocalAgent/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    @staticmethod
    def is_simple_greeting(user_text: str) -> bool:
        if not isinstance(user_text, str):
            return False
        normalized = unicodedata.normalize("NFKD", user_text.casefold())
        normalized = "".join(
            character
            for character in normalized
            if not unicodedata.combining(character)
        )
        normalized = re.sub(r"[¿?¡!,.;:…]", "", normalized)
        normalized = " ".join(normalized.split())
        return normalized in {
            "hola",
            "hola aura",
            "buenas",
            "buenos dias",
            "buenas tardes",
            "buenas noches",
            "hey",
            "saludos",
            "que tal",
        }

    @staticmethod
    def _acceptance_tests_from_request(user_text: str) -> str | None:
        heading = re.search(
            r"(?im)^\s*(?:#{1,6}\s*)?(?:pruebas?\s+de\s+aceptaci[oó]n|acceptance\s+tests?)\s*:?\s*$",
            user_text,
        )
        if not heading:
            return None

        test_block = re.search(
            r"```(?:python|py)?[ \t]*\r?\n(.*?)```",
            user_text[heading.end():],
            re.IGNORECASE | re.DOTALL,
        )
        if not test_block or not test_block.group(1).strip():
            return None

        request_without_code = re.sub(r"```.*?```", " ", user_text, flags=re.DOTALL)
        programming_request = re.search(
            r"\b(?:c[oó]digo|program(?:a|ar|aci[oó]n|ming)?|python|funci[oó]n|"
            r"clase|script|implement(?:a|ar|aci[oó]n)?|algoritmo|m[eé]todo|"
            r"bug|debug|refactor|software|m[oó]dulo|module|parser|desarroll(?:a|ar|o)|"
            r"code|function|class|method|write|fix)\b",
            request_without_code,
            re.IGNORECASE,
        )
        if not programming_request:
            return None
        return test_block.group(1).strip()

    @staticmethod
    def _is_programming_request(user_text: str) -> bool:
        request_text = re.sub(r"```.*?```", " ", user_text, flags=re.DOTALL)
        return bool(re.search(
            r"\b(?:c[oó]digo|code|python|program(?:a|ar|aci[oó]n|ming)?|"
            r"funci[oó]n|function|clase|class|script|algoritmo|algorithm|"
            r"m[eé]todo|method|implement(?:a|ar|aci[oó]n)?|debug|depura|"
            r"refactor|software)\b",
            request_text,
            re.IGNORECASE,
        ))

    def _verification_response_content(self, llm_result) -> str:
        if not isinstance(llm_result, dict) or llm_result.get("is_tool_call"):
            return ""
        content = llm_result.get("content", "")
        if not isinstance(content, str):
            return ""
        if (
            self._parse_tool_call(content) is not None
            and not re.search(r"```(?:python|py)\b", content, re.IGNORECASE)
        ):
            return ""
        return content

    @staticmethod
    def _verification_messages(messages):
        tool_free_system_prompt = (
            "Eres AURA CORE, un asistente local. Esta solicitud está en un modo de "
            "verificación sin herramientas: no hay herramientas disponibles y no debes "
            "emitir llamadas a herramientas ni respuestas JSON de herramientas. Responde "
            "directamente al usuario con el artefacto solicitado."
        )
        return [
            (
                {"role": "system", "content": tool_free_system_prompt}
                if message.get("role") == "system"
                else dict(message)
            )
            for message in messages
        ]

    @staticmethod
    def _verification_result_summary(result) -> tuple[str, str]:
        if not isinstance(result, dict):
            return "UNKNOWN", "El evaluador devolvió un resultado inválido."

        status = result.get("status")
        status = status[:80] if isinstance(status, str) else "UNKNOWN"
        detail = result.get("error") or result.get("stderr") or result.get("stdout") or ""
        detail = str(detail)
        if re.search(r"(?m)^(?:FAIL|ERROR):", detail):
            diagnostic_lines = [
                line.strip()
                for line in detail.splitlines()
                if re.match(r"^(?:FAIL|ERROR):", line)
                or re.match(r"^[A-Za-z_]\w*(?:Error|Exception):", line)
            ]
            if diagnostic_lines:
                detail = " | ".join(diagnostic_lines)
        detail = " ".join(detail.split())[:MAX_VERIFICATION_ERROR_CHARS]
        return status, detail

    def _record_verification_result(self, execute, code, test_code):
        started = time.perf_counter()
        try:
            return execute(code, test_code)
        finally:
            self._record_request_duration(
                "verification_seconds",
                time.perf_counter() - started,
            )

    @staticmethod
    def _review_criteria_prompt(criteria) -> str:
        if isinstance(criteria, dict):
            required = criteria.get("required_concepts", [])
            prohibited = criteria.get("prohibited_fallacies", [])
            minimum_words = criteria.get("minimum_word_count")
            if not isinstance(required, list) or not all(
                isinstance(group, list) and group
                and all(isinstance(item, str) and item.strip() for item in group)
                for group in required
            ):
                raise ValueError("required_concepts debe ser una lista de grupos de conceptos.")
            if not isinstance(prohibited, list) or not all(
                isinstance(item, str) and item.strip() for item in prohibited
            ):
                raise ValueError("prohibited_fallacies debe ser una lista de textos.")
            if minimum_words is not None and (
                isinstance(minimum_words, bool)
                or not isinstance(minimum_words, int)
                or minimum_words < 0
            ):
                raise ValueError("minimum_word_count debe ser un entero no negativo.")
            if not required and not prohibited and minimum_words is None:
                raise ValueError("review_criteria debe contener criterios verificables.")

            lines = [
                "- Cubre explícitamente cada concepto obligatorio. Incluye el término indicado "
                "en cada punto:"
            ]
            lines.extend(
                f"  - {max(group, key=len).strip()}"
                for group in required
            )
            if prohibited:
                lines.append(
                    "- No afirmes ninguna de estas falacias o afirmaciones prohibidas:"
                )
                lines.extend(f"  - {item.strip()}" for item in prohibited)
            if minimum_words is not None:
                lines.append(f"- La respuesta debe tener al menos {minimum_words} palabras.")
        elif isinstance(criteria, (list, tuple)) and criteria and all(
            isinstance(item, str) and item.strip() for item in criteria
        ):
            lines = ["- Cubre explícitamente cada criterio:"]
            lines.extend(f"  - {item.strip()}" for item in criteria)
        else:
            raise ValueError("review_criteria debe contener criterios verificables.")

        return (
            "\n\n[CRITERIOS EXPLÍCITOS DE REVISIÓN]\n"
            + "\n".join(lines)
            + "\n- No afirmes haber ejecutado pruebas; la revisión mide solo los criterios indicados."
        )

    def _chat_step_with_rubric_review(
        self,
        review_criteria,
        review_evaluator,
        progress_callback=None,
        source_task=None,
    ) -> str:
        if progress_callback:
            progress_callback({"type": "thinking", "iteration": 1})
        model_result = self._call_llm(
            self._verification_messages(self.history),
            retry_count=1,
            allow_tools=False,
        )
        candidate_response = self._verification_response_content(model_result)
        if not candidate_response:
            response_text = (
                "No se pudo verificar la respuesta con la rúbrica: el modelo no devolvió "
                "una respuesta utilizable y no se ejecutó ninguna herramienta."
            )
            self.history.append({"role": "assistant", "content": response_text})
            self._trim_history()
            if progress_callback:
                progress_callback({"type": "response", "content": response_text})
            return response_text

        repair_count = 0
        while True:
            try:
                result = review_evaluator(candidate_response)
            except Exception as exc:
                logger.exception("Falló la evaluación de la rúbrica semántica.")
                response_text = (
                    "No se pudo verificar la respuesta con la rúbrica. "
                    f"Detalle: {' '.join(str(exc).split())[:MAX_VERIFICATION_ERROR_CHARS]}\n\n"
                    f"{candidate_response}"
                )
                break

            if not isinstance(result, dict):
                result = {"status": "UNKNOWN", "passed": None, "error": "resultado inválido"}
            status, detail = self._verification_result_summary(result)
            if result.get("passed") is True and status == "PASS":
                repair_label = (
                    f" tras {repair_count} reparaciones" if repair_count else ""
                )
                response_text = (
                    f"Respuesta aprobada por los criterios explícitos ({status})"
                    f"{repair_label}.\n\n{candidate_response}"
                )
                break

            if result.get("passed") is not False or status != "FAIL":
                response_text = (
                    "No se pudo verificar la respuesta con la rúbrica "
                    f"(estado: {status}). {detail}\n\n{candidate_response}"
                )
                break

            if repair_count >= self.max_code_repairs:
                response_text = (
                    f"Respuesta no aprobada por la rúbrica (estado: {status}, "
                    f"{repair_count} reparaciones). {detail}\n\n{candidate_response}"
                )
                break

            self.history.append({"role": "assistant", "content": candidate_response})
            original_task = source_task if isinstance(source_task, str) else ""
            next_repair = repair_count + 1
            repair_prompt = (
                f"Revisa y corrige la respuesta (reparación {next_repair} de "
                f"{self.max_code_repairs}) para satisfacer todos los criterios originales.\n"
                f"Tarea original:\n{original_task}\n\n"
                f"Criterios completos:\n{review_criteria}\n\n"
                f"Resultado de la rúbrica: estado={status}; "
                f"detalle={detail or 'sin detalle disponible'}\n"
                "Corrige solo las omisiones o falacias identificadas. No invoques herramientas: "
                "están deshabilitadas para esta solicitud. Devuelve únicamente la respuesta final "
                "y no afirmes haber ejecutado pruebas."
            )
            self.history.append({"role": "user", "content": repair_prompt})
            if progress_callback:
                progress_callback({"type": "thinking", "iteration": next_repair + 1})
            repair_result = self._call_llm(
                self._verification_messages(self.history),
                retry_count=1,
                allow_tools=False,
            )
            candidate_response = self._verification_response_content(repair_result)
            if not candidate_response:
                response_text = (
                    "No se pudo verificar la respuesta con la rúbrica: la reparación no "
                    "devolvió contenido utilizable y no se ejecutó ninguna herramienta."
                )
                break
            repair_count = next_repair

        self.history.append({"role": "assistant", "content": response_text})
        self._trim_history()
        if progress_callback:
            progress_callback({"type": "response", "content": response_text})
        return response_text

    def _chat_step_with_code_verification(
        self,
        test_code: str,
        progress_callback=None,
        evaluator=None,
        source_task=None,
    ) -> str:
        try:
            from evals.coding_evaluator import execute_code_test, extract_python_code
        except Exception as exc:
            logger.exception("No se pudo cargar el evaluador de código aislado.")
            response_text = (
                "No se pudo verificar la solución porque el evaluador aislado no está disponible. "
                f"Detalle: {exc}"
            )
            self.history.append({"role": "assistant", "content": response_text})
            self._trim_history()
            return response_text

        execute = evaluator or execute_code_test
        if progress_callback:
            progress_callback({"type": "thinking", "iteration": 1})
        model_result = self._call_llm(
            self._verification_messages(self.history),
            retry_count=1,
            allow_tools=False,
        )
        candidate_response = self._verification_response_content(model_result)
        if not candidate_response:
            response_text = (
                "No se pudo verificar la solución: el modelo no devolvió una respuesta de código "
                "utilizable y no se ejecutó ninguna herramienta."
            )
            self.history.append({"role": "assistant", "content": response_text})
            self._trim_history()
            if progress_callback:
                progress_callback({"type": "response", "content": response_text})
            return response_text

        response_text = ""
        repair_count = 0
        while True:
            try:
                candidate_code, extraction_error = extract_python_code(candidate_response)
            except Exception:
                logger.exception("Falló la extracción de código para verificación aislada.")
                candidate_code, extraction_error = "", "Error interno al extraer el código."
            if extraction_error:
                result = {
                    "status": "SYNTAX_ERROR",
                    "passed": False,
                    "error": f"No se pudo extraer código ejecutable: {extraction_error}",
                }
                evaluation_error = ""
            else:
                try:
                    result = self._record_verification_result(execute, candidate_code, test_code)
                except Exception as exc:
                    logger.exception("Falló la invocación del evaluador aislado.")
                    result = None
                    evaluation_error = " ".join(str(exc).split())[:MAX_VERIFICATION_ERROR_CHARS]
                else:
                    evaluation_error = ""

            status, detail = self._verification_result_summary(result)
            if evaluation_error:
                detail = evaluation_error

            if (
                isinstance(result, dict)
                and result.get("status") == "PASS"
                and result.get("passed") is True
            ):
                if repair_count:
                    repair_label = (
                        "una reparación" if repair_count == 1
                        else f"{repair_count} reparaciones"
                    )
                    response_text = (
                        f"Código aprobado por las pruebas de aceptación tras {repair_label} "
                        f"({status}).\n\n{candidate_response}"
                    )
                else:
                    response_text = (
                        f"Código aprobado por las pruebas de aceptación ({status}).\n\n"
                        f"{candidate_response}"
                    )
                break

            if status not in KNOWN_VERIFICATION_STATUSES or status in {
                "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT",
                "ISOLATION_ERROR",
                "ERROR",
            } or evaluation_error:
                response_text = (
                    "No se pudo verificar el código porque el evaluador aislado no pudo confirmar "
                    f"una ejecución segura (estado: {status}). {detail}\n\n{candidate_response}"
                )
                break

            can_repair = (
                isinstance(result, dict)
                and result.get("passed") is False
                and status in {"FAIL", "TIMEOUT", "SYNTAX_ERROR", "SECURITY_VIOLATION"}
                and repair_count < self.max_code_repairs
            )
            if not can_repair:
                repair_note = (
                    f" tras {repair_count} reparaciones" if repair_count
                    else ""
                )
                if extraction_error:
                    response_text = (
                        "Código no verificado: no se pudo extraer una solución ejecutable"
                        f"{repair_note}. Detalle: {detail}\n\n{candidate_response}"
                    )
                else:
                    response_text = (
                        f"Código no verificado (estado: {status}{repair_note}). "
                        f"{detail}\n\n{candidate_response}"
                    )
                break

            self.history.append({"role": "assistant", "content": candidate_response})
            original_task = source_task
            if not isinstance(original_task, str):
                original_task = next(
                    (
                        message.get("content", "")
                        for message in reversed(self.history)
                        if message.get("role") == "user"
                    ),
                    "",
                )
            next_repair = repair_count + 1
            repair_prompt = (
                f"Repara el error observado en esta tarea (reparación {next_repair} de "
                f"{self.max_code_repairs}). Conserva el contrato original y no añadas requisitos.\n"
                f"Tarea y requisitos originales:\n{original_task}\n\n"
                f"Resultado de las pruebas: estado={status}; "
                f"detalle={detail or 'sin detalle disponible'}\n"
                "Corrige específicamente el fallo reportado, revisa la solución contra la interfaz "
                "y los casos límite solicitados, y devuelve el resultado completo en el formato pedido. "
                "Si generas pruebas, contrasta cada atributo con la API especificada y, ante una "
                "excepción no lanzada, verifica que el caso realmente cruce el límite estricto o "
                "inclusivo definido; no cambies el contrato para forzar el resultado esperado. "
                "No invoques herramientas: están deshabilitadas para esta solicitud. "
                "Devuelve la solución completa sin llamadas a herramientas y no afirmes que pasó "
                "una prueba sin resultado del evaluador."
            )
            self.history.append({"role": "user", "content": repair_prompt})
            if progress_callback:
                progress_callback({"type": "thinking", "iteration": next_repair + 1})
            repair_result = self._call_llm(
                self._verification_messages(self.history),
                retry_count=1,
                allow_tools=False,
            )
            candidate_response = self._verification_response_content(repair_result)
            if not candidate_response:
                response_text = (
                    "Código no verificado: la reparación no devolvió una solución utilizable. "
                    f"Resultado anterior: {status}. {detail}"
                )
                break
            repair_count = next_repair

        self.history.append({"role": "assistant", "content": response_text})
        self._trim_history()
        if progress_callback:
            progress_callback({"type": "response", "content": response_text})
        return response_text

    def _call_llm(self, messages, retry_count=0, allow_tools=True):
        result = self._call_llm_request(messages, retry_count, allow_tools)
        attempts = result.pop("_model_call_metrics", None)
        if attempts is None:
            usage = result.get("usage") or {}
            attempts = [{
                "round_trip_seconds": 0.0,
                "request_serialization_seconds": result.get(
                    "request_serialization_seconds", 0.0
                ),
                "max_tokens": result.get("max_tokens"),
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "finish_reason": result.get("finish_reason"),
                "error": result.get("content") if result.get("content", "").startswith("[Error") else None,
            }]
        for attempt in attempts:
            self._record_model_call(attempt)
        return result

    def _call_llm_request(self, messages, retry_count=0, allow_tools=True):
        messages = self._trim_messages(messages)
        latest_user_text = next(
            (message.get("content", "") for message in reversed(messages) if message.get("role") == "user"),
            "",
        )
        max_tokens = (
            self.programming_max_tokens
            if isinstance(latest_user_text, str) and self._is_programming_request(latest_user_text)
            else DEFAULT_CHAT_MAX_TOKENS
        )
        timeout_seconds = DEFAULT_CHAT_REQUEST_TIMEOUT_SECONDS
        if max_tokens > DEFAULT_CHAT_MAX_TOKENS:
            estimated_seconds = 180 + math.ceil(
                (max_tokens - DEFAULT_PROGRAMMING_MAX_TOKENS)
                / MIN_GENERATION_TOKENS_PER_SECOND_FOR_TIMEOUT
            )
            timeout_seconds = min(
                MAX_PROGRAMMING_REQUEST_TIMEOUT_SECONDS,
                max(DEFAULT_CHAT_REQUEST_TIMEOUT_SECONDS, estimated_seconds),
            )
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "max_tokens": max_tokens,
            "stream": False
        }
        if allow_tools:
            tools_declarations = self.tools_handler.get_tools_declarations()
            payload["tools"] = tools_declarations
            payload["tool_choice"] = "auto"

        serialization_started = time.perf_counter()
        data = json.dumps(payload).encode("utf-8")
        serialization_seconds = time.perf_counter() - serialization_started
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LocalAgent/1.0"
            }
        )
        request_started = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=timeout_seconds) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result["choices"][0]
                msg = choice.get("message", {})
                usage = result.get("usage") or {}
                call_metrics = {
                    "round_trip_seconds": round(time.perf_counter() - request_started, 4),
                    "request_serialization_seconds": round(serialization_seconds, 6),
                    "max_tokens": max_tokens,
                    "timeout_seconds": timeout_seconds,
                    "prompt_tokens": usage.get("prompt_tokens"),
                    "completion_tokens": usage.get("completion_tokens"),
                    "finish_reason": choice.get("finish_reason"),
                    "server_timings": result.get("timings"),
                    "error": None,
                }
                
                tool_calls = msg.get("tool_calls")
                if tool_calls and len(tool_calls) > 0:
                    fn = tool_calls[0].get("function", {})
                    fn_name = fn.get("name")
                    fn_args = fn.get("arguments", {})
                    if isinstance(fn_args, str):
                        try:
                            fn_args = json.loads(fn_args)
                        except Exception:
                            fn_args = {}
                    return {
                        "is_tool_call": True,
                        "tool": fn_name,
                        "args": fn_args,
                        "raw_content": f"<tool_call>\n{json.dumps({'name': fn_name, 'arguments': fn_args})}\n</tool_call>",
                        "usage": result.get("usage") or {},
                        "finish_reason": choice.get("finish_reason"),
                        "server_timings": result.get("timings"),
                        "max_tokens": max_tokens,
                        "timeout_seconds": timeout_seconds,
                        "request_serialization_seconds": round(serialization_seconds, 6),
                        "_model_call_metrics": [call_metrics],
                    }

                content = msg.get("content", "")
                return {
                    "is_tool_call": False,
                    "content": content,
                    "usage": result.get("usage") or {},
                    "finish_reason": choice.get("finish_reason"),
                    "server_timings": result.get("timings"),
                    "max_tokens": max_tokens,
                    "timeout_seconds": timeout_seconds,
                    "request_serialization_seconds": round(serialization_seconds, 6),
                    "_model_call_metrics": [call_metrics],
                }
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            failed_attempt = {
                "round_trip_seconds": round(time.perf_counter() - request_started, 4),
                "request_serialization_seconds": round(serialization_seconds, 6),
                "max_tokens": max_tokens,
                "timeout_seconds": timeout_seconds,
                "prompt_tokens": None,
                "completion_tokens": None,
                "finish_reason": None,
                "error": f"HTTP {e.code}: {e.reason}",
            }
            
            # Auto-recuperación si la petición excedió la ventana de contexto
            if retry_count == 0 and ("exceed" in err_body.lower() or "context" in err_body.lower() or e.code == 400):
                if len(messages) > 2:
                    emergency_msgs = [messages[0]] + messages[-2:]
                    result = self._call_llm_request(
                        emergency_msgs,
                        retry_count=1,
                        allow_tools=allow_tools,
                    )
                    attempts = result.pop("_model_call_metrics", [])
                    result["_model_call_metrics"] = [failed_attempt] + attempts
                    return result

            return {
                "is_tool_call": False,
                "content": f"[Error de conexión con el motor local: HTTP Error {e.code}: {e.reason}. Verifica que llama-server esté activo en el puerto 8089.]",
                "_model_call_metrics": [failed_attempt],
            }
        except urllib.error.URLError as e:
            return {
                "is_tool_call": False,
                "content": f"[Error de conexión con el motor local: {str(e)}. Verifica que llama-server esté activo en el puerto 8089.]",
                "_model_call_metrics": [{
                    "round_trip_seconds": round(time.perf_counter() - request_started, 4),
                    "request_serialization_seconds": round(serialization_seconds, 6),
                    "max_tokens": max_tokens,
                    "timeout_seconds": timeout_seconds,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "finish_reason": None,
                    "error": str(e),
                }],
            }
        except Exception as e:
            return {
                "is_tool_call": False,
                "content": f"[Error al consultar el modelo: {str(e)}]",
                "_model_call_metrics": [{
                    "round_trip_seconds": round(time.perf_counter() - request_started, 4),
                    "request_serialization_seconds": round(serialization_seconds, 6),
                    "max_tokens": max_tokens,
                    "timeout_seconds": timeout_seconds,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "finish_reason": None,
                    "error": str(e),
                }],
            }

    def _parse_tool_call(self, text: str):
        """Extrae llamadas a herramientas explícitas en diversos formatos que emite Qwen."""
        if not text:
            return None

        cleaned = text.strip()
        while cleaned.startswith("{{") and cleaned.endswith("}}"):
            cleaned = cleaned[1:-1].strip()

        # 1. Etiqueta explícita <tool_call>...</tool_call> (formato Qwen)
        match_tag = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        if match_tag:
            try:
                candidate = match_tag.group(1).strip()
                while candidate.startswith("{{") and candidate.endswith("}}"):
                    candidate = candidate[1:-1].strip()
                data = json.loads(candidate)
                name = data.get("name") or data.get("tool")
                args = data.get("arguments") or data.get("args") or {}
                if name:
                    return {"tool": name, "args": args}
            except Exception:
                pass

        # 2. Bloque markdown ```json ... ```, ```xml ... ``` o ```tool_call ... ```
        match_md = re.search(r"```(?:tool_call|json|xml)?\s*(.*?)\s*```", text, re.DOTALL)
        if match_md:
            try:
                candidate = match_md.group(1).strip()
                while candidate.startswith("{{") and candidate.endswith("}}"):
                    candidate = candidate[1:-1].strip()
                data = json.loads(candidate)
                name = data.get("name") or data.get("tool")
                args = data.get("arguments") or data.get("args") or {}
                if name:
                    return {"tool": name, "args": args}
            except Exception:
                pass

        # 3. JSON directo conteniendo "name" o "tool"
        match_raw = re.search(r"\{[\s\{]*\"(?:name|tool)\"\s*:\s*\"([^\"]+)\"\s*,\s*\"(?:arguments|args)\"\s*:\s*(\{.*?\})[\s\}]*\}", text, re.DOTALL)
        if match_raw:
            try:
                name = match_raw.group(1)
                args = json.loads(match_raw.group(2).strip())
                return {"tool": name, "args": args}
            except Exception:
                pass

        # 4. JSON completo directo
        try:
            data = json.loads(cleaned)
            name = data.get("name") or data.get("tool")
            args = data.get("arguments") or data.get("args") or {}
            if name and isinstance(name, str):
                return {"tool": name, "args": args}
        except Exception:
            pass

        return None

    def chat_step(
        self,
        user_text: str,
        progress_callback=None,
        acceptance_evaluator=None,
        review_criteria=None,
        review_evaluator=None,
    ) -> str:
        metrics = {
            "model_calls": [],
            "verification_seconds": 0.0,
            "tool_seconds": 0.0,
            "agent_total_seconds": 0.0,
            "time_to_first_token_seconds": None,
            "time_to_first_token_unavailable_reason": (
                "El cliente usa respuestas no streaming; solo se mide el round trip completo."
            ),
        }
        self._request_metrics.set(metrics)
        started = time.perf_counter()
        try:
            return self._chat_step(
                user_text,
                progress_callback,
                acceptance_evaluator=acceptance_evaluator,
                review_criteria=review_criteria,
                review_evaluator=review_evaluator,
            )
        finally:
            metrics["agent_total_seconds"] = round(time.perf_counter() - started, 4)
            metrics["model_call_count"] = len(metrics["model_calls"])
            prompt_tokens = [
                call["prompt_tokens"] for call in metrics["model_calls"]
                if isinstance(call.get("prompt_tokens"), int)
            ]
            completion_tokens = [
                call["completion_tokens"] for call in metrics["model_calls"]
                if isinstance(call.get("completion_tokens"), int)
            ]
            metrics["prompt_tokens"] = sum(prompt_tokens) if prompt_tokens else None
            metrics["completion_tokens"] = sum(completion_tokens) if completion_tokens else None
            metrics["prompt_eval_seconds"] = self._sum_server_timing(
                metrics["model_calls"], "prompt_ms"
            )
            metrics["generation_seconds"] = self._sum_server_timing(
                metrics["model_calls"], "predicted_ms"
            )
            metrics["generation_tokens_per_second"] = self._generation_speed(
                metrics["model_calls"]
            )

    def _chat_step(
        self,
        user_text: str,
        progress_callback=None,
        acceptance_evaluator=None,
        review_criteria=None,
        review_evaluator=None,
    ) -> str:
        """
        Ejecuta un turno completo de conversación resolviendo automáticamente
        las herramientas en un bucle agéntico con gestión de contexto y RAG local.
        """
        acceptance_tests = self._acceptance_tests_from_request(user_text)
        if acceptance_evaluator is not None and not callable(acceptance_evaluator):
            raise ValueError("acceptance_evaluator debe ser invocable.")
        if review_criteria is not None:
            if not callable(review_evaluator):
                raise ValueError("review_criteria requiere un review_evaluator invocable.")
            review_prompt = self._review_criteria_prompt(review_criteria)
        else:
            if review_evaluator is not None:
                raise ValueError("review_evaluator requiere review_criteria.")
            review_prompt = ""
        if acceptance_evaluator is not None and review_criteria is not None:
            raise ValueError("No se pueden combinar la evaluación de código y la rúbrica semántica.")

        if self.is_simple_greeting(user_text):
            response_text = "¡Hola! ¿En qué puedo ayudarte?"
            self.history.append({"role": "user", "content": user_text})
            self.history.append({"role": "assistant", "content": response_text})
            self._trim_history()
            if progress_callback:
                progress_callback({"type": "response", "content": response_text})
            return response_text

        user_content = user_text
        if getattr(self, "memory", None):
            try:
                clean_q = user_text.lower().strip()
                # No inyectar snippets de memoria cuando el usuario da una instrucción de acción directa
                is_action = any(clean_q.startswith(w) for w in ["accede", "entra", "abre", "lee", "escribe", "revisa", "corre", "ejecuta", "puedes acceder", "puedes entrar", "puedes leer", "lista", "dir", "ls"])
                if not is_action:
                    matches = self.memory.search_knowledge(user_text, limit=2)
                    memory_context = ""
                    seen_snippets = set()
                    for match in matches:
                        snippet = (match.get("snippet") or "").strip()
                        if not snippet or "¡Hola! Puedo" in snippet:
                            continue
                        normalized_snippet = " ".join(snippet.casefold().split())
                        if normalized_snippet in seen_snippets:
                            continue
                        seen_snippets.add(normalized_snippet)

                        title = (match.get("title") or "").strip()
                        context_bit = f"• {title}: {snippet}" if title else f"• {snippet}"
                        separator = "\n" if memory_context else ""
                        available_chars = (
                            MAX_MEMORY_CONTEXT_CHARS
                            - len(MEMORY_CONTEXT_HEADER)
                            - len(memory_context)
                            - len(separator)
                        )
                        if available_chars <= 0:
                            break
                        if len(context_bit) > available_chars:
                            context_bit = context_bit[:available_chars - 1].rstrip() + "…"
                        memory_context += separator + context_bit
                        if available_chars <= len(context_bit):
                            break
                    if memory_context:
                        user_content = f"{user_text}{MEMORY_CONTEXT_HEADER}{memory_context}"
            except Exception:
                logger.exception("No se pudo recuperar contexto de memoria para la consulta local.")

        if self._is_programming_request(user_text):
            user_content += PROGRAMMING_TASK_GUIDANCE
        if acceptance_tests is not None or acceptance_evaluator is not None:
            user_content += (
                "\n\n[MODO DE ENTREGA VERIFICABLE]\n"
                "Devuelve la solución completa solicitada y no invoques herramientas: "
                "están deshabilitadas para esta respuesta."
            )
        if review_prompt:
            user_content += review_prompt + (
                "\n- No invoques herramientas: están deshabilitadas para esta revisión."
            )

        self.history.append({"role": "user", "content": user_content})
        self._trim_history()

        if acceptance_evaluator is not None:
            return self._chat_step_with_code_verification(
                "",
                progress_callback,
                evaluator=acceptance_evaluator,
                source_task=user_text,
            )
        if acceptance_tests is not None:
            return self._chat_step_with_code_verification(
                acceptance_tests,
                progress_callback,
                source_task=user_text,
            )
        if review_prompt:
            return self._chat_step_with_rubric_review(
                review_prompt,
                review_evaluator,
                progress_callback=progress_callback,
                source_task=user_text,
            )

        max_iterations = 4
        current_iter = 0
        executed_calls = set()

        while current_iter < max_iterations:
            current_iter += 1
            if progress_callback:
                progress_callback({"type": "thinking", "iteration": current_iter})

            llm_res = self._call_llm(self.history)
            
            tool_name = None
            args = {}
            response_text = ""

            if llm_res.get("is_tool_call"):
                tool_name = llm_res.get("tool")
                args = llm_res.get("args", {})
                response_text = llm_res.get("raw_content", "")
            else:
                response_text = llm_res.get("content", "")
                parsed = self._parse_tool_call(response_text)
                if parsed:
                    tool_name = parsed.get("tool")
                    args = parsed.get("args", {})

            if not tool_name:
                # El modelo respondió directamente con texto
                if (
                    llm_res.get("finish_reason") == "length"
                    and self._is_programming_request(user_text)
                ):
                    response_text += (
                        "\n\n[AVISO: se alcanzó el límite de salida; el código o la respuesta "
                        "pueden estar incompletos y no deben considerarse verificados.]"
                    )
                if not response_text.startswith("[Error"):
                    self.history.append({"role": "assistant", "content": response_text})
                    self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": response_text})
                return response_text

            # Prevención de bucles repetitivos de herramientas
            call_key = f"{tool_name}:{json.dumps(args, sort_keys=True)}"
            if call_key in executed_calls:
                # El modelo está repitiendo la misma llamada; forzar respuesta en texto
                loop_notice = f"[Aviso del sistema]: Ya ejecutaste '{tool_name}' con estos argumentos. Ahora responde directamente al usuario en español explicando de forma clara y estructurada lo que encontraste."
                self.history.append({"role": "user", "content": loop_notice})
                final_res = self._call_llm(self.history, allow_tools=False)
                final_text = (final_res.get("content") or "").strip()
                if not final_text or final_text.startswith("<tool_call>") or '"name":' in final_text:
                    final_text = self._format_tool_summary(tool_name, tool_output or {})
                self.history.append({"role": "assistant", "content": final_text})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": final_text})
                return final_text

            executed_calls.add(call_key)

            # Ejecutar la herramienta detectada
            if progress_callback:
                progress_callback({
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": args
                })

            tool_started = time.perf_counter()
            tool_output = None
            if tool_name == "run_command":
                cmd = args.get("command") or args.get("cmd") or ""
                tool_output = self.tools_handler.run_command(cmd)
            elif tool_name == "read_file":
                fp = args.get("file_path") or args.get("path") or args.get("file") or ""
                start_line = int(args.get("start_line", 1))
                max_lines = int(args.get("max_lines", 50))
                tool_output = self.tools_handler.read_file(fp, start_line, max_lines)
            elif tool_name == "write_file":
                fp = args.get("file_path") or args.get("path") or args.get("file") or ""
                content = args.get("content") or args.get("text") or ""
                tool_output = self.tools_handler.write_file(fp, content)
            elif tool_name == "list_directory":
                dp = args.get("dir_path") or args.get("path") or args.get("folder") or args.get("directory") or "."
                tool_output = self.tools_handler.list_directory(dp)
            elif tool_name == "search_files":
                pat = args.get("pattern") or args.get("query") or "*"
                root_path = args.get("root_path") or args.get("dir_path") or args.get("path") or "."
                tool_output = self.tools_handler.search_files(pat, root_path)
            elif tool_name == "get_system_stats":
                tool_output = self.tools_handler.get_system_stats()
            elif tool_name == "get_datetime":
                tool_output = self.tools_handler.get_datetime()
            else:
                tool_output = {"error": f"Herramienta '{tool_name}' no reconocida."}
            self._record_request_duration(
                "tool_seconds",
                time.perf_counter() - tool_started,
            )

            if progress_callback:
                progress_callback({
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": tool_output
                })

            # Añadir la llamada del asistente y el feedback al historial
            self.history.append({"role": "assistant", "content": response_text})
            
            # Formatear la salida de forma concisa para no saturar al modelo
            out_str = json.dumps(tool_output, ensure_ascii=False)
            if len(out_str) > 1200:
                out_str = out_str[:1200] + "... [truncado]"

            feedback = f"[Resultado de {tool_name}]:\n{out_str}\n\nCon esta información, respóndele ahora directamente al usuario en español describiendo con claridad lo que encontraste."
            self.history.append({"role": "user", "content": feedback})
            self._trim_history()

            # Forzar generación directa de respuesta textual con allow_tools=False
            post_res = self._call_llm(self.history, allow_tools=False)
            post_content = (post_res.get("content") or "").strip()

            disclaimers = [
                "no puedo ejecutar comandos",
                "no tengo la capacidad",
                "en este contexto",
                "como modelo de lenguaje",
                "lo siento, pero no",
                "no tengo acceso"
            ]
            is_disclaimer = any(d in post_content.lower() for d in disclaimers)

            if post_content and not post_content.startswith("<tool_call>") and '"name":' not in post_content and not is_disclaimer:
                self.history.append({"role": "assistant", "content": post_content})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": post_content})
                return post_content
            elif is_disclaimer:
                # El modelo intentó una evasiva de seguridad a pesar de haber ejecutado la herramienta
                fallback_msg = self._format_tool_summary(tool_name, tool_output or {})
                self.history.append({"role": "assistant", "content": fallback_msg})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": fallback_msg})
                return fallback_msg

        # Si agotó las iteraciones o no respondió texto limpio, generar resumen estructurado
        final_prompt = [m for m in self.history] + [{"role": "user", "content": "Con los resultados obtenidos anteriormente, responde directamente al usuario en español."}]
        synth_res = self._call_llm(final_prompt, allow_tools=False)
        final_msg = (synth_res.get("content") or "").strip()
        is_disclaimer_final = any(d in final_msg.lower() for d in disclaimers)
        if not final_msg or final_msg.startswith("<tool_call>") or '"name":' in final_msg or is_disclaimer_final:
            final_msg = self._format_tool_summary(tool_name, tool_output or {})
        self.history.append({"role": "assistant", "content": final_msg})
        return final_msg

    def _format_tool_summary(self, tool_name: str, output: dict) -> str:
        """Formatea la salida de una herramienta de manera neutral y directa."""
        if not output:
            return "No se obtuvo información de la herramienta."
        if "error" in output:
            return f"Aviso al ejecutar {tool_name}: {output['error']}"
        if tool_name == "list_directory":
            files = output.get("files", [])
            path = output.get("path", "")
            count = output.get("total_items", output.get("count", len(files)))
            sample = files[:25]
            listing = ", ".join(sample)
            suffix = f"\n... ({count - len(sample)} elementos más)" if count > len(sample) else ""
            return f"Contenido de `{path}` ({count} elementos):\n{listing}{suffix}"
        elif tool_name == "read_file":
            content = output.get("content", "")
            path = output.get("file_path", "")
            lines = output.get("lines_read", 0)
            return f"Lectura de `{path}` ({lines} líneas):\n```\n{content[:2500]}\n```"
        elif tool_name == "run_command":
            stdout = output.get("stdout", "")
            stderr = output.get("stderr", "")
            code = output.get("exit_code", 0)
            out = stdout if stdout else stderr
            return f"Comando (exit code {code}):\n{out}"
        elif tool_name == "get_system_stats":
            return json.dumps(output, ensure_ascii=False, indent=2)
        return json.dumps(output, ensure_ascii=False)
