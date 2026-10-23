"""
Generador y Validador de Datasets de Entrenamiento para AURA Core.
Combina:
1. Muestras destiladas de alta calidad (datasets/raw/distillation_dataset.jsonl).
2. Correcciones y feedback explícito del usuario (feedback/feedback_log.jsonl).
3. Casos base de conocimiento técnico de Bot-08-09 y guardarraíles.

Exporta en formatos estándar:
- ShareGPT / ChatML (JSONL) para Unsloth y llama.cpp.
- Alpaca (JSON) para fine-tuning supervisado rápido.
"""

import os
import json
import re
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DISTILL_FILE = BASE_DIR / "datasets" / "raw" / "distillation_dataset.jsonl"
FEEDBACK_FILE = BASE_DIR / "feedback" / "feedback_log.jsonl"

OUT_CHATML = BASE_DIR / "datasets" / "aura_finetune_chatml.jsonl"
OUT_ALPACA = BASE_DIR / "datasets" / "aura_finetune_alpaca.json"

SYSTEM_INSTRUCTION = (
    "Eres AURA, un asistente de programación y trading autónomo local de ultra-alta eficiencia. "
    "Respondes siempre en español de forma directa, técnica y concisa. "
    "Manejas herramientas nativas, gestión de riesgo y arquitectura de bots sin dar rodeos ni meta-comentarios."
)

def clean_text(text: str) -> str:
    if not text:
        return ""
    return text.strip()

