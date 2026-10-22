"""
Servidor Web Ultraligero para el Agente Local y Motor de Debate Multi-Agente.
Cero dependencias externas: utiliza http.server nativo de Python con multithreading.
Sirve la interfaz web moderna y proporciona endpoints API REST.
"""

import os
import sys
import json
import re
import mimetypes
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

try:
    from agent.core import LocalAgent
    from agent.memory import LocalMemory
    from agent.cloud_debate import CloudDebateEngine
except Exception:
    try:
        from core import LocalAgent
        from memory import LocalMemory
        from cloud_debate import CloudDebateEngine
    except Exception:
        from .core import LocalAgent
        from .memory import LocalMemory
        from .cloud_debate import CloudDebateEngine

WEB_DIR = os.path.join(BASE_DIR, "web")
WORKSPACE_DIR = BASE_DIR

memory = LocalMemory()
agent = LocalAgent(api_base="http://127.0.0.1:8089/v1", workspace=WORKSPACE_DIR, memory=memory)
debate_engine = CloudDebateEngine()

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True

class AgentRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Desactivar logs ruidosos en consola
        return

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(self, content: bytes, mime_type: str = "text/plain", status=200):
        self.send_response(status)
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Connection", "close")
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # API: Estado del sistema y motor
        if path == "/api/status":
            server_online = agent.is_server_online()
            stats = agent.tools_handler.get_system_stats()
            mem_stats = memory.get_stats()
            debate_status = debate_engine.is_configured()
            
            # Contar muestras en dataset de destilación
            distill_count = 0
            dataset_path = os.path.join(BASE_DIR, "data", "distillation_dataset.jsonl")
            if os.path.exists(dataset_path):
                try:
                    with open(dataset_path, "r", encoding="utf-8") as f:
                        distill_count = sum(1 for line in f if line.strip())
                except Exception:
                    pass

            response = {
                "server_online": server_online,
                "model": "Qwen 2.5 Coder 1.5B (Local)",
                "system": stats,
                "memory": mem_stats,
                "debate": debate_status,
                "distilled_samples": distill_count
            }
            self._send_json(response, 200)
            return

        # API: Estado específico del motor de debate
        if path == "/api/debate/status":
            st = debate_engine.is_configured()
            st["groq_masked"] = (debate_engine.groq_key[:6] + "..." + debate_engine.groq_key[-4:]) if len(debate_engine.groq_key) > 10 else ("Configurada" if debate_engine.groq_key else "")
            st["gemini_masked"] = (debate_engine.gemini_key[:6] + "..." + debate_engine.gemini_key[-4:]) if len(debate_engine.gemini_key) > 10 else ("Configurada" if debate_engine.gemini_key else "")
            distill_count = 0
            dataset_path = os.path.join(BASE_DIR, "data", "distillation_dataset.jsonl")
            if os.path.exists(dataset_path):
                try:
                    with open(dataset_path, "r", encoding="utf-8") as f:
                        distill_count = sum(1 for line in f if line.strip())
                except Exception:
                    pass
            st["distilled_samples"] = distill_count
            self._send_json(st, 200)
            return

        # API: Lista de herramientas activas
        if path == "/api/tools":
            tools = agent.tools_handler.get_tools_declarations()
            self._send_json(tools, 200)
            return

        # API: Búsqueda en memoria local
        if path == "/api/memory/search":
            q = query.get("q", [""])[0]
            results = memory.search(q)
            self._send_json(results, 200)
            return

        # Servir archivos estáticos de la interfaz web
        if path == "/" or path == "":
            path = "/index.html"
        
        file_path = os.path.join(WEB_DIR, path.lstrip("/"))
        if os.path.exists(file_path) and os.path.isfile(file_path):
            mime_type, _ = mimetypes.guess_type(file_path)
            mime_type = mime_type or "application/octet-stream"
            try:
                with open(file_path, "rb") as f:
                    content = f.read()
                self._send_bytes(content, mime_type, 200)
            except Exception as e:
                self._send_bytes(str(e).encode("utf-8"), "text/plain", 500)
        else:
            self._send_bytes(b"404 Not Found", "text/plain", 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        # API: Configurar claves del Cerebro Dual (Groq / Gemini)
        if path == "/api/debate/keys":
            groq_key = data.get("groq_key")
            gemini_key = data.get("gemini_key")
            debate_engine.save_keys(groq_key=groq_key, gemini_key=gemini_key)
            self._send_json({"success": True, "status": debate_engine.is_configured()}, 200)
            return

        # API: Chat agéntico (Modo Local o Modo Debate Multi-Agente)
        if path == "/api/chat":
            user_message = data.get("message", "").strip()
            mode = data.get("mode", "auto")  # "auto", "debate", "local"
            history = data.get("history", [])
            if not user_message:
                self._send_json({"error": "Mensaje vacío"}, 400)
                return

            events = []
            def on_progress(event):
                events.append(event)

            # Si el usuario eligió debate o si está en auto con claves configuradas
            debate_ready = debate_engine.is_configured()["debate_ready"] or debate_engine.is_configured()["groq_ready"] or debate_engine.is_configured()["gemini_ready"]
            
            if mode == "debate" and not debate_ready:
                resp = {
                    "success": False,
                    "need_keys": True,
                    "error": "Para activar el Modo Debate Multi-Agente (Groq 70B vs Gemini), ingresa al menos una clave API gratuita (Groq o Gemini). Haz clic en el botón '⚙️ Claves Cloud' arriba a la derecha."
                }
                self._send_json(resp, 200)
                return

            use_debate = (mode == "debate") or (mode == "auto" and debate_ready)

            if use_debate and debate_ready:
                try:
                    system_info = "Sistema operativo: Windows 10."
                    debate_res = debate_engine.run_debate(
                        user_message,
                        history=history,
                        system_tools_info=system_info,
                        tools_handler=agent.tools_handler,
                        progress_callback=on_progress
                    )
                    
                    if debate_res.get("consensus"):
                        # Alimentar memoria RAG local con el consenso
                        memory.add_document("debate_distill", f"Consenso: {user_message[:35]}", debate_res["final_response"], "distilled_knowledge")

                    combined_events = debate_res.get("tool_events", [])
                    if not combined_events and events:
                        combined_events = events

                    resp = {
                        "success": True,
                        "response": debate_res.get("final_response", ""),
                        "debate_rounds": debate_res.get("debate_rounds", []),
                        "mode_used": "debate_cloud",
                        "tool_events": combined_events
                    }
                    self._send_json(resp, 200)
                except Exception as e:
                    print(f"[AURA SERVER] Cloud debate no disponible ({e}). Degradando automáticamente a agente local...")
                    try:
                        agent.reset_conversation()
                        if history:
                            for h_msg in history[-6:]:
                                role = h_msg.get("role", "user")
                                content = h_msg.get("content", "")
                                if content and role in ("user", "assistant"):
                                    agent.history.append({"role": role, "content": content})
                        response_text = agent.chat_step(user_message, progress_callback=on_progress)
                        resp = {
                            "success": True,
                            "response": response_text,
                            "mode_used": "local_agent_fallback",
                            "tool_events": events,
                            "warning": f"Nube no disponible ({str(e)}). Se utilizó el agente local."
                        }
                        self._send_json(resp, 200)
                        return
                    except Exception as inner_e:
                        self._send_json({"error": f"Error: {str(inner_e)}"}, 500)
                        return

            # Modo Local tradicional
            try:
                agent.reset_conversation()
                if history:
                    for h_msg in history[-6:]:
                        role = h_msg.get("role", "user")
                        content = (h_msg.get("content") or "").strip()
                        if content and role in ("user", "assistant"):
                            if role == "user" and content.lower() == user_message.lower():
                                continue
                            agent.history.append({"role": role, "content": content})

                response_text = agent.chat_step(user_message, progress_callback=on_progress)
                resp = {
                    "success": True,
                    "response": response_text,
                    "mode_used": "local_agent",
                    "tool_events": events
                }
                self._send_json(resp, 200)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                return
            except Exception as e:
                try:
                    self._send_json({"error": str(e)}, 500)
                except Exception:
                    pass
            return

        # API: Reiniciar conversación
        if path == "/api/reset":
            agent.reset_conversation()
            self._send_json({"success": True}, 200)
            return

        # API: Indexar documento en memoria
        if path == "/api/memory/add":
            source = data.get("source", "manual")
            title = data.get("title", "Nota")
            content = data.get("content", "")
            category = data.get("category", "general")
            memory.add_document(source, title, content, category)
            self._send_json({"success": True}, 200)
            return

        self._send_bytes(b"404 Not Found", "text/plain", 404)

def run(port=5000):
    server_address = ("127.0.0.1", port)
    httpd = ThreadedHTTPServer(server_address, AgentRequestHandler)
    print(f"[AURA CORE] Servidor Web y Motor de Debate activo en http://127.0.0.1:{port}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDeteniendo servidor...")
        httpd.server_close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    run(port)
