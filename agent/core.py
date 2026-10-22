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

try:
    from .tools import AgentTools
except Exception:
    try:
        from agent.tools import AgentTools
    except Exception:
        from tools import AgentTools

SYSTEM_PROMPT = """You are an autonomous AI coding assistant running locally on the user's PC.
You have access to native tools to explore files, read source code, and run commands.
- Use `list_directory` when the user asks to see, explore, or access a folder or files.
- Use `read_file` when the user asks to view or inspect code in a file.
- Use `search_files` to find files matching a name or pattern.
- Use `run_command` to execute shell commands when needed.
When the user asks conversational questions, greets you, or asks what you can do, answer directly in Spanish without calling tools.
Be concise, direct, and helpful in your answers. Always respond in clear Spanish."""

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

    def _call_llm(self, messages, retry_count=0, allow_tools=True):
        url = f"{self.api_base}/chat/completions"
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 256,
            "stream": False
        }
        if allow_tools:
            payload["tools"] = self.tools_handler.get_tools_declarations()
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
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                choice = result["choices"][0]
                msg = choice.get("message", {})
                
                tool_calls = msg.get("tool_calls")
                if tool_calls and len(tool_calls) > 0:
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
            if retry_count == 0 and ("exceed" in err_body.lower() or "context" in err_body.lower() or e.code == 400):
                if len(messages) > 2:
                    emergency_msgs = [messages[0]] + messages[-2:]
                    return self._call_llm(emergency_msgs, retry_count=1, allow_tools=allow_tools)
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
                "directories": dirs[:15],
                "files": files[:30]
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

    def chat_step(self, user_text: str, progress_callback=None) -> str:
        """
        Ciclo agéntico puro (ReAct autónomo):
        1. Envía el mensaje directamente a la red neuronal con la lista de herramientas.
        2. La red decide por sí misma si responder en texto o invocar una herramienta.
        3. Si la red invoca una herramienta, se ejecuta y se le devuelve el resultado.
        4. La red sintetiza la respuesta final.
        Cero condicionales de palabras clave. Cero heurísticas.
        """
        self.history.append({"role": "user", "content": user_text})
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
            self.history.append({
                "role": "assistant",
                "content": None,
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

            # La red neuronal sintetiza la respuesta con los datos de la herramienta
            post_res = self._call_llm(self.history, allow_tools=False)
            post_content = (post_res.get("content") or "").strip()

            if post_content:
                self.history.append({"role": "assistant", "content": post_content})
                self._trim_history()
                if progress_callback:
                    progress_callback({"type": "response", "content": post_content})
                return post_content

        return "No pude completar la tarea en el número máximo de pasos."
