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
from pathlib import Path

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
</tools>

Para invocar una herramienta, responde con:
<tool_call>
{{"name": "<nombre_herramienta>", "arguments": {{<argumentos>}}}}
</tool_call>

Reglas obligatorias:
1. Para ver qué archivos o carpetas hay en cualquier directorio o proyecto (por ejemplo si el usuario dice "accede a X", "entra a X", "qué hay en X" o "mira X"), usa SIEMPRE la herramienta `list_directory` indicando la carpeta en `dir_path`. NO intentes usar PowerShell ni Get-ChildItem para explorar archivos.
2. NUNCA inventes nombres de usuarios ni rutas ficticias como C:\\Users\\AURA; utiliza nombres de carpeta directos o las rutas del entorno real indicado arriba.
3. NUNCA digas que no tienes acceso a archivos o que no puedes ejecutar código: tienes herramientas reales conectadas.
4. Tras recibir el resultado de una herramienta, responde de forma directa, técnica, concisa y en español."""

class LocalAgent:
    def __init__(self, api_base="http://127.0.0.1:8089/v1", model_name="local-model", workspace=None, memory=None):
        self.api_base = api_base.rstrip("/")
        self.model_name = model_name
        self.tools_handler = AgentTools(workspace_root=workspace)
        self.memory = memory
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    def reset_conversation(self):
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]

    def _trim_history(self, max_messages=12):
        """Mantiene el SYSTEM_PROMPT intacto y recorta mensajes antiguos para evitar desbordar el contexto."""
        if len(self.history) > max_messages:
            system_msg = self.history[0]
            recent_msgs = self.history[-(max_messages - 1):]
            self.history = [system_msg] + recent_msgs

    def is_server_online(self) -> bool:
        """Verifica si el servidor de inferencia llama.cpp está activo."""
        try:
            req = urllib.request.Request(f"{self.api_base}/models", headers={"User-Agent": "LocalAgent/1.0"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    def _call_llm(self, messages, retry_count=0, allow_tools=True):
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "max_tokens": 512,
            "stream": False
        }
        if allow_tools:
            tools_declarations = self.tools_handler.get_tools_declarations()
            payload["tools"] = tools_declarations
            payload["tool_choice"] = "auto"

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "LocalAgent/1.0"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result["choices"][0]
                msg = choice.get("message", {})
                
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
                        "raw_content": f"<tool_call>\n{json.dumps({'name': fn_name, 'arguments': fn_args})}\n</tool_call>"
                    }

                content = msg.get("content", "")
                return {
                    "is_tool_call": False,
                    "content": content
                }
        except urllib.error.HTTPError as e:
            err_body = ""
            try:
                err_body = e.read().decode("utf-8")
            except Exception:
                pass
            
            # Auto-recuperación si la petición excedió la ventana de contexto
            if retry_count == 0 and ("exceed" in err_body.lower() or "context" in err_body.lower() or e.code == 400):
                if len(messages) > 2:
                    emergency_msgs = [messages[0]] + messages[-2:]
                    return self._call_llm(emergency_msgs, retry_count=1)

            return {
                "is_tool_call": False,
                "content": f"[Error de conexión con el motor local: HTTP Error {e.code}: {e.reason}. Verifica que llama-server esté activo en el puerto 8089.]"
            }
        except urllib.error.URLError as e:
            return {
                "is_tool_call": False,
                "content": f"[Error de conexión con el motor local: {str(e)}. Verifica que llama-server esté activo en el puerto 8089.]"
            }
        except Exception as e:
            return {
                "is_tool_call": False,
                "content": f"[Error al consultar el modelo: {str(e)}]"
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

    def chat_step(self, user_text: str, progress_callback=None) -> str:
        """
        Ejecuta un turno completo de conversación resolviendo automáticamente
        las herramientas en un bucle agéntico con gestión de contexto y RAG local.
        """
        user_content = user_text
        if getattr(self, "memory", None):
            try:
                clean_q = user_text.lower().strip()
                # No inyectar snippets de memoria cuando el usuario da una instrucción de acción directa
                is_action = any(clean_q.startswith(w) for w in ["accede", "entra", "abre", "lee", "escribe", "revisa", "corre", "ejecuta", "puedes acceder", "puedes entrar", "puedes leer", "lista", "dir", "ls"])
                if not is_action:
                    matches = self.memory.search(user_text, limit=2)
                    if matches:
                        context_bits = [f"• {m['title']}: {m['snippet']}" for m in matches if m.get('snippet') and "¡Hola! Puedo" not in m.get('snippet', '')]
                        if context_bits:
                            user_content = f"{user_text}\n\n[CONOCIMIENTO TÉCNICO DESTILADO DE REFERENCIA]:\n" + "\n".join(context_bits)
            except Exception:
                pass

        self.history.append({"role": "user", "content": user_content})
        self._trim_history()

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
            else:
                tool_output = {"error": f"Herramienta '{tool_name}' no reconocida."}

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
