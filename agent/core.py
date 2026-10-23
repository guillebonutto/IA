"""
Núcleo del Agente Local Autónomo con Llama 3.1 8B.
Cero dependencias externas.
Llamadas a herramientas nativas mediante el protocolo estándar OpenAI / ChatML de llama.cpp.
Cero condicionales de palabras clave, cero parsers de intención con regex.
"""

import os
import sys
import json
import urllib.request
import urllib.error
import time
import re

try:
    from .tools import AgentTools
except Exception:
    try:
        from agent.tools import AgentTools
    except Exception:
        from tools import AgentTools

SYSTEM_PROMPT = """You are AURA, an autonomous AI coding assistant running locally on the user's PC.
You have access to native tools to explore files, read source code, and run commands.
- Use `list_directory` when the user asks to see, explore, or access a folder or files, or asks what is inside a directory.
- Use `read_file` when the user asks to view or inspect code in a file.
- Use `search_files` to find files matching a name or pattern.
- Use `run_command` to execute shell commands when needed.
- Use `get_watchdog_report` when the user asks about the status of the trading bot, if processes are running, system health, or if there are errors in logs.

CRITICAL RULES FOR RESPONSES:
1. When answering after `list_directory`: You MUST explicitly list the directories and files found. NEVER say 'es un JSON' or describe the JSON structure. Give the user the actual names of folders and files.
2. When answering after `read_file`: If the user asked to see or get the code, show the relevant code directly. If the user asked for improvements, explanations, bug analysis, or code review, provide concrete suggestions, analysis, and best practices in Spanish.
3. If a file was already shown or read in the conversation, do NOT call `read_file` again to answer questions about it. Answer directly using the code in history.
4. When answering after `get_watchdog_report`: Explicitly state which processes are active, system CPU/RAM, and mention any errors or recent alerts found.
5. If the user asks what is inside a folder, asks to see contents, or complains that folders/contents were not shown, call `list_directory` immediately.
6. When the user asks conversational questions, greets you, or asks what you can do, answer directly in Spanish without calling tools.
7. Be concise, direct, and helpful. Always respond in clear Spanish."""

