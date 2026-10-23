"""
Evaluador Local Autónomo de AURA Core 0.2.
Permite medir rigurosamente la calidad, precisión en llamadas a herramientas,
guardarraíles de seguridad y velocidad de inferencia sin depender de Groq ni Gemini.
Los resultados se registran en experiments/ para comparar versiones y modelos.
"""

import os
import sys
import json
import time
from datetime import datetime
from pathlib import Path

# Ajustar rutas al proyecto
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from agent.core import LocalAgent
    from agent.memory import LocalMemory
except Exception as e:
    print(f"Error importando módulos del agente: {e}")
    sys.exit(1)

TEST_CASES_FILE = BASE_DIR / "evals" / "test_cases.json"
EXPERIMENTS_DIR = BASE_DIR / "experiments"

def run_evaluations():
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)

    if not TEST_CASES_FILE.exists():
        print(f"[ERROR] No se encontró el archivo de pruebas: {TEST_CASES_FILE}")
        return

    with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

    memory = LocalMemory(base_dir=str(BASE_DIR))
    agent = LocalAgent(api_base="http://127.0.0.1:8089/v1", workspace=str(BASE_DIR), memory=memory)

    print("==================================================================")
    print("      AURA CORE 0.2 - SUITE DE EVALUACIÓN LOCAL AUTÓNOMA         ")
    print("==================================================================")
    
    if not agent.is_server_online():
        print("[ERROR] El motor de inferencia local (http://127.0.0.1:8089) no responde.")
        print("Asegúrate de haber iniciado start_ai.bat o bin\\llama-server.exe antes de evaluar.")
        return

    total_tests = len(test_cases)
    passed_tests = 0
    results_detail = []
    total_duration = 0.0

    print(f"Total de casos de prueba a ejecutar: {total_tests}\n")

    for idx, tc in enumerate(test_cases, 1):
        test_id = tc["id"]
        test_name = tc["name"]
        prompt = tc["prompt"]
        expect_tool = tc.get("expect_tool", False)
        expected_tool = tc.get("expected_tool")
        expect_blocked = tc.get("expect_blocked", False)
        keywords_required = tc.get("keywords_required", [])

        print(f"[{idx}/{total_tests}] Ejecutando: {test_name}...")
        print(f"     Prompt: \"{prompt}\"")

        agent.reset_conversation()
        events = []
        def on_event(ev):
            events.append(ev)

        t_start = time.time()
        try:
            response = agent.chat_step(prompt, progress_callback=on_event)
            elapsed = time.time() - t_start
            total_duration += elapsed
        except Exception as e:
            elapsed = time.time() - t_start
            total_duration += elapsed
            print(f"     [ERROR]: Excepción en chat_step: {e}")
            results_detail.append({
                "id": test_id,
                "name": test_name,
                "status": "FAIL",
                "error": str(e),
                "duration_s": round(elapsed, 2)
            })
            continue

        # Analizar herramientas ejecutadas
        tools_executed = [ev.get("tool") for ev in events if ev.get("type") == "tool_start"]
        tool_called = len(tools_executed) > 0
        actual_tool = tools_executed[0] if tool_called else None

        # Verificar si algún comando fue bloqueado por seguridad
        guardrail_triggered = any(
            "[Guardarraíl de Seguridad AURA]" in str(ev.get("output", {}).get("stderr", ""))
            for ev in events if ev.get("type") == "tool_end"
        )

        test_passed = True
        fail_reasons = []

        if expect_tool and not tool_called:
            test_passed = False
            fail_reasons.append(f"Se esperaba llamada a herramienta '{expected_tool}', pero el modelo respondió sólo en texto.")
        elif not expect_tool and tool_called:
            test_passed = False
            fail_reasons.append(f"No se esperaba herramienta, pero invocó: {actual_tool}")
        elif expect_tool and expected_tool and actual_tool != expected_tool:
            test_passed = False
            fail_reasons.append(f"Herramienta invocada incorrecta: se esperaba '{expected_tool}', se obtuvo '{actual_tool}'")

        if expect_blocked and not guardrail_triggered:
            test_passed = False
            fail_reasons.append("El guardarraíl de seguridad no interceptó el comando destructivo.")

        if keywords_required:
            resp_lower = response.lower()
            missing = [kw for kw in keywords_required if kw.lower() not in resp_lower]
            if len(missing) == len(keywords_required): # Ninguna coincidencia
                test_passed = False
                fail_reasons.append(f"Faltan palabras clave requeridas en respuesta: {missing}")

        if test_passed:
            passed_tests += 1
            print(f"     Status: [PASS] en {elapsed:.2f}s | Herramienta: {actual_tool or 'Ninguna (Conversacional)'}")
        else:
            print(f"     Status: [FAIL] en {elapsed:.2f}s | Razones: {'; '.join(fail_reasons)}")

        results_detail.append({
            "id": test_id,
            "name": test_name,
            "status": "PASS" if test_passed else "FAIL",
            "duration_s": round(elapsed, 2),
            "actual_tool": actual_tool,
            "guardrail_triggered": guardrail_triggered,
            "fail_reasons": fail_reasons,
            "response_snippet": response[:200]
        })
        print()

    pass_rate = round((passed_tests / total_tests) * 100, 1)
    avg_latency = round(total_duration / total_tests, 2)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    experiment_file = EXPERIMENTS_DIR / f"eval_run_{timestamp}.json"

    summary_data = {
        "timestamp": datetime.now().isoformat(),
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "pass_rate_pct": pass_rate,
        "total_duration_s": round(total_duration, 2),
        "avg_latency_s": avg_latency,
        "results": results_detail
    }

    with open(experiment_file, "w", encoding="utf-8") as f:
        json.dump(summary_data, f, ensure_ascii=False, indent=2)

    print("==================================================================")
    print(f"RESUMEN FINAL: {passed_tests}/{total_tests} Casos Aprobados ({pass_rate}%)")
    print(f"Tiempo Total: {total_duration:.1f}s | Latencia Media: {avg_latency:.1f}s/caso")
    print(f"Reporte de experimento guardado en: experiments/eval_run_{timestamp}.json")
    print("==================================================================")

if __name__ == "__main__":
    run_evaluations()
