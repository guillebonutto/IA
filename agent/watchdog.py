"""
Supervisor y Watchdog en Segundo Plano de AURA Core.
Supervisa la salud del hardware, la actividad de los procesos de trading (Bot-08-09)
y analiza logs en busca de errores o alertas críticas.
"""

import os
import sys
import time
import json
import psutil
import threading
from datetime import datetime
from pathlib import Path

class AuraWatchdog:
    def __init__(self, workspace_root=None, bot_dir=None):
        self.workspace_root = workspace_root or str(Path(__file__).resolve().parent.parent)
        self.bot_dir = bot_dir or str(Path(self.workspace_root).parent / "Bot-08-09")
        self.alerts = []
        self.max_alerts = 30
        self.is_running = False
        self.thread = None
        self.lock = threading.Lock()
        self.last_check_time = None
        self.system_health = {}
        self.monitored_processes = []
        self.recent_log_warnings = []

    def start(self):
        """Inicia el bucle de supervisión en segundo plano como daemon thread."""
        if self.is_running:
            return
        self.is_running = True
        self.thread = threading.Thread(target=self._run_loop, daemon=True, name="AuraWatchdog")
        self.thread.start()

    def stop(self):
        self.is_running = False

    def _run_loop(self):
        while self.is_running:
            try:
                self._check_system()
                self._check_processes()
                self._check_bot_logs()
                self.last_check_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            except Exception as e:
                self._add_alert("watchdog", f"Excepción interna en ciclo de supervisión: {str(e)}", "warning")
            time.sleep(12)

    def _add_alert(self, category: str, message: str, level: str = "info"):
        with self.lock:
            alert = {
                "timestamp": datetime.now().strftime("%H:%M:%S"),
                "category": category,
                "message": message,
                "level": level
            }
            # Evitar alertas duplicadas idénticas en ráfaga
            if self.alerts and self.alerts[-1]["message"] == message:
                return
            self.alerts.append(alert)
            if len(self.alerts) > self.max_alerts:
                self.alerts.pop(0)

    def _check_system(self):
        try:
            cpu_pct = psutil.cpu_percent(interval=None)
            mem = psutil.virtual_memory()
            disk = psutil.disk_usage("C:\\")
            self.system_health = {
                "cpu_percent": cpu_pct,
                "ram_percent": mem.percent,
                "ram_used_gb": round(mem.used / (1024**3), 2),
                "ram_total_gb": round(mem.total / (1024**3), 2),
                "disk_free_gb": round(disk.free / (1024**3), 2)
            }
            if cpu_pct > 92.0:
                self._add_alert("hardware", f"Uso elevado de CPU: {cpu_pct}%", "warning")
            if mem.percent > 90.0:
                self._add_alert("hardware", f"Uso crítico de memoria RAM: {mem.percent}%", "warning")
        except Exception:
            pass

    def _check_processes(self):
        TARGET_SCRIPTS = ("main.py", "paper_bot.py", "pibot_terminal.pyw", "llama-server.exe")
        found = []
        try:
            for p in psutil.process_iter(['pid', 'name', 'cmdline', 'cpu_percent', 'memory_info']):
                try:
                    pname = p.info['name'] or ""
                    cmdline = " ".join(p.info['cmdline'] or []).lower()
                    
                    for target in TARGET_SCRIPTS:
                        if target in pname.lower() or target in cmdline:
                            mem_mb = round(p.info['memory_info'].rss / (1024**2), 1) if p.info['memory_info'] else 0
                            found.append({
                                "target": target,
                                "pid": p.info['pid'],
                                "name": pname,
                                "memory_mb": mem_mb
                            })
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        except Exception:
            pass

        self.monitored_processes = found

    def _check_bot_logs(self):
        """Revisa los logs más recientes de Bot-08-09."""
        if not os.path.exists(self.bot_dir):
            return

        logs_dir = os.path.join(self.bot_dir, "logs")
        candidates = []
        if os.path.exists(logs_dir):
            try:
                for f in os.listdir(logs_dir):
                    if f.endswith((".log", ".txt")):
                        fp = os.path.join(logs_dir, f)
                        candidates.append((fp, os.path.getmtime(fp)))
            except Exception:
                pass

        # Si no hay carpeta logs, buscar en la raíz del bot
        if not candidates:
            try:
                for f in os.listdir(self.bot_dir):
                    if f.endswith(".log"):
                        fp = os.path.join(self.bot_dir, f)
                        candidates.append((fp, os.path.getmtime(fp)))
            except Exception:
                pass

        candidates.sort(key=lambda x: x[1], reverse=True)
        warnings_found = []

        # Analizar las últimas 20 líneas de los 2 archivos más recientes
        for fp, _ in candidates[:2]:
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-25:]
                    fname = os.path.basename(fp)
                    for line in lines:
                        l_lower = line.lower()
                        if "error" in l_lower or "exception" in l_lower or "crash" in l_lower:
                            clean_line = line.strip()[:140]
                            warnings_found.append(f"[{fname}] {clean_line}")
                            self._add_alert("trading_bot", f"Incidencia en {fname}: {clean_line}", "error")
            except Exception:
                continue

        self.recent_log_warnings = warnings_found[:8]

    def get_status_report(self) -> dict:
        """Devuelve un diccionario estructurado con el estado general para la UI y la IA."""
        return {
            "online": True,
            "last_check": self.last_check_time,
            "system_health": self.system_health,
            "active_processes": self.monitored_processes,
            "process_count": len(self.monitored_processes),
            "recent_alerts": list(reversed(self.alerts[-10:])),
            "log_warnings": self.recent_log_warnings
        }
