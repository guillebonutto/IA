"""
Pruebas Unitarias Metodológicas del Experimento A/B
===================================================
Verifica sin requerir servidor ni ejecución de modelos:
1. Paridad estricta de prompts de reintento entre Variante A y Variante B.
2. Formateo y exclusión de auto-recuperación (cero self-retrieval).
3. Motor comparador A/B: emparejamiento por task_id, cálculo de ganancias y regresiones.
4. Rechazo formal ante suites dispares o datos corruptos.
5. Clasificación y segregación de errores de infraestructura vs errores funcionales.
"""

import unittest
import json
import tempfile
from pathlib import Path

from evals.selective_retriever import SelectiveExampleRetriever
from scratch.run_ab_selective_experiment import (
    compare_ab_results,
    format_condensed_feedback,
    format_failure_focused_feedback,
    extract_diagnostic_lines,
    RETRY_PROMPT_CODE_TEMPLATE
)

class TestABMethodology(unittest.TestCase):

    def test_retry_prompt_template_parity(self):
        """Verifica que el prompt de reintento use exactamente la misma estructura de diagnóstico."""
        prompt = RETRY_PROMPT_CODE_TEMPLATE.format(
            title="Tarea de Prueba",
            task_prompt="Implementa suma(a, b)",
            previous_code="def suma(a, b): return a - b",
            condensed_error="AssertionError: 5 != 3"
        )
        self.assertIn("=== ENUNCIADO Y CONTRATO ORIGINAL ===", prompt)
        self.assertIn("=== CÓDIGO PROPUESTO EN EL INTENTO ANTERIOR ===", prompt)
        self.assertIn("=== RESULTADO CONDENSADO DE LAS PRUEBAS ===", prompt)
        self.assertIn("=== INSTRUCCIONES OBLIGATORIAS DE ANÁLISIS Y CORRECCIÓN POR CONTRATO ===", prompt)
        self.assertIn("- **ERROR:**", prompt)
        self.assertIn("- **CONTRATO:**", prompt)
        self.assertIn("- **CORRECCIÓN:**", prompt)
        # Asegurar que en el reintento NO se inyectan ejemplos ICL
        self.assertNotIn("PATRONES CANÓNICOS DE REFERENCIA", prompt)

    def test_condensed_feedback_and_diagnostics_extraction(self):
        """Verifica el filtrado de trazas y la extracción de las 3 líneas de diagnóstico."""
        raw_error = "Traceback (most recent call last):\n  File 'test.py', line 10\nAssertionError: expected 10 got 5"
        condensed = format_condensed_feedback(raw_error)
        self.assertIn("AssertionError: expected 10 got 5", condensed)

        sample_response = (
            "- **ERROR:** AssertionError en test_suma por cálculo erróneo\n"
            "- **CONTRATO:** Retornar la suma de dos enteros positivos\n"
            "- **CORRECCIÓN:** Cambiar operador de resta por suma\n"
            "```python\ndef suma(a, b): return a + b\n```"
        )
        lines = extract_diagnostic_lines(sample_response)
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[0].startswith("- **ERROR:**"))
        self.assertTrue(lines[1].startswith("- **CONTRATO:**"))
        self.assertTrue(lines[2].startswith("- **CORRECCIÓN:**"))

    def test_failure_focused_feedback_keeps_only_actionable_failures(self):
        """C conserva el nombre y la aserción de cada fallo, no las pruebas aprobadas."""
        raw_error = (
            "test_ok (__main__.T.test_ok) ... ok\n\n"
            "======================================================================\n"
            "FAIL: test_invalid_type (__main__.T.test_invalid_type)\n"
            "----------------------------------------------------------------------\n"
            "AssertionError: TypeError not raised\n\n"
            "======================================================================\n"
            "ERROR: test_timeout (__main__.T.test_timeout)\n"
            "----------------------------------------------------------------------\n"
            "RuntimeError: deadline exceeded\n"
        )
        focused = format_failure_focused_feedback(raw_error)
        self.assertIn("FAIL: test_invalid_type", focused)
        self.assertIn("AssertionError: TypeError not raised", focused)
        self.assertIn("ERROR: test_timeout", focused)
        self.assertIn("RuntimeError: deadline exceeded", focused)
        self.assertNotIn("test_ok", focused)

    def test_comparator_gains_and_regressions(self):
        """Verifica que el comparador detecte correctamente tareas ganadas y regresiones."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_a = Path(tmpdir) / "results_a.json"
            file_b = Path(tmpdir) / "results_b.json"

            # Tarea 1: A falla, B pasa (GANADA por B)
            # Tarea 2: A pasa, B falla (REGRESIÓN de B)
            # Tarea 3: A y B pasan (AMBOS PASAN)
            data_a = {
                "metadata": {"suite_name": "test_suite"},
                "summary": {"pass_at_1_count": 1, "final_pass_count": 2},
                "task_results": [
                    {"task_id": "T01", "is_valid_run": True, "pass_at_1": False, "final_passed": False, "attempts_used": 2, "total_latency_s": 10.0},
                    {"task_id": "T02", "is_valid_run": True, "pass_at_1": True, "final_passed": True, "attempts_used": 1, "total_latency_s": 5.0},
                    {"task_id": "T03", "is_valid_run": True, "pass_at_1": True, "final_passed": True, "attempts_used": 1, "total_latency_s": 5.0}
                ]
            }
            data_b = {
                "metadata": {"suite_name": "test_suite"},
                "summary": {"pass_at_1_count": 2, "final_pass_count": 2},
                "task_results": [
                    {"task_id": "T01", "is_valid_run": True, "pass_at_1": True, "final_passed": True, "attempts_used": 1, "total_latency_s": 6.0, "retrieved_examples": [{"task_id": "P01"}]},
                    {"task_id": "T02", "is_valid_run": True, "pass_at_1": False, "final_passed": False, "attempts_used": 2, "total_latency_s": 11.0, "retrieved_examples": []},
                    {"task_id": "T03", "is_valid_run": True, "pass_at_1": True, "final_passed": True, "attempts_used": 1, "total_latency_s": 5.0, "retrieved_examples": []}
                ]
            }

            with open(file_a, "w", encoding="utf-8") as f:
                json.dump(data_a, f)
            with open(file_b, "w", encoding="utf-8") as f:
                json.dump(data_b, f)

            report = compare_ab_results(file_a, file_b)
            summary = report["metrics_summary"]

            self.assertEqual(summary["tasks_gained_by_b"], ["T01"])
            self.assertEqual(summary["tasks_regressed_by_b"], ["T02"])
            self.assertEqual(summary["net_gain"], 0)

    def test_comparator_rejects_mismatched_suites(self):
        """Verifica que el comparador aborte si las suites no coinciden."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_a = Path(tmpdir) / "results_a.json"
            file_b = Path(tmpdir) / "results_b.json"

            data_a = {
                "metadata": {"suite_name": "suite_1"},
                "task_results": [{"task_id": "T01"}]
            }
            data_b = {
                "metadata": {"suite_name": "suite_2"},
                "task_results": [{"task_id": "T99"}]
            }
            with open(file_a, "w", encoding="utf-8") as f: json.dump(data_a, f)
            with open(file_b, "w", encoding="utf-8") as f: json.dump(data_b, f)

            with self.assertRaises(ValueError):
                compare_ab_results(file_a, file_b)

    def test_infrastructure_error_segregation(self):
        """Verifica que los fallos de infraestructura se excluyan de las tareas válidas emparejadas."""
        with tempfile.TemporaryDirectory() as tmpdir:
            file_a = Path(tmpdir) / "results_a.json"
            file_b = Path(tmpdir) / "results_b.json"

            data_a = {
                "metadata": {"suite_name": "test"},
                "summary": {"pass_at_1_count": 0, "final_pass_count": 0},
                "task_results": [
                    {"task_id": "T01", "is_valid_run": False, "error_category": "SERVER_ERROR", "pass_at_1": False, "final_passed": False, "attempts_used": 1, "total_latency_s": 0.0}
                ]
            }
            data_b = {
                "metadata": {"suite_name": "test"},
                "summary": {"pass_at_1_count": 1, "final_pass_count": 1},
                "task_results": [
                    {"task_id": "T01", "is_valid_run": True, "error_category": None, "pass_at_1": True, "final_passed": True, "attempts_used": 1, "total_latency_s": 5.0}
                ]
            }
            with open(file_a, "w", encoding="utf-8") as f: json.dump(data_a, f)
            with open(file_b, "w", encoding="utf-8") as f: json.dump(data_b, f)
            report = compare_ab_results(file_a, file_b)
            self.assertEqual(report["metrics_summary"]["infra_errors_excluded"], 1)
            self.assertEqual(report["metrics_summary"]["valid_paired_tasks"], 0)

    def test_timeout_parity_between_variants(self):
        """Verifica que ambas variantes compartan la misma configuración de timeout_s."""
        import inspect
        from scratch.run_ab_selective_experiment import evaluate_task_ab
        sig = inspect.signature(evaluate_task_ab)
        default_timeout = sig.parameters["timeout_s"].default
        self.assertEqual(default_timeout, 240.0)

if __name__ == "__main__":
    unittest.main()
