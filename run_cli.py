"""
Cliente de Terminal Interactivo para AURA CORE.
Permite chatear y ordenar tareas a la IA directamente desde PowerShell o CMD.
"""

import sys
import os
import json
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from agent.core import LocalAgent

def main():
    print("=" * 60)
    print("  AURA CORE - AGENTE LOCAL ZERO-BLOAT (MODO TERMINAL)")
    print("=" * 60)
    print("Conectando con el motor local (llama-server:8085)...")

    agent = LocalAgent(api_base="http://127.0.0.1:8085/v1", workspace=BASE_DIR)
    
    if not agent.is_server_online():
        print("[!] AVISO: llama-server no parece estar activo en el puerto 8085.")
        print("    Asegúrate de haber iniciado 'start_ai.bat' o 'llama-server.exe'.")
        print("-" * 60)
    else:
        print("[✓] Conexión establecida con el motor local.")
        print("-" * 60)

    print("Escribe tu instrucción o comando para la IA ('salir' para terminar):\n")

    def print_progress(event):
        if event.type == "tool_start":
            print(f"\n  [EJECUTANDO HERRAMIENTA]: {event['tool']} -> {json.dumps(event.get('args', {}), ensure_ascii=False)}")
        elif event.type == "tool_end":
            out = event.get("output", {})
            if isinstance(out, dict) and "stdout" in out and out["stdout"]:
                lines = out["stdout"].split("\n")[:3]
                print(f"  [SALIDA]: {' | '.join(lines)}")
            else:
                print(f"  [COMPLETADO]")

    while True:
        try:
            prompt = input("\nTÚ > ").strip()
            if not prompt:
                continue
            if prompt.lower() in ["salir", "exit", "quit"]:
                print("Hasta luego.")
                break

            print("\nIA > Pensando...", end="", flush=True)
            res = agent.chat_step(prompt, progress_callback=print_progress)
            print(f"\rIA > {res}\n")

        except KeyboardInterrupt:
            print("\nOperación cancelada.")
            break
        except Exception as e:
            print(f"\nError: {e}")

if __name__ == "__main__":
    main()
