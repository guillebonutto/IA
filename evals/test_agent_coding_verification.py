"""Pruebas unitarias del flujo opcional de verificación de código del agente."""

import unittest
from unittest.mock import Mock, patch

from agent.core import DEFAULT_MAX_CODE_REPAIRS, LocalAgent


PROGRAMMING_REQUEST = """Implementa una función add en Python.

Pruebas de aceptación:
```python
assert add(1, 2) == 3
```
"""

INITIAL_CODE = "```python\ndef add(a, b):\n    return a - b\n```"
REPAIRED_CODE = "```python\ndef add(a, b):\n    return a + b\n```"


class TestAgentCodingVerification(unittest.TestCase):
    def setUp(self):
        self.agent = LocalAgent()
        self.sent_model_messages = []

    @staticmethod
    def llm_response(content):
        return {"is_tool_call": False, "content": content}

    def set_model_responses(self, *responses):
        queued_responses = list(responses)

        def respond(messages, **kwargs):
            self.sent_model_messages.append([dict(message) for message in messages])
            return queued_responses.pop(0)

        self.agent._call_llm = Mock(side_effect=respond)

    def test_verification_summary_preserves_each_failure_cause(self):
        error = (
            "FAIL: test_one (__main__.Tests.test_one)\n"
            "Traceback details omitted\n"
            "AssertionError: expected 1, got 2\n"
            "ERROR: test_two (__main__.Tests.test_two)\n"
            "Traceback details omitted\n"
            "AttributeError: missing public attribute\n"
        )

        status, detail = self.agent._verification_result_summary({
            "status": "FAIL",
            "passed": False,
            "error": error,
        })

        self.assertEqual(status, "FAIL")
        self.assertIn("test_one", detail)
        self.assertIn("AssertionError: expected 1, got 2", detail)
        self.assertIn("test_two", detail)
        self.assertIn("AttributeError: missing public attribute", detail)
        self.assertNotIn("Traceback details", detail)

    @patch("evals.coding_evaluator.execute_code_test")
    def test_code_passing_first_attempt_uses_one_inference(self, mock_execute):
        self.set_model_responses(self.llm_response(REPAIRED_CODE))
        mock_execute.return_value = {"status": "PASS", "passed": True, "error": ""}

        with patch("subprocess.run") as mock_subprocess_run:
            response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("Código aprobado por las pruebas de aceptación", response)
        self.assertEqual(self.agent._call_llm.call_count, 1)
        self.agent._call_llm.assert_called_once()
        self.assertEqual(
            self.agent._call_llm.call_args.kwargs,
            {"retry_count": 1, "allow_tools": False},
        )
        mock_execute.assert_called_once_with(
            "def add(a, b):\n    return a + b",
            "assert add(1, 2) == 3",
        )
        mock_subprocess_run.assert_not_called()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_failed_tests_allow_two_repairs_and_pass_on_the_last_attempt(self, mock_execute):
        self.set_model_responses(
            self.llm_response(INITIAL_CODE),
            self.llm_response(INITIAL_CODE),
            self.llm_response(REPAIRED_CODE),
        )
        mock_execute.side_effect = [
            {"status": "FAIL", "passed": False, "error": "x" * 2500},
            {"status": "FAIL", "passed": False, "error": "second assertion failed"},
            {"status": "PASS", "passed": True, "error": ""},
        ]

        response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("tras 2 reparaciones", response)
        self.assertEqual(self.agent._call_llm.call_count, 3)
        self.assertTrue(all(
            call.kwargs == {"retry_count": 1, "allow_tools": False}
            for call in self.agent._call_llm.call_args_list
        ))
        self.assertEqual(mock_execute.call_count, 3)
        first_repair_prompt = self.sent_model_messages[1][-1]["content"]
        second_repair_prompt = self.sent_model_messages[2][-1]["content"]
        self.assertIn("x" * 1600, first_repair_prompt)
        self.assertNotIn("x" * 1601, first_repair_prompt)
        self.assertIn("second assertion failed", second_repair_prompt)
        self.assertIn(PROGRAMMING_REQUEST.strip(), first_repair_prompt)
        self.assertIn("realmente cruce el límite estricto", first_repair_prompt)

    @patch("evals.coding_evaluator.execute_code_test")
    def test_failed_repairs_stop_at_configured_maximum(self, mock_execute):
        self.set_model_responses(
            self.llm_response(INITIAL_CODE),
            self.llm_response(INITIAL_CODE),
            self.llm_response(INITIAL_CODE),
        )
        mock_execute.return_value = {"status": "FAIL", "passed": False, "error": "assertion failed"}

        response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("Código no verificado", response)
        self.assertIn("2 reparaciones", response)
        self.assertEqual(self.agent._call_llm.call_count, DEFAULT_MAX_CODE_REPAIRS + 1)
        self.assertEqual(mock_execute.call_count, DEFAULT_MAX_CODE_REPAIRS + 1)

    @patch("evals.coding_evaluator.execute_code_test")
    def test_unextractable_repair_uses_remaining_repair_budget(self, mock_execute):
        truncated_repair = "```python\ndef add(a, b):\n    return a + b"
        self.set_model_responses(
            self.llm_response(INITIAL_CODE),
            self.llm_response(truncated_repair),
            self.llm_response(REPAIRED_CODE),
        )
        mock_execute.side_effect = [
            {"status": "FAIL", "passed": False, "error": "assertion failed"},
            {"status": "PASS", "passed": True, "error": ""},
        ]

        response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("Código aprobado por las pruebas de aceptación tras 2 reparaciones", response)
        self.assertEqual(self.agent._call_llm.call_count, 3)
        self.assertEqual(mock_execute.call_count, 2)
        mock_execute.assert_any_call(
            "def add(a, b):\n    return a - b",
            "assert add(1, 2) == 3",
        )
        mock_execute.assert_any_call(
            "def add(a, b):\n    return a + b",
            "assert add(1, 2) == 3",
        )
        second_repair_prompt = self.sent_model_messages[2][-1]["content"]
        self.assertIn("No se pudo extraer código ejecutable", second_repair_prompt)

    @patch("evals.coding_evaluator.execute_code_test")
    def test_zero_repairs_verifies_initial_solution_only(self, mock_execute):
        self.agent = LocalAgent(max_code_repairs=0)
        self.set_model_responses(self.llm_response(INITIAL_CODE))
        mock_execute.return_value = {"status": "FAIL", "passed": False, "error": "assertion failed"}

        response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("Código no verificado", response)
        self.assertEqual(self.agent._call_llm.call_count, 1)
        mock_execute.assert_called_once()

    def test_repair_limit_configuration_is_validated(self):
        for invalid_value in (-1, 3, True, 1.5):
            with self.subTest(value=invalid_value):
                with self.assertRaises(ValueError):
                    LocalAgent(max_code_repairs=invalid_value)

    @patch("evals.coding_evaluator.execute_code_test")
    def test_evaluator_exception_is_observable_and_not_repaired(self, mock_execute):
        self.set_model_responses(self.llm_response(REPAIRED_CODE))
        mock_execute.side_effect = RuntimeError("sandbox bridge unavailable")

        with self.assertLogs("agent.core", level="ERROR"):
            response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("No se pudo verificar", response)
        self.assertIn("sandbox bridge unavailable", response)
        self.agent._call_llm.assert_called_once()
        mock_execute.assert_called_once()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_custom_isolated_evaluator_is_used_for_specialized_acceptance(self, mock_execute):
        self.set_model_responses(self.llm_response(REPAIRED_CODE))
        custom_evaluator = Mock(return_value={
            "status": "PASS",
            "passed": True,
            "error": "",
        })

        response = self.agent._chat_step_with_code_verification(
            "unused for this evaluator",
            evaluator=custom_evaluator,
            source_task="Genera una suite de pruebas.",
        )

        self.assertIn("Código aprobado por las pruebas de aceptación", response)
        custom_evaluator.assert_called_once_with(
            "def add(a, b):\n    return a + b",
            "unused for this evaluator",
        )
        mock_execute.assert_not_called()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_text_tool_call_is_rejected_without_evaluation(self, mock_execute):
        self.set_model_responses(self.llm_response(
            '```json\n{"name":"run_command","arguments":{"command":"python test.py"}}\n```'
        ))

        response = self.agent.chat_step(PROGRAMMING_REQUEST)

        self.assertIn("no devolvió una respuesta de código utilizable", response)
        mock_execute.assert_not_called()
        self.agent._call_llm.assert_called_once()
        self.assertNotIn("<tools>", self.sent_model_messages[0][0]["content"])
        self.assertIn(
            "no hay herramientas disponibles",
            self.sent_model_messages[0][0]["content"],
        )

    def test_rubric_review_repairs_only_after_failed_criteria(self):
        rubric = {
            "required_concepts": [
                ["global interpreter lock", "gil"],
                ["cpu-bound", "cpu bound"],
            ],
            "prohibited_fallacies": ["multiprocessing siempre es mejor"],
            "minimum_word_count": 40,
        }
        initial = "Python threads can be useful for I/O-bound work."
        repaired = (
            "The Global Interpreter Lock (GIL) limits simultaneous Python bytecode "
            "execution across threads. Threads can still be effective for I/O-bound "
            "tasks because they wait on external operations. CPU-bound work may benefit "
            "from multiprocessing, which uses separate processes, but it adds startup, "
            "memory, and inter-process communication costs. The right choice depends on "
            "the workload and data-sharing requirements."
        )
        self.set_model_responses(self.llm_response(initial), self.llm_response(repaired))
        review = Mock(side_effect=[
            {"status": "FAIL", "passed": False, "error": "missing CPU-bound tradeoffs"},
            {"status": "PASS", "passed": True, "error": ""},
        ])

        response = self.agent.chat_step(
            "Explica GIL, threads y multiprocessing.",
            review_criteria=rubric,
            review_evaluator=review,
        )

        self.assertIn("Respuesta aprobada por los criterios explícitos", response)
        self.assertIn(repaired, response)
        self.assertEqual(self.agent._call_llm.call_count, 2)
        self.assertEqual(review.call_count, 2)
        self.assertIn("global interpreter lock", self.sent_model_messages[0][-1]["content"])
        self.assertIn("multiprocessing siempre es mejor", self.sent_model_messages[0][-1]["content"])
        self.assertIn("al menos 40 palabras", self.sent_model_messages[0][-1]["content"])
        self.assertIn("detalle=missing CPU-bound tradeoffs", self.sent_model_messages[1][-1]["content"])
        self.assertTrue(all(
            call.kwargs == {"retry_count": 1, "allow_tools": False}
            for call in self.agent._call_llm.call_args_list
        ))

    def test_rubric_review_stops_after_configured_repair_limit(self):
        self.agent = LocalAgent(max_code_repairs=1)
        self.set_model_responses(
            self.llm_response("Incomplete answer."),
            self.llm_response("Still incomplete."),
        )
        review = Mock(return_value={
            "status": "FAIL",
            "passed": False,
            "error": "missing required concepts",
        })

        response = self.agent.chat_step(
            "Explica un concepto.",
            review_criteria=["incluye el concepto principal"],
            review_evaluator=review,
        )

        self.assertIn("Respuesta no aprobada por la rúbrica", response)
        self.assertIn("1 reparaciones", response)
        self.assertEqual(self.agent._call_llm.call_count, 2)
        self.assertEqual(review.call_count, 2)

    def test_rubric_review_does_not_repair_unknown_evaluator_state(self):
        self.set_model_responses(self.llm_response("A response."))
        review = Mock(return_value={
            "status": "UNKNOWN",
            "passed": False,
            "error": "review unavailable",
        })

        response = self.agent.chat_step(
            "Explica un concepto.",
            review_criteria=["incluye el concepto principal"],
            review_evaluator=review,
        )

        self.assertIn("No se pudo verificar", response)
        self.agent._call_llm.assert_called_once()
        review.assert_called_once()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_request_without_explicit_acceptance_tests_keeps_normal_flow(self, mock_execute):
        self.agent._call_llm = Mock(return_value=self.llm_response("Puedo implementar la función."))

        response = self.agent.chat_step("Implementa una función add en Python.")

        self.assertEqual(response, "Puedo implementar la función.")
        self.agent._call_llm.assert_called_once()
        self.assertEqual(self.agent._call_llm.call_args.kwargs, {})
        mock_execute.assert_not_called()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_blocked_or_unknown_evaluator_status_does_not_repair(self, mock_execute):
        for status in (
            "EXECUTION_BLOCKED_UNSAFE_ENVIRONMENT",
            "ISOLATION_ERROR",
            "UNKNOWN_EVALUATOR_STATE",
        ):
            with self.subTest(status=status):
                self.agent = LocalAgent()
                self.set_model_responses(self.llm_response(REPAIRED_CODE))
                mock_execute.reset_mock()
                mock_execute.return_value = {
                    "status": status,
                    "passed": False,
                    "error": "isolated execution unavailable",
                }

                response = self.agent.chat_step(PROGRAMMING_REQUEST)

                self.assertIn("No se pudo verificar", response)
                self.agent._call_llm.assert_called_once()
                mock_execute.assert_called_once()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_acceptance_section_without_programming_request_does_not_activate(self, mock_execute):
        self.set_model_responses(self.llm_response("La afirmación es correcta."))

        response = self.agent.chat_step(
            "Explica brevemente este concepto.\n\n"
            "Pruebas de aceptación:\n```python\nassert 1 + 1 == 2\n```"
        )

        self.assertEqual(response, "La afirmación es correcta.")
        mock_execute.assert_not_called()
        self.agent._call_llm.assert_called_once()
        self.assertEqual(self.agent._call_llm.call_args.kwargs, {})
        self.assertEqual(
            self.sent_model_messages[0][-1]["content"],
            "Explica brevemente este concepto.\n\n"
            "Pruebas de aceptación:\n```python\nassert 1 + 1 == 2\n```",
        )


if __name__ == "__main__":
    unittest.main()
