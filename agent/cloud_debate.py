"""
Motor de Debate Multi-Agente (Multi-Agent Debate / Consensus).
Orquesta el enfrentamiento y consenso entre:
- Groq (Llama-3.3-70B-Versatile): Propuestas de código de alta velocidad y arquitectura.
- Google Gemini (Gemini-1.5-Flash / Gemini-2.0-Flash): Crítico analítico y optimización de casos borde.

Genera salidas de nivel experto y alimenta el dataset local de destilación (Teacher-Student)
para el modelo local Qwen 7B.
Cero dependencias externas (utiliza urllib nativo de Python).
"""

import os
import sys
import json
import urllib.request
import urllib.error
import time
from pathlib import Path
import re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
DATASET_FILE = os.path.join(DATA_DIR, "distillation_dataset.jsonl")

class CloudDebateEngine:
    def __init__(self, groq_key: str = None, gemini_key: str = None):
        self.groq_key = groq_key or os.environ.get("GROQ_API_KEY", "")
        self.gemini_key = gemini_key or os.environ.get("GEMINI_API_KEY", "")
        self.last_dir = None
        self._load_config()
        os.makedirs(DATA_DIR, exist_ok=True)

    def _load_config(self):
        """Carga claves API desde config.json si existen."""
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    if not self.groq_key and cfg.get("groq_api_key"):
                        self.groq_key = cfg.get("groq_api_key")
                    if not self.gemini_key and cfg.get("gemini_api_key"):
                        self.gemini_key = cfg.get("gemini_api_key")
            except Exception:
                pass

    def save_keys(self, groq_key: str = None, gemini_key: str = None):
        """Persiste las claves API en config.json local."""
        cfg = {}
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}

        if groq_key is not None:
            self.groq_key = groq_key.strip()
            cfg["groq_api_key"] = self.groq_key
        if gemini_key is not None:
            self.gemini_key = gemini_key.strip()
            cfg["gemini_api_key"] = self.gemini_key

        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def is_configured(self) -> dict:
        """Verifica qué proveedores en la nube están listos."""
        return {
            "groq_ready": bool(self.groq_key),
            "gemini_ready": bool(self.gemini_key),
            "debate_ready": bool(self.groq_key and self.gemini_key)
        }

    def _call_groq(self, messages, model="openai/gpt-oss-120b", max_tokens=950) -> str:
        """Consulta Groq API con fallback dinámico entre modelos disponibles y límite seguro de tokens."""
        if not self.groq_key:
            raise ValueError("Falta la clave GROQ_API_KEY. Configúrala en la interfaz.")

        candidate_models = [model, "llama-3.3-70b-versatile", "llama-3.1-8b-instant", "mixtral-8x7b-32768", "gemma2-9b-it", "allam-2-7b"]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_error = None
        for m in models_to_try:
            safe_tokens = min(max_tokens, 650) if "qwen" in m.lower() else min(max_tokens, 1500)
            url = "https://api.groq.com/openai/v1/chat/completions"

            # Prevenir que modelos como gpt-oss-120b intenten llamadas a funciones de contenedor (tool_use_failed)
            safe_messages = []
            has_sys = False
            for msg in messages:
                if msg.get("role") == "system":
                    has_sys = True
                    safe_messages.append({
                        "role": "system",
                        "content": f"{msg.get('content', '')}\n[Instrucción técnica: Responde directamente en texto y markdown. No generes llamadas a herramientas ni bloques de funciones externas]."
                    })
                else:
                    safe_messages.append(msg)
            if not has_sys:
                safe_messages.insert(0, {
                    "role": "system",
                    "content": "Responde directamente en texto y markdown sin llamadas a herramientas externas."
                })

            payload = {
                "model": m,
                "messages": safe_messages,
                "temperature": 0.4,
                "max_tokens": safe_tokens
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.groq_key}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AuraDebate/1.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=35) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or msg.get("reasoning") or ""
                    return content.strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                last_error = f"Error Groq (HTTP {e.code}): {err_body}"
                # Fallback dinámico si el modelo no existe (404), excede tokens (429) o falló por llamada de herramienta nativa (400 tool_use_failed)
                if e.code in (400, 404, 429) or "tool_use_failed" in err_body or "model_not_found" in err_body or "rate_limit_exceeded" in err_body:
                    continue
                raise RuntimeError(last_error)
            except Exception as e:
                last_error = f"Error de conexión con Groq: {str(e)}"
                continue

        raise RuntimeError(last_error or "No se pudo conectar con ningún modelo de Groq disponible.")

    def _call_gemini(self, messages, model="gemini-1.5-flash", max_tokens=2048) -> str:
        """Consulta Google AI Studio con fallback dinámico entre modelos."""
        if not self.gemini_key:
            raise ValueError("Falta la clave GEMINI_API_KEY. Configúrala en la interfaz.")

        candidate_models = [model, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-flash-latest", "gemini-2.5-flash"]
        seen = set()
        models_to_try = [m for m in candidate_models if not (m in seen or seen.add(m))]

        last_error = None
        for m in models_to_try:
            url = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
            payload = {
                "model": m,
                "messages": messages,
                "temperature": 0.4,
                "max_tokens": max_tokens
            }
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.gemini_key}",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AuraDebate/1.0"
                    }
                )
                with urllib.request.urlopen(req, timeout=35) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    msg = data["choices"][0]["message"]
                    content = msg.get("content") or ""
                    return content.strip()
            except urllib.error.HTTPError as e:
                err_body = e.read().decode("utf-8", errors="ignore")
                last_error = f"Error Gemini (HTTP {e.code}): {err_body}"
                if e.code == 429 or "RESOURCE_EXHAUSTED" in err_body or "quota" in err_body.lower():
                    self._gemini_exhausted = True
                    break
                if e.code == 404 or "not found" in err_body.lower():
                    continue
                raise RuntimeError(last_error)
            except Exception as e:
                last_error = f"Error de conexión con Gemini: {str(e)}"
                continue

        raise RuntimeError(last_error or "No se pudo conectar con ningún modelo de Gemini disponible.")

    def _find_matching_directory(self, query: str, workspace_root: str = None) -> str:
        """Busca dinámicamente si el usuario menciona una carpeta o ruta en su sistema."""
        import re
        # 1. Ruta absoluta explícita en el texto
        m = re.search(r'[a-zA-Z]:\\[^"\'\n\r<>|*?]+', query)
        if m and os.path.isdir(m.group(0).strip()):
            return m.group(0).strip()
        
        # 2. Búsqueda dinámica en carpetas de usuario estándar
        user_home = Path.home()
        search_roots = [
            str(user_home / "Downloads"),
            str(user_home / "Desktop"),
            str(user_home / "Documents"),
            str(user_home),
            workspace_root or BASE_DIR,
            str(Path.cwd())
        ]
        
        q_norm = re.sub(r'[^a-zA-Z0-9]', '', query.lower())
        for root in search_roots:
            if not os.path.exists(root):
                continue
            try:
                for entry in os.listdir(root):
                    full = os.path.join(root, entry)
                    if os.path.isdir(full):
                        entry_norm = re.sub(r'[^a-zA-Z0-9]', '', entry.lower())
                        if len(entry_norm) >= 2 and entry_norm in q_norm:
                            return full
            except Exception:
                pass
        return None

    def _find_matching_file(self, query: str, current_dir: str = None) -> str:
        """Busca dinámicamente un archivo mencionado con extensión en el sistema."""
        import re
        m = re.search(r'\b([a-zA-Z0-9_\-]+\.[a-zA-Z0-9]{1,5})\b', query)
        if not m:
            return None
        fname = m.group(1).strip()
        
        user_home = Path.home()
        dirs_to_check = []
        if current_dir and os.path.isdir(current_dir):
            dirs_to_check.append(current_dir)
        dirs_to_check.extend([
            BASE_DIR,
            str(Path.cwd()),
            str(user_home / "Downloads"),
            str(user_home / "Desktop"),
            str(user_home / "Documents"),
            str(user_home)
        ])
        
        for d in dirs_to_check:
            if not d or not os.path.exists(d):
                continue
            full = os.path.join(d, fname)
            if os.path.isfile(full):
                return full
            # Búsqueda dinámica en subdirectorios inmediatos (1 nivel)
            try:
                for sub in os.listdir(d):
                    sub_path = os.path.join(d, sub)
                    if os.path.isdir(sub_path):
                        target = os.path.join(sub_path, fname)
                        if os.path.isfile(target):
                            return target
            except Exception:
                pass
        return None

    def _clean_consensus_response(self, text: str) -> str:
        """
        Garantiza que la respuesta entregada al usuario sea la respuesta directa final,
        removiendo artefactos de meta-evaluación interna o tablas de fortalezas/debilidades.
        """
        if not text:
            return ""
        clean = text.strip()

        # 1. Si el modelo puso una sección explícita de respuesta sugerida o definitiva
        patterns = [
            r'(?:Mejora recomendada\s*\([^)]*\)|Respuesta sugerida|Respuesta definitiva|Respuesta final para el usuario|Mensaje para el usuario)\s*:\s*\n*(.+)',
            r'###\s*(?:Respuesta sugerida|Respuesta definitiva|Mensaje al usuario|Respuesta final)\s*\n*(.+)',
        ]
        for pat in patterns:
            m = re.search(pat, clean, re.DOTALL | re.IGNORECASE)
            if m and len(m.group(1).strip()) > 15:
                return m.group(1).strip()

        # 2. Si empieza con un encabezado típico de evaluación o auditoría interna
        meta_headers = [
            r"^#+\s*Evaluación\b",
            r"^#+\s*Auditoría\b",
            r"^#+\s*Fortalezas de la propuesta\b",
            r"^✅\s*Fortalezas\b",
            r"^#+\s*Análisis crítico\b"
        ]
        for mh in meta_headers:
            if re.search(mh, clean, re.IGNORECASE):
                parts = re.split(r'\n(?:###?|##)\s*(?:Respuesta|Mensaje|Solución|Conclusión|Propuesta final|Recomendación final)[^\n]*\n', clean, flags=re.IGNORECASE)
                if len(parts) > 1 and len(parts[-1].strip()) > 20:
                    return parts[-1].strip()
        return clean

    def run_debate(self, user_query: str, history: list = None, system_tools_info: str = "", tools_handler=None, progress_callback=None) -> dict:
        """
        Ejecuta el protocolo de debate adversarial multi-agente (Groq 120B vs Gemini Flash),
        con resolución dinámica de herramientas y memoria multi-turno limpia.
        """
        self._load_config()
        status = self.is_configured()

        # Contexto de conversación previa
        history_msgs = []
        if history and isinstance(history, list):
            for h in history[-6:]:
                role = "assistant" if h.get("role") in ("ai", "assistant") else "user"
                content = h.get("content") or h.get("text") or ""
                if content:
                    if len(content) > 600:
                        content = content[:600] + "... [truncado]"
                    history_msgs.append({"role": role, "content": content})

        # Resolución dinámica de herramientas (carpetas y archivos)
        tool_context = ""
        executed_tool_events = []

        if tools_handler:
            q_lower = user_query.lower()
            
            # A) Acceso o inspección de directorios
            target_dir = self._find_matching_directory(user_query)
            if not target_dir:
                if self.last_dir and os.path.isdir(self.last_dir):
                    target_dir = self.last_dir
                elif history:
                    for h in reversed(history):
                        h_content = h.get("content") or h.get("text") or ""
                        matched = self._find_matching_directory(h_content)
                        if matched:
                            target_dir = matched
                            break

            if target_dir and os.path.isdir(target_dir):
                self.last_dir = target_dir
                tools_handler.current_dir = target_dir
                
                needs_listing = any(w in q_lower for w in [
                    "accede", "entra", "carpeta", "carpetas", "archivos", "archivo", 
                    "mira", "lista", "listar", "ver", "contenido", "directorio", 
                    "explora", "que hay", "qué hay", "hay algun", "hay algún", "main", "codigo", "código", "dime"
                ])
                if needs_listing:
                    if progress_callback:
                        progress_callback({"type": "tool_start", "tool": "list_directory", "args": {"dir_path": target_dir}})
                    executed_tool_events.append({"type": "tool_start", "tool": "list_directory", "args": {"dir_path": target_dir}})
                    dir_res = tools_handler.list_directory(target_dir)
                    tool_context += f"\n\n[DATOS DEL SISTEMA: Archivos y carpetas en '{target_dir}']:\n{json.dumps(dir_res, ensure_ascii=False)}\n"

            # B) Lectura de archivo específico
            target_file = self._find_matching_file(user_query, current_dir=self.last_dir)
            if not target_file and self.last_dir and "main" in q_lower:
                for candidate in ["main.py", "main.pyw", "main.js", "main.ts", "index.py", "app.py"]:
                    cand_path = os.path.join(self.last_dir, candidate)
                    if os.path.isfile(cand_path):
                        target_file = cand_path
                        break

            if target_file and any(w in q_lower for w in ["lee", "leer", "codigo", "código", "muestra", "ver", "contenido", "abre", "hay"]):
                if progress_callback:
                    progress_callback({"type": "tool_start", "tool": "read_file", "args": {"file_path": target_file}})
                executed_tool_events.append({"type": "tool_start", "tool": "read_file", "args": {"file_path": target_file}})
                file_res = tools_handler.read_file(target_file, max_lines=150)
                tool_context += f"\n\n[DATOS DEL SISTEMA: Contenido de '{os.path.basename(target_file)}']:\n{json.dumps(file_res, ensure_ascii=False)}\n"

        # Si solo hay un proveedor disponible, operar en modo directo
        if not status["debate_ready"]:
            if status["groq_ready"]:
                if progress_callback: progress_callback({"type": "debate_round", "agent": "Groq (Arquitecto 120B)", "status": "Respondiendo con Groq 120B..."})
                msgs = [
                    {"role": "system", "content": f"Eres AURA CORE, asistente de ingeniería de software en Windows 10. {system_tools_info}\nTienes herramientas locales integradas. Si se te proporcionan datos de herramientas, utilízalos de forma precisa. NUNCA le pidas al usuario que abra CMD o PowerShell para explorar archivos."},
                ]
                msgs.extend(history_msgs)
                msgs.append({"role": "user", "content": f"{user_query}{tool_context}"})
                ans = self._call_groq(msgs, model="openai/gpt-oss-120b")
                self.record_distillation(user_query, "Modo Directo Groq 120B", ans)
                return {
                    "final_response": ans,
                    "debate_rounds": [{"agent": "Groq (Arquitecto 120B)", "role": "Respuesta Directa", "content": ans}],
                    "consensus": True,
                    "tool_events": executed_tool_events
                }
            elif status["gemini_ready"]:
                if progress_callback: progress_callback({"type": "debate_round", "agent": "Gemini Flash", "status": "Respondiendo con Gemini..."})
                msgs = [
                    {"role": "system", "content": f"Eres AURA CORE, asistente de ingeniería de software en Windows 10. {system_tools_info}\nSi se te proporcionan datos de herramientas, utilízalos de forma precisa."},
                ]
                msgs.extend(history_msgs)
                msgs.append({"role": "user", "content": f"{user_query}{tool_context}"})
                ans = self._call_gemini(msgs)
                self.record_distillation(user_query, "Modo Directo Gemini Flash", ans)
                return {
                    "final_response": ans,
                    "debate_rounds": [{"agent": "Google Gemini", "role": "Respuesta Directa", "content": ans}],
                    "consensus": True,
                    "tool_events": executed_tool_events
                }
            else:
                return {
                    "error": "No se han configurado las claves API de Groq o Gemini.",
                    "final_response": "Por favor ingresa tus claves API gratuitas de **Groq** y **Gemini** en el botón de ajustes (⚙️ Claves Cloud) para activar el Debate Adversarial y super-entrenamiento."
                }

        # Detección de mensajes puramente conversacionales, humor o confirmaciones breves
        q_clean = user_query.strip().lower()
        tech_indicators = [
            "codigo", "código", "script", "archivo", "analiza", "optimiza", 
            "refactoriza", "bug", "error", "función", "funcion", "clase", 
            "def ", "import ", "crea", "haz", "modifica", "escribe", "arregla",
            "bot", "trading", "alpaca", "telegram", "terminal", "log", "logs",
            "directorio", "carpeta", "accede", "entra", "lee", "ver"
        ]
        has_tech_intent = any(k in q_clean for k in tech_indicators) or bool(tool_context)
        
        is_casual = (
            not has_tech_intent and (
                len(user_query.strip()) < 75 and
                any(w in q_clean for w in [
                    "jaja", "jeje", "gracias", "ok", "dale", "hola", "buenas", 
                    "no te adelantes", "solo te pedí", "calma", "jajaja", 
                    "chau", "adiós", "bueno", "perfecto", "entendido", "bien"
                ])
            )
        )
        
        if is_casual:
            if progress_callback:
                progress_callback({"type": "debate_round", "agent": "AURA Asistente", "status": "Respondiendo directamente..."})
            casual_sys = f"""Eres AURA, un asistente técnico inteligente, simpático, cercano y natural en Windows.
El usuario te está hablando de manera informal, con humor, ironía o confirmando una acción previa.
Responde de forma 100% natural, cercana, empática y breve (1 o 2 oraciones).
No des sermones, no hagas tablas, ni analices la conversación como si fueras un auditor.
Responde en español directamente al usuario."""
            casual_msgs = [{"role": "system", "content": casual_sys}]
            casual_msgs.extend(history_msgs)
            casual_msgs.append({"role": "user", "content": user_query})
            ans = self._call_groq(casual_msgs, model="openai/gpt-oss-120b", max_tokens=250)
            clean_ans = self._clean_consensus_response(ans)
            return {
                "success": True,
                "final_response": clean_ans,
                "debate_rounds": [{"agent": "AURA", "role": "Conversación", "content": clean_ans}],
                "consensus": True,
                "tool_events": executed_tool_events
            }

        debate_rounds = []

        # RONDA 1: Groq Arquitecto (120B) propone
        if progress_callback:
            progress_callback({
                "type": "debate_round",
                "round": 1,
                "agent": "Groq (Arquitecto 120B)",
                "status": "Ronda 1: Groq generando propuesta y análisis técnico..."
            })

        groq_sys = f"""Eres el Asistente Técnico y Desarrollador Principal en Windows.
Tu misión es responder de manera útil, directa y sin sobre-complicar:
- Cuentas con herramientas locales y acceso directo al sistema de archivos. NUNCA le pidas al usuario que abra CMD, PowerShell o el explorador para consultar carpetas o archivos.
- Si se ejecutaron herramientas locales o se dispone de datos de directorios o archivos en el contexto, informa al usuario el contenido real encontrado de forma limpia y ordenada.
- Si el usuario pregunta por un archivo (ej: main.py) o por carpetas, responde directamente con lo que existe en el directorio de trabajo activo.
- No des tutoriales obvios de comandos para que el usuario navegue manualmente cuando ya estás operando directamente en el entorno.
{system_tools_info}
Responde en español directamente al usuario."""

        groq_msgs = [{"role": "system", "content": groq_sys}]
        groq_msgs.extend(history_msgs)
        groq_msgs.append({"role": "user", "content": f"{user_query}{tool_context}"})

        groq_proposal = self._call_groq(groq_msgs, model="openai/gpt-oss-120b")
        debate_rounds.append({
            "agent": "Groq (Arquitecto 120B)",
            "badge": "Arquitecto",
            "role": "Ronda 1: Propuesta y Arquitectura",
            "content": groq_proposal
        })

        # RONDA 2: Auditoría y Casos Borde (Gemini o Groq 20B)
        if progress_callback:
            progress_callback({
                "type": "debate_round",
                "round": 2,
                "agent": "Auditor Crítico",
                "status": "Ronda 2: Auditando propuesta, cazando bugs y casos borde..."
            })

        gemini_sys = f"""Eres el Auditor de Software y Casos Borde.
CONTEXTO REAL DEL ENTORNO:
- El asistente cuenta con HERRAMIENTAS REALES en el sistema local de Windows.
- Las consultas a directorios y lecturas de archivos son 100% REALES ejecutadas por herramientas locales.
- NUNCA digas que 'el modelo no puede acceder a archivos' o que 'es una simulación'. El acceso es REAL.
- Tu misión es auditar:
  1. ¿Responde con fidelidad y precisión a lo que el usuario pidió sin inventar ni adelantarse innecesariamente?
  2. Si hay código o scripts, ¿tienen bugs, vulnerabilidades o fallas de lógica?
  3. Señala solo objeciones técnicas breves y mejoras concretas.
Responde en español de forma concisa."""

        tool_note = f"\n\n[DATOS REALES OBTENIDOS DEL SISTEMA]:\n{tool_context}" if tool_context else ""
        auditor_user_prompt = f"### CONSULTA ORIGINAL DEL USUARIO:\n{user_query}{tool_note}\n\n### PROPUESTA DEL ASISTENTE:\n{groq_proposal}\n\nEntrega tu auditoría técnica, objeciones y mejoras concretas:"

        gemini_critique = ""
        gemini_success = False
        if not getattr(self, "_gemini_exhausted", False):
            try:
                gemini_critique = self._call_gemini([
                    {"role": "system", "content": gemini_sys},
                    {"role": "user", "content": auditor_user_prompt}
                ])
                debate_rounds.append({
                    "agent": "Google Gemini (Flash)",
                    "badge": "Auditor Crítico",
                    "role": "Ronda 2: Auditoría, Bugs y Casos Borde",
                    "content": gemini_critique
                })
                gemini_success = True
            except Exception as e:
                err_s = str(e)
                if "429" in err_s or "RESOURCE_EXHAUSTED" in err_s or "quota" in err_s.lower():
                    self._gemini_exhausted = True

        if not gemini_success:
            # Modo Consenso Dual Groq (120B + 20B): Groq 20B audita la propuesta de 120B y redacta el veredicto definitivo
            if progress_callback:
                progress_callback({
                    "type": "debate_round",
                    "round": 2,
                    "agent": "Groq (Auditor 20B)",
                    "status": "Ronda 2: Auditando y consolidando respuesta final con Groq 20B..."
                })

            dual_consensus_sys = f"""Eres el Desarrollador Principal y Auditor de Software hablando DIRECTAMENTE al usuario en el chat.
Tu misión es revisar la propuesta técnica generada por el Arquitecto (Groq 120B), resolver cualquier bug o caso borde y entregar la RESPUESTA FINAL consolidada.

REGLAS ABSOLUTAS:
1. HABLA DIRECTAMENTE AL USUARIO: Habla en primera persona con tono profesional y directo.
2. CERO META-EVALUACIÓN: No generes tablas ni apartados de 'Evaluación', 'Fortalezas' o 'Auditoría'. Entrega la solución final lista para usar.
3. CÓDIGO COMPLETO: Si hay código, entrega la versión funcional, robusta y comentada.
4. NUNCA PIDAS AL USUARIO QUE ABRA CMD O POWERSHELL para listar archivos o navegar cuando ya se dispone de las herramientas del sistema; responde con la información real de los archivos y carpetas.
{system_tools_info}
Responde en español directamente al usuario:"""

            dual_prompt = f"""CONSULTA DEL USUARIO:
{user_query}

{f"DATOS REALES DEL SISTEMA:\n{tool_context}\n" if tool_context else ""}
PROPUESTA DEL ARQUITECTO (Groq 120B):
{groq_proposal}

INSTRUCCIÓN:
Redacta la solución técnica definitiva, consolidada y sin rodeos para el usuario:"""

            try:
                final_consensus = self._call_groq([
                    {"role": "system", "content": dual_consensus_sys},
                    {"role": "user", "content": dual_prompt}
                ], model="llama-3.1-8b-instant", max_tokens=1400)
            except Exception:
                try:
                    final_consensus = self._call_gemini([
                        {"role": "system", "content": dual_consensus_sys},
                        {"role": "user", "content": dual_prompt}
                    ], max_tokens=1400)
                except Exception:
                    final_consensus = groq_proposal

            final_consensus = self._clean_consensus_response(final_consensus)
            debate_rounds.append({
                "agent": "Auditor Cloud",
                "badge": "Veredicto Consensuado",
                "role": "Ronda 2: Auditoría y Consenso Definitivo",
                "content": final_consensus
            })

            self.record_distillation(user_query, debate_rounds, final_consensus)
            return {
                "success": True,
                "final_response": final_consensus,
                "debate_rounds": debate_rounds,
                "consensus": True,
                "tool_events": executed_tool_events
            }

        # RONDA 3: Síntesis y Consenso Definitivo
        if progress_callback:
            progress_callback({
                "type": "debate_round",
                "round": 3,
                "agent": "Consenso Definitivo",
                "status": "Ronda 3: Sintetizando veredicto y solución final pulida..."
            })

        consensus_sys = f"""Eres el Desarrollador y Asistente Principal hablando DIRECTAMENTE al usuario en el chat.
Tu misión es redactar la RESPUESTA FINAL que el usuario va a leer.

REGLAS ABSOLUTAS:
1. HABLA DIRECTAMENTE AL USUARIO: Habla en primera persona ("He accedido a la carpeta...", "Aquí tienes el código...", "Ya verifiqué el directorio...").
2. CERO META-EVALUACIÓN: Está TERMINANTEMENTE PROHIBIDO generar tablas o secciones de 'Evaluación de la propuesta', 'Fortalezas de la propuesta', 'Observaciones críticas', 'Resumen de auditoría' o 'Mejora recomendada'.
3. NO MUESTRES TU RAZONAMIENTO INTERNO: El usuario no debe ver un informe de evaluación de modelos, sino la respuesta final pulida, útil y lista.
4. LAS HERRAMIENTAS SON REALES: Nunca digas que 'no puedes acceder a archivos' o que 'es una simulación'. Las herramientas locales ya inspeccionaron el sistema real.
5. CONCISIÓN Y FIDELIDAD: Si el usuario solo pidió acceder o ver algo, entrega la información clara y concisa sin rodeos ni sermones.

Responde en español directamente al usuario:"""

        consensus_user_prompt = f"""CONSULTA DEL USUARIO:
{user_query}

{f"DATOS REALES DEL SISTEMA (OBTENIDOS POR HERRAMIENTAS):\n{tool_context}\n" if tool_context else ""}
PROPUESTA PREVIA:
{groq_proposal}

OBSERVACIONES DE CALIDAD:
{gemini_critique}

INSTRUCCIÓN:
Escribe ÚNICAMENTE el mensaje final que se mostrará en el chat para el usuario. Sin tablas de meta-evaluación, sin mencionar 'la propuesta' ni 'el auditor'. Solo tu respuesta definitiva lista para leer:"""

        final_consensus = self._call_groq([
            {"role": "system", "content": consensus_sys},
            {"role": "user", "content": consensus_user_prompt}
        ], model="openai/gpt-oss-120b")
        final_consensus = self._clean_consensus_response(final_consensus)
        debate_rounds.append({
            "agent": "Consenso Definitivo",
            "badge": "Veredicto Final",
            "role": "Ronda 3: Síntesis Definitiva",
            "content": final_consensus
        })

        # Registro para auto-entrenamiento / destilación para el modelo local 7B
        self.record_distillation(user_query, debate_rounds, final_consensus)

        return {
            "success": True,
            "final_response": final_consensus,
            "debate_rounds": debate_rounds,
            "consensus": True,
            "tool_events": executed_tool_events
        }

    def record_distillation(self, user_query: str, debate_rounds, final_response: str):
        """
        Almacena el par de entrenamiento sintetizado en formato JSONL
        para destilar el modelo local Qwen 7B (Teacher-Student Dataset).
        """
        sample = {
            "timestamp": time.time(),
            "date": time.strftime("%Y-%m-%d %H:%M:%S"),
            "messages": [
                {"role": "user", "content": user_query},
                {"role": "assistant", "content": final_response}
            ],
            "metadata": {
                "source": "multi_agent_debate_groq_gemini",
                "teacher_models": ["llama-3.3-70b-versatile", "gemini-1.5-flash"]
            }
        }
        try:
            with open(DATASET_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[Error al guardar dataset de destilación: {e}]")
