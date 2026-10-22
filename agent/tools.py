"""
Herramientas nativas del Agente Local Ultra-Optimizado.
Cero dependencias pesadas: utiliza la biblioteca estándar de Python y comandos de sistema.
"""

import os
import sys
import subprocess
import glob
import json
import urllib.request
import urllib.parse
import re
import platform
import shutil
from pathlib import Path

class AgentTools:
    def __init__(self, workspace_root=None):
        self.workspace_root = workspace_root or os.getcwd()
        self.current_dir = None

    def _resolve_path(self, path: str) -> str:
        """
        Resuelve rutas relativas o nombres de carpetas de forma inteligente:
        1. Si path es '.' o vacío, devuelve current_dir si está fijado, sino workspace_root.
        2. Si es ruta absoluta existente, la devuelve directamente.
        3. Si existe relativa a current_dir (última carpeta navegada), la devuelve.
        4. Si existe relativa a workspace_root (IA), la devuelve.
        5. Si existe en la carpeta padre (ej: Downloads), la devuelve.
        6. Búsqueda insensible a mayúsculas/minúsculas en carpetas navegadas, workspace o padre.
        """
        if not path or path.strip() in (".", ""):
            return self.current_dir or self.workspace_root

        clean_path = path.strip().strip("'\"")
        base = os.path.basename(clean_path).lower()

        # Placeholders genéricos del modelo (ej: /path/to/directory)
        if "path/to" in clean_path.lower() or base in ("directory", "folder", "directorio", "carpeta", "path"):
            return self.current_dir or self.workspace_root

        # Alias comunes para el workspace del usuario
        if clean_path.lower() in ("ia", "workspace", "root", "raiz", "raíz"):
            return self.workspace_root

        # 1. Ruta absoluta
        if os.path.isabs(clean_path):
            if os.path.exists(clean_path):
                return clean_path
            # Búsqueda insensible a mayúsculas en el directorio contenedor de la ruta
            parent = os.path.dirname(clean_path)
            if os.path.exists(parent):
                for item in os.listdir(parent):
                    if item.lower() == base:
                        return os.path.join(parent, item)
            grandparent = os.path.dirname(parent)
            if grandparent and os.path.exists(grandparent):
                for item in os.listdir(grandparent):
                    if item.lower() == base:
                        return os.path.join(grandparent, item)

        # 2. Probar ruta directa en current_dir, workspace_root o parent_dir
        for root in [self.current_dir, self.workspace_root, self.parent_dir]:
            if root and os.path.exists(root):
                candidate = os.path.join(root, clean_path)
                if os.path.exists(candidate):
                    return candidate

        # 3. Búsqueda inteligente por nombre insensible a mayúsculas y signos
        found = (
            self._find_in_dir(self.current_dir, clean_path) or
            self._find_in_dir(self.workspace_root, clean_path) or
            self._find_in_dir(self.parent_dir, clean_path) or
            self._find_in_dir(self.current_dir, base) or
            self._find_in_dir(self.workspace_root, base) or
            self._find_in_dir(self.parent_dir, base)
        )
        if found:
            return found

        return clean_path

    def _find_in_dir(self, directory: str, query: str, check_subdirs: bool = True) -> str:
        """Busca un archivo o carpeta en un directorio tolerando mayúsculas, signos y errores de extensión (ej: .ñy -> .py)."""
        if not directory or not os.path.exists(directory):
            return None
        clean = query.strip().strip("'\"")
        # Corrección de errores típicos de teclado español (.ñy -> .py, .pt -> .py)
        clean = re.sub(r'\.ñy$', '.py', clean, flags=re.IGNORECASE)
        clean = re.sub(r'\.pt$', '.py', clean, flags=re.IGNORECASE)
        clean = re.sub(r'^\.+([a-zA-Z0-9_\-]+)', r'\1', clean)

        base = os.path.basename(clean).lower()
        stem = os.path.splitext(base)[0].lower()
        norm_query = re.sub(r'[^a-zA-Z0-9]', '', base)
        norm_stem = re.sub(r'[^a-zA-Z0-9]', '', stem)

        try:
            items = os.listdir(directory)
        except Exception:
            return None

        # 1. Coincidencia exacta insensible a mayúsculas
        for item in items:
            if item.lower() == base:
                return os.path.join(directory, item)

        # 2. Coincidencia normalizada sin puntuación ni guiones
        if norm_query:
            for item in items:
                norm_item = re.sub(r'[^a-zA-Z0-9]', '', item.lower())
                if norm_item == norm_query:
                    return os.path.join(directory, item)

        # 3. Coincidencia por raíz (stem) ignorando extensión
        if norm_stem and len(norm_stem) >= 3:
            for item in items:
                item_stem = os.path.splitext(item)[0].lower()
                norm_item_stem = re.sub(r'[^a-zA-Z0-9]', '', item_stem)
                if norm_item_stem == norm_stem:
                    return os.path.join(directory, item)

        # 4. Coincidencia de subcadena única si es código
        if len(norm_stem) >= 4:
            candidates = [item for item in items if norm_stem in re.sub(r'[^a-zA-Z0-9]', '', item.lower())]
            if len(candidates) == 1:
                return os.path.join(directory, candidates[0])

        # 5. Búsqueda en subdirectorios inmediatos (1 nivel)
        if check_subdirs:
            for item in items:
                sub_path = os.path.join(directory, item)
                if os.path.isdir(sub_path) and not item.startswith("."):
                    found = self._find_in_dir(sub_path, query, check_subdirs=False)
                    if found:
                        return found

        return None

    def _resolve_path(self, path: str) -> str:
        """
        Resuelve rutas relativas o nombres de carpetas de forma inteligente:
        1. Si path es '.' o vacío, devuelve current_dir si está fijado, sino workspace_root.
        2. Si es ruta absoluta existente, la devuelve directamente.
        3. Busca con tolerancia a fallos tipográficos y de extensión en:
           a) current_dir (última carpeta navegada)
           b) workspace_root (IA)
           c) carpeta padre (ej: Downloads)
        """
        if not path or path.strip() in (".", ""):
            return self.current_dir or self.workspace_root

        clean_path = path.strip().strip("'\"")

        # 1. Ruta absoluta
        if os.path.isabs(clean_path):
            if os.path.exists(clean_path):
                return clean_path
            parent = os.path.dirname(clean_path)
            found = self._find_in_dir(parent, os.path.basename(clean_path))
            if found:
                return found
            grandparent = os.path.dirname(parent)
            found_gp = self._find_in_dir(grandparent, os.path.basename(clean_path))
            if found_gp:
                return found_gp
            return clean_path

        # 2. Búsqueda en el directorio actualmente navegado (si hay uno activo)
        if self.current_dir:
            found_curr = self._find_in_dir(self.current_dir, clean_path)
            if found_curr:
                return found_curr

        # 3. Búsqueda en el workspace actual
        found_ws = self._find_in_dir(self.workspace_root, clean_path)
        if found_ws:
            return found_ws

        # 4. Búsqueda en el directorio padre (proyectos hermanos: ../)
        parent_dir = os.path.dirname(self.workspace_root)
        found_parent = self._find_in_dir(parent_dir, clean_path)
        if found_parent:
            return found_parent

        candidate = os.path.abspath(os.path.join(self.workspace_root, clean_path))
        return candidate

    def run_command(self, command: str, cwd: str = None, timeout: int = 45) -> dict:
        """Ejecuta un comando en PowerShell de manera controlada y segura."""
        work_dir = self._resolve_path(cwd) if cwd else self.workspace_root
        clean_cmd = command.strip()

        # Desenvolver llamadas redundantes a powershell si el comando ya incluye el prefijo
        ps_unwrap = re.match(r"^powershell(?:\.exe)?\s+(?:-Command\s+)?[\"']?(.*)[\"']?$", clean_cmd, re.IGNORECASE | re.DOTALL)
        if ps_unwrap and len(ps_unwrap.group(1).strip()) > 3:
            clean_cmd = ps_unwrap.group(1).strip()
            if (clean_cmd.startswith('"') and clean_cmd.endswith('"')) or (clean_cmd.startswith("'") and clean_cmd.endswith("'")):
                clean_cmd = clean_cmd[1:-1].strip()

        try:
            process = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", clean_cmd],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace"
            )
            stdout = process.stdout.strip()
            stderr = process.stderr.strip()

            # Limitar salida para no saturar la ventana de contexto
            if len(stdout) > 4000:
                stdout = stdout[:4000] + "\n... [Salida truncada]"
            if len(stderr) > 2000:
                stderr = stderr[:2000] + "\n... [Errores truncados]"

            return {
                "exit_code": process.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "success": process.returncode == 0
            }
        except subprocess.TimeoutExpired:
            return {"exit_code": -1, "stdout": "", "stderr": f"Tiempo de espera agotado ({timeout}s).", "success": False}
        except Exception as e:
            return {"exit_code": -1, "stdout": "", "stderr": str(e), "success": False}

    def read_file(self, file_path: str, start_line: int = 1, max_lines: int = 300) -> dict:
        """Lee el contenido de un archivo local de forma paginada."""
        resolved = self._resolve_path(file_path)
        if not os.path.exists(resolved):
            return {"error": f"El archivo '{file_path}' no existe.", "content": None}
        if os.path.isdir(resolved):
            # Si el modelo o usuario pidió leer una carpeta, listar su contenido automáticamente
            return self.list_directory(resolved)

        try:
            with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
            
            total_lines = len(lines)
            start_idx = max(0, start_line - 1)
            end_idx = min(total_lines, start_idx + max_lines)
            
            selected = lines[start_idx:end_idx]
            numbered = [f"{i + 1:4d} | {line}" for i, line in enumerate(selected, start=start_idx)]
            
            return {
                "path": resolved,
                "total_lines": total_lines,
                "showing_range": f"{start_idx + 1}-{end_idx}",
                "content": "".join(numbered)
            }
        except Exception as e:
            return {"error": f"Error al leer archivo: {str(e)}", "content": None}

    def write_file(self, file_path: str, content: str, mode: str = "w") -> dict:
        """Crea o modifica un archivo local asegurando directorios padres."""
        resolved = self._resolve_path(file_path)
        try:
            os.makedirs(os.path.dirname(resolved), exist_ok=True)
            with open(resolved, mode, encoding="utf-8") as f:
                f.write(content)
            return {"path": resolved, "bytes_written": len(content.encode("utf-8")), "success": True}
        except Exception as e:
            return {"error": f"Error al escribir archivo: {str(e)}", "success": False}

    def list_directory(self, dir_path: str = ".", max_items: int = 35) -> dict:
        """Lista archivos y subdirectorios de una ruta priorizando código y scripts."""
        resolved = self._resolve_path(dir_path)
        if not os.path.exists(resolved):
            return {"error": f"La ruta '{dir_path}' no existe."}
        
        if os.path.isdir(resolved):
            self.current_dir = resolved

        try:
            all_items = os.listdir(resolved)
            dirs = sorted([i for i in all_items if os.path.isdir(os.path.join(resolved, i))])
            files = [i for i in all_items if os.path.isfile(os.path.join(resolved, i))]
            
            CODE_EXTS = (
                '.py', '.pyw', '.js', '.ts', '.jsx', '.tsx', '.json',
                '.html', '.css', '.bat', '.ps1', '.sh', '.cpp', '.c',
                '.h', '.rs', '.go', '.java', '.md', '.txt', '.toml',
                '.yaml', '.yml', '.env', '.ini', '.cfg'
            )
            
            code_files = [f for f in files if f.lower().endswith(CODE_EXTS)]
            other_files = [f for f in files if not f.lower().endswith(CODE_EXTS)]
            
            ENTRY_KEYS = ('terminal', 'main', 'run', 'bot', 'app', 'start', 'server', 'index')
            code_files.sort(key=lambda x: (
                0 if any(k in x.lower() for k in ENTRY_KEYS) else 1,
                x.lower()
            ))
            
            sample_files = code_files[:25] + other_files[:max(5, 30 - len(code_files[:25]))]
            
            return {
                "path": resolved,
                "exists": True,
                "total_items": len(all_items),
                "directories": dirs[:15],
                "files": sample_files,
                "files_sample": sample_files,
                "code_files": code_files[:25],
                "total_code_files": len(code_files),
                "total_directories": len(dirs),
                "has_more": len(all_items) > len(sample_files)
            }
        except Exception as e:
            return {"error": str(e)}

    def search_files(self, pattern: str, root_path: str = ".") -> dict:
        """Busca archivos por patrón de nombre (glob)."""
        resolved = self._resolve_path(root_path)
        matches = []
        try:
            for root, _, files in os.walk(resolved):
                for f in files:
                    if pattern.lower() in f.lower() or glob.fnmatch.fnmatch(f.lower(), pattern.lower()):
                        rel = os.path.relpath(os.path.join(root, f), resolved)
                        matches.append(rel)
                        if len(matches) >= 50:
                            break
                if len(matches) >= 50:
                    break
            return {"pattern": pattern, "root_path": resolved, "matches_count": len(matches), "matches": matches}
        except Exception as e:
            return {"error": str(e)}

    def get_system_stats(self) -> dict:
        """Obtiene métricas en tiempo real de CPU, RAM y disco sin dependencias pesadas."""
        stats = {
            "os": platform.platform(),
            "python": platform.python_version(),
            "cpu_cores": os.cpu_count()
        }
        # Espacio en disco
        try:
            total, used, free = shutil.disk_usage(self.workspace_root)
            stats["disk_total_gb"] = round(total / (1024**3), 2)
            stats["disk_used_gb"] = round(used / (1024**3), 2)
            stats["disk_free_gb"] = round(free / (1024**3), 2)
        except Exception:
            pass
        return stats

    def get_tools_declarations(self) -> list:
        """Retorna las definiciones de herramientas para el modelo (compatible con function calling)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "run_command",
                    "description": "Ejecuta comandos de PowerShell en Windows para compilar código, instalar paquetes, consultar git, etc.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Comando exacto de PowerShell a ejecutar."}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "read_file",
                    "description": "Lee el código o texto de un archivo específico (ej: main.py). No la uses para directorios o carpetas.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Ruta relativa o absoluta al archivo a leer."},
                            "start_line": {"type": "integer", "description": "Línea de inicio opcional (1 por defecto)."}
                        },
                        "required": ["file_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "write_file",
                    "description": "Crea o sobrescribe un archivo en el disco con código o texto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "file_path": {"type": "string", "description": "Ruta del archivo a escribir."},
                            "content": {"type": "string", "description": "Contenido completo a escribir en el archivo."}
                        },
                        "required": ["file_path", "content"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_directory",
                    "description": "Lista los archivos y subcarpetas dentro de una carpeta o directorio. Úsala siempre que el usuario pida acceder, explorar o ver el contenido de una carpeta o proyecto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "dir_path": {"type": "string", "description": "Nombre o ruta de la carpeta a listar (ej: 'bot-08-09' o '.')."}
                        },
                        "required": ["dir_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_files",
                    "description": "Busca archivos en el proyecto por nombre o extensión.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string", "description": "Patrón de búsqueda (ej. '*.py', 'main', 'config*')."}
                        },
                        "required": ["pattern"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_stats",
                    "description": "Consulta el estado del sistema: CPU, RAM y espacio en disco.",
                    "parameters": {
                        "type": "object",
                        "properties": {}
                    }
                }
            }
        ]