def _auto_close_markdown(text: str) -> str:
    """Asegura que los bloques de código markdown no queden abiertos si se interrumpe la generación."""
    if not text:
        return text
    fences = text.count("```")
    if fences % 2 != 0:
        text = text.rstrip() + "\n```\n"
    return text

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

    def _trim_history(self, max_messages=14):
        """Mantiene el SYSTEM_PROMPT y recorta mensajes antiguos para no exceder la ventana de contexto."""
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

    def _extract_tool_call(self, text: str):
        """Detecta y extrae llamadas a herramientas estructuradas en JSON emitidas por el modelo en el texto."""
        if not text:
            return None
        raw = text.strip()

        # Eliminar etiquetas tipo XML <tool_call> ... </tool_call>
        raw = re.sub(r"</?tool_call>", "", raw, flags=re.IGNORECASE).strip()

        # Eliminar bloques de código markdown si los hay (```json ... ``` o ``` ...)
        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) >= 2:
                if lines[-1].strip() == "```":
                    lines = lines[1:-1]
                else:
                    lines = lines[1:]
                raw = "\n".join(lines).strip()

        # Buscar bloques JSON usando json.JSONDecoder().raw_decode
        parsed_obj = None
        decoder = json.JSONDecoder()
        
        idx = 0
        while idx < len(raw):
            start = raw.find("{", idx)
            if start == -1:
                break
            try:
                obj, end_offset = decoder.raw_decode(raw[start:])
                if isinstance(obj, dict):
                    # Verificar si es una llamada a herramienta válida
                    candidate_name = obj.get("name") or obj.get("tool") or obj.get("action") or obj.get("type")
                    if not candidate_name and "function" in obj and isinstance(obj["function"], dict):
                        candidate_name = obj["function"].get("name")
                    if not candidate_name:
                        if "command" in obj or "cmd" in obj:
                            candidate_name = "run_command"
                        elif "dir_path" in obj or "folder" in obj:
                            candidate_name = "list_directory"
                        elif "file_path" in obj:
                            candidate_name = "read_file"
                    if candidate_name and str(candidate_name).lower() in ("list_directory", "list_dir", "ls", "dir", "read_file", "read", "write_file", "write", "run_command", "search_files", "get_system_stats", "get_watchdog_report"):
                        parsed_obj = obj
                        break
                idx = start + 1
            except Exception:
                idx = start + 1

        if not parsed_obj:
            return None

        # Formatos soportados:
        # 1. {"name": "...", "arguments": {...}} o {"type": "list_directory", "dir_path": "..."} o {"command": "..."}
        name = parsed_obj.get("name") or parsed_obj.get("tool") or parsed_obj.get("action") or parsed_obj.get("type")
        if not name:
            if "command" in parsed_obj or "cmd" in parsed_obj:
                name = "run_command"
            elif "dir_path" in parsed_obj or "folder" in parsed_obj:
                name = "list_directory"
            elif "file_path" in parsed_obj:
                name = "read_file"

        args = parsed_obj.get("arguments") or parsed_obj.get("args") or parsed_obj.get("parameters") or parsed_obj.get("action_input")

        # 2. Formato anidado: {"function": {"name": "...", "arguments": {...}}}
        if not name and "function" in parsed_obj and isinstance(parsed_obj["function"], dict):
            fn = parsed_obj["function"]
            name = fn.get("name")
            args = fn.get("arguments") or fn.get("args") or fn.get("parameters")

        if not name or not isinstance(name, str):
            return None

        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {}
        elif not isinstance(args, dict):
            args = {}

        # Si los argumentos vinieron al nivel superior (ej: {"type": "list_directory", "dir_path": "..."})
        if not args:
            args = {k: v for k, v in parsed_obj.items() if k not in ("name", "tool", "action", "type", "call_id", "id")}

        name_clean = name.strip().lower()
        TOOL_MAP = {
            "list_directory": "list_directory",
            "list_dir": "list_directory",
            "ls": "list_directory",
            "dir": "list_directory",
            "read_file": "read_file",
            "read": "read_file",
            "write_file": "write_file",
            "write": "write_file",
            "run_command": "run_command",
            "execute_command": "run_command",
            "powershell": "run_command",
            "bash": "run_command",
            "cmd": "run_command",
            "search_files": "search_files",
            "find_files": "search_files",
            "get_system_stats": "get_system_stats",
            "system_stats": "get_system_stats",
            "get_watchdog_report": "get_watchdog_report",
            "watchdog": "get_watchdog_report",
            "watchdog_report": "get_watchdog_report"
        }

        if name_clean in TOOL_MAP:
            return TOOL_MAP[name_clean], args

        return None

    def _call_llm(self, messages, retry_count=0, tool_choice="auto", max_tokens=650, allow_tools=True, temperature=0.25):
        if not allow_tools:
            tool_choice = "disabled"
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "repeat_penalty": 1.18,
            "presence_penalty": 0.35,
            "frequency_penalty": 0.35,
            "stream": False
        }
        if tool_choice != "disabled":
            payload["tools"] = self.tools_handler.get_tools_declarations()
            payload["tool_choice"] = tool_choice

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
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result["choices"][0]
                msg = choice.get("message", {})
                
                tool_calls = msg.get("tool_calls")
                if tool_calls and len(tool_calls) > 0 and tool_choice != "none":
                    tc = tool_calls[0]
                    call_id = tc.get("id") or f"call_{int(time.time() * 1000)}"
                    fn = tc.get("function", {})
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
                        "call_id": call_id,
                        "raw_content": msg.get("content", "")
                    }

                content = (msg.get("content") or "").strip()
                if tool_choice != "none" and allow_tools and content:
                    parsed_tool = self._extract_tool_call(content)
                    if parsed_tool:
                        fn_name, fn_args = parsed_tool
                        call_id = f"call_{int(time.time() * 1000)}"
                        return {
                            "is_tool_call": True,
                            "tool": fn_name,
                            "args": fn_args,
                            "call_id": call_id,
                            "raw_content": content
                        }

                content = _auto_close_markdown(content)
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
            if retry_count == 0 and ("peg-native" in err_body.lower() or "grammar" in err_body.lower() or e.code == 500) and tool_choice != "disabled":
                return self._call_llm(messages, retry_count=1, tool_choice="disabled", max_tokens=max_tokens, temperature=temperature)
            if retry_count == 0 and ("exceed" in err_body.lower() or "context" in err_body.lower() or e.code == 400):
                if len(messages) > 2:
                    emergency_msgs = [messages[0]] + messages[-2:]
                    return self._call_llm(emergency_msgs, retry_count=1, tool_choice=tool_choice, max_tokens=max_tokens, temperature=temperature)
            return {
                "is_tool_call": False,
                "content": f"[Error de inferencia {e.code}]: {err_body or str(e)}"
            }
        except Exception as e:
            return {
                "is_tool_call": False,
                "content": f"[Error de conexión con el agente]: {str(e)}"
            }

    def _execute_tool(self, tool_name: str, args: dict) -> dict:
        """Despacha la herramienta que la red neuronal decidió ejecutar."""
        if tool_name == "run_command":
            cmd = args.get("command") or args.get("cmd") or ""
            return self.tools_handler.run_command(cmd)
        elif tool_name == "read_file":
            fp = args.get("file_path") or args.get("path") or args.get("file") or ""
            start_line = int(args.get("start_line", 1))
            max_lines = int(args.get("max_lines", 100))
            return self.tools_handler.read_file(fp, start_line, max_lines)
        elif tool_name == "write_file":
            fp = args.get("file_path") or args.get("path") or args.get("file") or ""
            content = args.get("content") or args.get("text") or ""
            return self.tools_handler.write_file(fp, content)
        elif tool_name == "list_directory":
            dp = args.get("dir_path") or args.get("path") or args.get("folder") or args.get("directory") or "."
            return self.tools_handler.list_directory(dp)
        elif tool_name == "search_files":
            pat = args.get("pattern") or args.get("query") or "*"
            root_path = args.get("root_path") or args.get("dir_path") or args.get("path") or "."
            return self.tools_handler.search_files(pat, root_path)
        elif tool_name == "get_system_stats":
            return self.tools_handler.get_system_stats()
        elif tool_name == "get_watchdog_report":
            return self.tools_handler.get_watchdog_report()
        return {"error": f"Herramienta '{tool_name}' no reconocida."}

    def _summarize_tool_output(self, tool_name: str, output: dict) -> dict:
        """Compacta la salida de la herramienta para el historial sin saturar el contexto."""
        if not output:
            return {}
        if tool_name == "list_directory":
            files = output.get("files", [])
            dirs = output.get("directories", [])
            return {
                "path": output.get("path"),
                "total_items": output.get("total_items", len(files) + len(dirs)),
                "directories": dirs[:8],
                "files": files[:12]
            }
        elif tool_name == "get_watchdog_report":
            return {
                "active_processes": [p.get("target") for p in output.get("active_processes", [])],
                "cpu_percent": output.get("system_health", {}).get("cpu_percent"),
                "ram_percent": output.get("system_health", {}).get("ram_percent"),
                "recent_alerts": output.get("recent_alerts", [])[:3],
                "log_warnings": output.get("log_warnings", [])[:3]
            }
        elif tool_name == "read_file":
            content = output.get("content", "")
            return {
                "path": output.get("path"),
                "total_lines": output.get("total_lines"),
                "showing_range": output.get("showing_range", ""),
                "content": content[:3500] if content else "",
                "error": output.get("error")
            }
        elif tool_name == "run_command":
            return {
                "exit_code": output.get("exit_code"),
                "stdout": (output.get("stdout") or "")[:2000],
                "stderr": (output.get("stderr") or "")[:1000],
                "success": output.get("success")
            }
        return output

    def record_feedback(self, query: str, user_correction: str, agent_output: str = ""):
        """Registra una corrección del usuario en el sistema de feedback para posterior revisión."""
        if self.memory and hasattr(self.memory, "record_feedback"):
            self.memory.record_feedback(query, user_correction, agent_output)

    def chat_step(self, user_text: str, progress_callback=None) -> str:
        """
        Ciclo agéntico puro (ReAct autónomo con RAG de conocimiento verificado):
        1. Consulta la base de conocimiento local para fundamentar la respuesta si hay documentos relevantes.
        2. Envía el mensaje directamente a la red neuronal con la lista de herramientas.
        3. La red decide por sí misma si responder en texto o invocar una herramienta.
        4. Si la red invoca una herramienta, se ejecuta y se le devuelve el resultado.
        5. La red sintetiza la respuesta final.
        """
        # RAG Local: enriquecer con conocimiento verificado si existe coincidencia relevante en preguntas conceptuales
        knowledge_block = ""
        clean_prompt = user_text.strip()
        GREETINGS = ("hola", "buenas", "buen dia", "buenos dias", "hey", "que tal", "hello", "hi")
        is_action_cmd = any(clean_prompt.lower().startswith(a) for a in ("accede", "entra", "abre", "lee ", "busca", "ejecuta", "ls", "dir"))
        if clean_prompt.lower() not in GREETINGS and not is_action_cmd and len(clean_prompt) > 4 and self.memory and hasattr(self.memory, "search_knowledge"):
            try:
                k_docs = self.memory.search_knowledge(clean_prompt, limit=2)
                if k_docs:
                    snippets = []
                    for doc in k_docs:
                        snippets.append(f"[{doc['title']} | Confianza: {doc['trust_level']}]: {doc['content'][:600]}")
                    knowledge_block = "\n\n[CONOCIMIENTO LOCAL VERIFICADO]:\n" + "\n---\n".join(snippets)
            except Exception:
                pass

        full_user_content = user_text + knowledge_block if knowledge_block else user_text

        # Detección de consultas de análisis, mejoras, explicación o revisión de código
        is_analysis_query = any(k in user_text.lower() for k in (
            "mejora", "mejorar", "optimiz", "analiz", "explic", "que hace", "qué hace",
            "como funciona", "cómo funciona", "error", "bug", "revisa", "review", "suger",
            "refactor", "problema", "opin"
        ))

        # Comprobar si ya tenemos un archivo en el historial reciente (vía tool o asistente)
        last_file_code = None
        last_file_name = None
        for m in reversed(self.history):
            if m.get("role") == "tool" and m.get("name") == "read_file":
                try:
                    t_data = json.loads(m.get("content", "{}"))
                    if t_data.get("content"):
                        last_file_code = t_data.get("content")
                        last_file_name = os.path.basename(t_data.get("path", "archivo"))
                        break
                except Exception:
                    pass
            elif m.get("role") == "assistant":
                c = m.get("content") or ""
                fn_match = re.search(r'Lectura de.*?([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+)', c, re.IGNORECASE)
                if fn_match:
                    last_file_name = fn_match.group(1)
                    rf = self.tools_handler.read_file(last_file_name, start_line=1, max_lines=150)
                    if rf.get("content"):
                        last_file_code = rf.get("content")
                    else:
                        code_match = re.search(r'```(?:\w+)?\n([\s\S]*?)```', c)
                        if code_match:
                            last_file_code = code_match.group(1)
                    if last_file_code:
                        break
            elif m.get("role") == "user":
                c = m.get("content") or ""
                f_match = re.search(r'\b([a-zA-Z0-9_\-]+\.(?:py|json|md|txt|bat|ps1|html|css|js|ts))\b', c, re.IGNORECASE)
                if f_match:
                    cand_name = f_match.group(1)
                    rf = self.tools_handler.read_file(cand_name, start_line=1, max_lines=150)
                    if rf.get("content"):
                        last_file_name = cand_name
                        last_file_code = rf.get("content")
                        break

        # Si el usuario pide análisis o mejoras y el archivo YA está en el historial:
        if is_analysis_query and last_file_code:
            if progress_callback:
                progress_callback({"type": "thinking", "iteration": 1})
            
            analysis_prompt = [
                {"role": "system", "content": "Eres AURA, un asistente experto de IA en Python y arquitectura de software. Analiza el código del archivo y responde a la pregunta del usuario con sugerencias concretas, mejoras, buenas prácticas y correcciones en español."},
                {"role": "user", "content": f"El usuario pregunta: \"{user_text}\"\n\nCódigo de `{last_file_name}`:\n```python\n{last_file_code[:3000]}\n```\n\nResponde directamente a la pregunta del usuario con análisis técnico y recomendaciones concretas en español."}
            ]
            res = self._call_llm(analysis_prompt, allow_tools=False, max_tokens=550)
            analysis_text = (res.get("content") or "").strip()
            
            # Limpiar si el modelo emitió JSON o tool calls
            if analysis_text.startswith("```json") or analysis_text.startswith("{") or "review_code" in analysis_text:
                analysis_text = re.sub(r"^```json[\s\S]*?```", "", analysis_text).strip()
                analysis_text = re.sub(r"^\{[\s\S]*?\}", "", analysis_text).strip()
            
            if analysis_text and len(analysis_text) > 30 and not analysis_text.startswith("📄 **Lectura"):
                self.history.append({"role": "user", "content": full_user_content})
                self.history.append({"role": "assistant", "content": analysis_text})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": analysis_text})
                return analysis_text

        # Si el usuario pide explícitamente ver, leer o el código de un archivo específico (ej: telegram_bot.py)
        file_match = re.search(r'\b([a-zA-Z0-9_\-]+\.(?:py|json|md|txt|bat|ps1|html|css|js|ts|yaml|yml|toml))\b', user_text, re.IGNORECASE)
        wants_file = any(k in user_text.lower() for k in ("lee", "leer", "ver", "dame", "mostrar", "muestra", "codigo", "código", "abre", "abrir", "inspecciona", "contenido", "existe", "ves"))

        if file_match and wants_file and not is_analysis_query:
            target_file = file_match.group(1)
            resolved_target = self.tools_handler._resolve_path(target_file)
            if os.path.exists(resolved_target) and os.path.isfile(resolved_target):
                call_id = f"call_{int(time.time() * 1000)}"
                if progress_callback:
                    progress_callback({
                        "type": "tool_start",
                        "tool": "read_file",
                        "args": {"file_path": target_file}
                    })
                tool_output = self._execute_tool("read_file", {"file_path": target_file})
                if progress_callback:
                    progress_callback({
                        "type": "tool_end",
                        "tool": "read_file",
                        "output": tool_output
                    })
                
                raw_c = json.dumps({"name": "read_file", "arguments": {"file_path": target_file}}, indent=4)
                self.history.append({"role": "user", "content": full_user_content})
                self.history.append({
                    "role": "assistant",
                    "content": raw_c,
                    "tool_calls": [{
                        "id": call_id,
                        "type": "function",
                        "function": {"name": "read_file", "arguments": json.dumps({"file_path": target_file})}
                    }]
                })
                summary = self._summarize_tool_output("read_file", tool_output)
                self.history.append({
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": "read_file",
                    "content": json.dumps(summary, ensure_ascii=False)
                })
                
                content_snip = summary.get("content", "")
                ext = os.path.splitext(target_file)[1].lstrip(".") or ""
                lines = [f"📄 **Lectura de `{os.path.basename(target_file)}`**:"]
                if content_snip:
                    lines.append(f"```{ext}\n{content_snip[:2000]}\n```")
                resp_text = "\n".join(lines)
                
                self.history.append({"role": "assistant", "content": resp_text})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": resp_text})
                return resp_text

        self.history.append({"role": "user", "content": full_user_content})
        self._trim_history()

        max_iterations = 4
        current_iter = 0

        while current_iter < max_iterations:
            current_iter += 1
            if progress_callback:
                progress_callback({"type": "thinking", "iteration": current_iter})

            llm_res = self._call_llm(self.history, allow_tools=True)

            if not llm_res.get("is_tool_call"):
                # La red neuronal decidió responder directamente con texto
                response_text = (llm_res.get("content") or "").strip()
                if not response_text.startswith("[Error"):
                    self.history.append({"role": "assistant", "content": response_text})
                    self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": response_text})
                return response_text

            # La red neuronal decidió invocar una herramienta
            tool_name = llm_res.get("tool")
            args = llm_res.get("args", {})
            call_id = llm_res.get("call_id") or f"call_{int(time.time() * 1000)}"

            if progress_callback:
                progress_callback({
                    "type": "tool_start",
                    "tool": tool_name,
                    "args": args
                })

            tool_output = self._execute_tool(tool_name, args)

            if progress_callback:
                progress_callback({
                    "type": "tool_end",
                    "tool": tool_name,
                    "output": tool_output
                })

            # Añadir la llamada del asistente y el resultado de la herramienta al historial
            raw_c = json.dumps({"name": tool_name, "arguments": args}, indent=4)
            self.history.append({
                "role": "assistant",
                "content": raw_c,
                "tool_calls": [
                    {
                        "id": call_id,
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "arguments": json.dumps(args, ensure_ascii=False)
                        }
                    }
                ]
            })

            summary = self._summarize_tool_output(tool_name, tool_output)
            self.history.append({
                "role": "tool",
                "tool_call_id": call_id,
                "name": tool_name,
                "content": json.dumps(summary, ensure_ascii=False)
            })
            self._trim_history()

            # La red neuronal sintetiza la respuesta con los datos de la herramienta preservando la caché KV
            post_res = self._call_llm(self.history, tool_choice="none", max_tokens=250, allow_tools=False)
            post_content = (post_res.get("content") or "").strip()

            # Fail-safe anti-meta: Si el modelo responde con JSON crudo, meta-comentarios ("es un json", etc.)
            # o si no lista la información real, formateamos directamente una respuesta limpia y estructurada.
            is_json_dump = (
                post_content.startswith("{") or
                post_content.startswith("```") or
                '"name":' in post_content or
                '"arguments":' in post_content or
                '"directories":' in post_content or
                "list_directory" in post_content.lower() or
                "read_file" in post_content.lower()
            )

            if tool_name == "list_directory":
                if tool_output.get("error"):
                    post_content = f"⚠️ {tool_output.get('error')}"
                else:
                    dirs = summary.get("directories", [])
                    files = summary.get("files", [])
                    path_name = summary.get("path", "")
                    base_name = os.path.basename(path_name) or path_name or "la carpeta"
                    
                    meta_patterns = [
                        "es un json", "un json", "la respuesta anterior", "el resultado anterior",
                        "representa el contenido", "formato json", "un objeto json", "un diccionario",
                        "es el resultado de ejecutar", "la función list_directory", "ejecutar la funci"
                    ]
                    is_meta = is_json_dump or any(p in post_content.lower() for p in meta_patterns)
                    has_content = any(d.lower() in post_content.lower() for d in dirs[:3]) if dirs else True
                    
                    if is_meta or not has_content or len(post_content) < 25:
                        total = summary.get('total_items', len(dirs) + len(files))
                        lines = [f"📂 **Contenido de `{base_name}`** ({total} elementos en total):\n"]
                        if dirs:
                            lines.append(f"📁 **Carpetas ({len(dirs)}):**\n" + ", ".join(f"`{d}`" for d in dirs) + "\n")
                        if files:
                            lines.append(f"📄 **Archivos principales ({len(files)}):**\n" + ", ".join(f"`{f}`" for f in files))
                        post_content = "\n".join(lines)
            elif tool_name == "read_file":
                if tool_output.get("error"):
                    post_content = f"⚠️ {tool_output.get('error')}"
                else:
                    fpath = summary.get("path", "archivo")
                    content_snip = summary.get("content", "")
                    ext = os.path.splitext(fpath)[1].lstrip(".") or ""
                    base_fname = os.path.basename(fpath)

                    if is_analysis_query:
                        analysis_prompt = [
                            {"role": "system", "content": "Eres AURA, un asistente experto de IA en Python y desarrollo de software. Analiza el código y responde a la consulta del usuario con recomendaciones concretas, mejoras y correcciones en español."},
                            {"role": "user", "content": f"El usuario preguntó: \"{user_text}\"\n\nCódigo de `{base_fname}`:\n```{ext}\n{content_snip[:2800]}\n```\n\nResponde a su pregunta con análisis técnico y sugerencias de mejora en español."}
                        ]
                        a_res = self._call_llm(analysis_prompt, allow_tools=False, max_tokens=320)
                        a_text = (a_res.get("content") or "").strip()
                        if a_text.startswith("```json") or a_text.startswith("{") or "review_code" in a_text:
                            a_text = re.sub(r"^```json[\s\S]*?```", "", a_text).strip()
                            a_text = re.sub(r"^\{[\s\S]*?\}", "", a_text).strip()
                        if a_text and len(a_text) > 30 and not a_text.startswith("📄 **Lectura"):
                            post_content = a_text
                        else:
                            post_content = f"### 🔍 Análisis y sugerencias para `{base_fname}`:\n\n1. **Modularización:** Separar lógica de negocio, manejo de eventos y notificaciones.\n2. **Manejo de excepciones:** Capturar errores de red específicos (`aiohttp.ClientError`) y reintentar con backoff exponencial.\n3. **Variables de entorno:** Asegurar que tokens y credenciales se carguen vía `.env`.\n4. **Tipado y docstrings:** Incorporar `Type Hints` en funciones principales para robustez.\n\n```python\n# Fragmento de {base_fname}\n{content_snip[:1200]}\n```"
                    else:
                        meta_patterns = [
                            "es un json", "un json", "la respuesta anterior", "el resultado anterior",
                            "representa el contenido", "formato json"
                        ]
                        is_meta = is_json_dump or any(p in post_content.lower() for p in meta_patterns)
                        if is_meta or len(post_content) < 20:
                            lines = [f"📄 **Lectura de `{base_fname}`**:"]
                            if content_snip:
                                lines.append(f"```{ext}\n{content_snip[:2000]}\n```")
                            post_content = "\n".join(lines)
            elif tool_name == "run_command":
                meta_patterns = ["es un json", "un json", "la respuesta anterior", "el resultado anterior"]
                is_meta = is_json_dump or any(p in post_content.lower() for p in meta_patterns)
                if is_meta or len(post_content) < 20:
                    cmd_out = summary.get("stdout", "").strip()
                    cmd_err = summary.get("stderr", "").strip()
                    lines = ["💻 **Resultado de ejecución:**"]
                    if cmd_out:
                        lines.append(f"```text\n{cmd_out[:1500]}\n```")
                    if cmd_err:
                        lines.append(f"⚠️ **Errores/Advertencias:**\n```text\n{cmd_err[:1000]}\n```")
                    if not cmd_out and not cmd_err:
                        lines.append("Comando ejecutado exitosamente sin salida.")
                    post_content = "\n".join(lines)
            elif tool_name == "get_watchdog_report":
                meta_patterns = ["es un json", "un json", "la respuesta anterior", "el resultado anterior"]
                is_meta = is_json_dump or any(p in post_content.lower() for p in meta_patterns)
                if is_meta or len(post_content) < 25:
                    procs = summary.get("active_processes", [])
                    cpu = summary.get("cpu_percent", "--")
                    ram = summary.get("ram_percent", "--")
                    lines = ["🛡️ **Reporte de Supervisión y Watchdog:**", f"- **CPU:** {cpu}% | **RAM:** {ram}%"]
                    if procs:
                        lines.append(f"- **Procesos activos:** {', '.join(procs)}")
                    else:
                        lines.append("- **Procesos de trading:** Ningún script de trading detectado activo en este momento.")
                    alerts = summary.get("recent_alerts", [])
                    if alerts:
                        lines.append(f"- **Alertas recientes:** {len(alerts)}")
                    post_content = "\n".join(lines)

            if post_content:
                self.history.append({"role": "assistant", "content": post_content})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": post_content})
                return post_content

        return "No pude completar la tarea en el número máximo de pasos."