def build_dataset():
    print("==========================================================")
    print("   AURA CORE - COMPILADOR Y VALIDADOR DE DATASET LO-RA    ")
    print("==========================================================")

    chatml_records = []
    alpaca_records = []
    seen_prompts = set()

    # 1. Procesar correcciones del usuario (Feedback humano con máxima prioridad)
    feedback_count = 0
    if FEEDBACK_FILE.exists():
        with open(FEEDBACK_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    q = clean_text(entry.get("query", ""))
                    corr = clean_text(entry.get("correction", ""))
                    if q and corr and q.lower() not in seen_prompts:
                        seen_prompts.add(q.lower())
                        feedback_count += 1
                        
                        # Formato ChatML
                        chatml_records.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_INSTRUCTION},
                                {"role": "user", "content": q},
                                {"role": "assistant", "content": corr}
                            ]
                        })

                        # Formato Alpaca
                        alpaca_records.append({
                            "instruction": q,
                            "input": "",
                            "output": corr
                        })
                except Exception:
                    continue

    print(f"[*] Correcciones humanas procesadas (feedback/): {feedback_count}")

    # 2. Procesar pares destilados de debate
    distill_count = 0
    if RAW_DISTILL_FILE.exists():
        with open(RAW_DISTILL_FILE, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                    # Soportar formato messages: [{"role": "user", ...}, {"role": "assistant", ...}]
                    if "messages" in entry and isinstance(entry["messages"], list):
                        u_msg = next((m.get("content", "") for m in entry["messages"] if m.get("role") == "user"), "")
                        a_msg = next((m.get("content", "") for m in entry["messages"] if m.get("role") == "assistant"), "")
                        prompt = clean_text(u_msg)
                        response = clean_text(a_msg)
                    else:
                        prompt = clean_text(entry.get("prompt") or entry.get("instruction") or "")
                        response = clean_text(entry.get("response") or entry.get("output") or "")
                    
                    if not prompt or not response or len(response) < 15:
                        continue
                    
                    # Evitar respuestas meta corruptas en el dataset de entrenamiento
                    if "es un json que representa" in response.lower() or "la respuesta anterior" in response.lower():
                        continue

                    p_norm = prompt.lower()
                    if p_norm not in seen_prompts:
                        seen_prompts.add(p_norm)
                        distill_count += 1

                        chatml_records.append({
                            "messages": [
                                {"role": "system", "content": SYSTEM_INSTRUCTION},
                                {"role": "user", "content": prompt},
                                {"role": "assistant", "content": response}
                            ]
                        })

                        alpaca_records.append({
                            "instruction": prompt,
                            "input": "",
                            "output": response
                        })
                except Exception:
                    continue

    print(f"[*] Pares de destilacion destilados validos: {distill_count}")

    # 3. Inyectar pares fundamentales de conocimiento de Bot-08-09
    CURATED_PAIRS = [
        (
            "¿Cuáles son las 4 estrategias de trading principales de Bot-08-09?",
            "Las 4 estrategias core de Bot-08-09 son:\n1. StrategyStochastic (Tendencia): Cruces de Estocástico a favor de SMA_200 y EMA_20/50.\n2. StrategyStructure (Reversión MSS): Detección de Dobles Techos y Suelos con rompimiento confirmado de Neckline y filtro MACD.\n3. StrategyContinuation (Tendencia): Breakout con fuerza ATR de patrones chartistas de compresión o triángulos.\n4. StrategyFibonacci (Tendencia): Retrocesos al nivel áureo del 61.8% con giro confirmado en velas de rechazo."
        ),
        (
            "¿Cómo gestiona el riesgo Bot-08-09 ante mercados laterales o volátiles?",
            "El bot evalúa el régimen de mercado en cada ciclo: si detecta consolidación (SIDEWAYS) o volatilidad extrema (VOLATILE), entra en un bloqueo absoluto y no emite órdenes para evitar el serrucho de falsos breakouts y slippage. Además, aplica un Lock de Concurrencia (máximo 1 orden abierta por cuenta) y un Daily Stop Loss que pausa la operativa si se alcanza la pérdida máxima de la sesión."
        ),
        (
            "¿Qué se debe hacer si se solicita matar o terminar los procesos de Bot-08-09 o PiBot_Terminal?",
            "Los procesos main.py, paper_bot.py y PiBot_Terminal.pyw están protegidos por guardarraíles de seguridad en AURA. Bajo ninguna circunstancia deben ser cancelados o terminados abruptamente mediante comandos como taskkill o Stop-Process, ya que pueden interrumpir operaciones financieras activas o corromper datos de órdenes."
        ),
        (
            "Accede a bot-08-09 y dime qué carpetas y archivos ves.",
            "Acceso confirmado a la carpeta Bot-08-09. Contiene los siguientes directorios principales:\n- Carpetas: .git, ai_models, assets, backups, bin, binaryoptionstoolsv2, historical_data, logs.\n- Archivos clave: main.py, paper_bot.py, PiBot_Terminal.pyw, config.json y DOCUMENTACION_BOT.md."
        )
    ]

    curated_count = 0
    for q, ans in CURATED_PAIRS:
        if q.lower() not in seen_prompts:
            seen_prompts.add(q.lower())
            curated_count += 1
            chatml_records.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_INSTRUCTION},
                    {"role": "user", "content": q},
                    {"role": "assistant", "content": ans}
                ]
            })
            alpaca_records.append({
                "instruction": q,
                "input": "",
                "output": ans
            })

    print(f"[*] Pares de conocimiento experto inyectados: {curated_count}")

    total_samples = len(chatml_records)
    print(f"\n[+] Total de muestras curadas listas para entrenamiento: {total_samples}")

    # Guardar en JSONL (ChatML)
    with open(OUT_CHATML, "w", encoding="utf-8") as f:
        for r in chatml_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[OK] Guardado ChatML: {OUT_CHATML} ({os.path.getsize(OUT_CHATML) / 1024:.1f} KB)")

    # Guardar en JSON (Alpaca)
    with open(OUT_ALPACA, "w", encoding="utf-8") as f:
        json.dump(alpaca_records, f, ensure_ascii=False, indent=2)
    print(f"[OK] Guardado Alpaca: {OUT_ALPACA} ({os.path.getsize(OUT_ALPACA) / 1024:.1f} KB)")

    print("\n==========================================================")
    print("  ¡DATASET COMPILADO EXITOSAMENTE!")
    print("  Para entrenar tu modelo:")
    print("  1. Abre AURA_Qwen_FineTuning.ipynb en Google Colab.")
    print(f"  2. Sube '{OUT_CHATML.name}' en la pestaña de archivos de Colab.")
    print("  3. Ejecuta las celdas para obtener tu archivo GGUF cuantizado.")
    print("==========================================================")

if __name__ == "__main__":
    build_dataset()
