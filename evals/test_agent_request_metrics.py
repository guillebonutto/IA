"""Pruebas del presupuesto de salida y las métricas por solicitud del agente."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from agent.core import (
    DEFAULT_CHAT_MAX_TOKENS,
    DEFAULT_PROGRAMMING_MAX_TOKENS,
    LocalAgent,
)


class TestAgentRequestMetrics(unittest.TestCase):
    def setUp(self):
        self.agent = LocalAgent()

    @staticmethod
    def model_response(content, finish_reason="stop", usage=None, timings=None):
        return io.BytesIO(json.dumps({
            "choices": [{
                "message": {"content": content},
                "finish_reason": finish_reason,
            }],
            "usage": usage or {"prompt_tokens": 41, "completion_tokens": 13},
            "timings": timings or {
                "prompt_ms": 50.0,
                "predicted_ms": 250.0,
                "predicted_n": 13,
            },
        }).encode("utf-8"))

    @patch("agent.core.urllib.request.urlopen")
    def test_programming_request_gets_configured_budget_and_reports_usage(self, mock_urlopen):
        mock_urlopen.return_value = self.model_response(
            "```python\nprint('incomplete')",
            finish_reason="length",
        )

        response = self.agent.chat_step("Escribe código Python que salude.")

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["max_tokens"], DEFAULT_PROGRAMMING_MAX_TOKENS)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 180)
        self.assertIn("pueden estar incompletos", response)
        metrics = self.agent.get_last_request_metrics()
        self.assertEqual(metrics["model_call_count"], 1)
        self.assertEqual(metrics["prompt_tokens"], 41)
        self.assertEqual(metrics["completion_tokens"], 13)
        self.assertEqual(metrics["model_calls"][0]["finish_reason"], "length")
        self.assertGreaterEqual(metrics["model_calls"][0]["round_trip_seconds"], 0)
        self.assertGreaterEqual(metrics["agent_total_seconds"], 0)
        self.assertEqual(metrics["prompt_eval_seconds"], 0.05)
        self.assertEqual(metrics["generation_seconds"], 0.25)
        self.assertEqual(metrics["generation_tokens_per_second"], 52.0)
        self.assertIsNone(metrics["time_to_first_token_seconds"])

    @patch("agent.core.urllib.request.urlopen")
    def test_normal_request_keeps_small_output_budget(self, mock_urlopen):
        mock_urlopen.return_value = self.model_response("Hola.")

        response = self.agent.chat_step("Hola, ¿cómo estás?")

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["max_tokens"], DEFAULT_CHAT_MAX_TOKENS)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 120)
        self.assertEqual(response, "Hola.")
        self.assertEqual(self.agent.get_last_request_metrics()["model_call_count"], 1)

    @patch("agent.core.urllib.request.urlopen")
    @patch("evals.coding_evaluator.execute_code_test")
    def test_verification_time_and_inference_count_are_reported(
        self, mock_execute, mock_urlopen
    ):
        mock_urlopen.return_value = self.model_response(
            "```python\ndef add(a, b):\n    return a + b\n```"
        )
        mock_execute.return_value = {
            "status": "PASS",
            "passed": True,
            "error": "",
        }
        request = (
            "Implementa en Python una función add.\n\n"
            "Pruebas de aceptación:\n"
            "```python\nassert add(1, 2) == 3\n```"
        )

        response = self.agent.chat_step(request)

        self.assertIn("Código aprobado por las pruebas", response)
        metrics = self.agent.get_last_request_metrics()
        self.assertEqual(metrics["model_call_count"], 1)
        self.assertGreaterEqual(metrics["verification_seconds"], 0)
        mock_execute.assert_called_once()

    def test_programming_token_budget_must_be_within_supported_range(self):
        with self.assertRaises(ValueError):
            LocalAgent(programming_max_tokens=511)
        with self.assertRaises(ValueError):
            LocalAgent(programming_max_tokens=4096)

    @patch("agent.core.urllib.request.urlopen")
    def test_configured_programming_budget_scales_request_timeout(self, mock_urlopen):
        mock_urlopen.return_value = self.model_response("```python\nprint('ok')\n```")
        agent = LocalAgent(programming_max_tokens=2048)

        agent.chat_step("Escribe código Python.")

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["max_tokens"], 2048)
        self.assertEqual(mock_urlopen.call_args.kwargs["timeout"], 331)
        self.assertEqual(
            agent.get_last_request_metrics()["model_calls"][0]["timeout_seconds"],
            331,
        )

    @patch("agent.core.urllib.request.urlopen")
    def test_context_retry_counts_each_http_model_call(self, mock_urlopen):
        http_error = urllib.error.HTTPError(
            "http://127.0.0.1/v1/chat/completions",
            400,
            "Bad Request",
            None,
            io.BytesIO(b"context length exceeded"),
        )
        mock_urlopen.side_effect = [http_error, self.model_response("Hola.")]
        self.agent.history.extend([
            {"role": "user", "content": "Pregunta anterior."},
            {"role": "assistant", "content": "Respuesta previa."},
        ])
        self.agent._request_metrics.set({"model_calls": []})

        try:
            messages = self.agent.history + [{"role": "user", "content": "Hola."}]
            result = self.agent._call_llm(messages)
        finally:
            http_error.close()

        metrics = self.agent.get_last_request_metrics()
        self.assertEqual(mock_urlopen.call_count, 2)
        self.assertEqual(len(metrics["model_calls"]), 2)
        self.assertEqual(metrics["model_calls"][0]["error"], "HTTP 400: Bad Request")
        self.assertEqual(metrics["model_calls"][1]["completion_tokens"], 13)
        self.assertEqual(result["content"], "Hola.")

    @patch("agent.core.urllib.request.urlopen")
    def test_tool_execution_time_is_included_in_request_metrics(self, mock_urlopen):
        tool_response = io.BytesIO(json.dumps({
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "get_system_stats",
                            "arguments": "{}",
                        }
                    }]
                },
                "finish_reason": "tool_calls",
            }],
            "usage": {"prompt_tokens": 20, "completion_tokens": 3},
        }).encode("utf-8"))
        mock_urlopen.side_effect = [
            tool_response,
            self.model_response("CPU y memoria disponibles."),
        ]
        with patch.object(
            self.agent.tools_handler,
            "get_system_stats",
            return_value={"cpu": 2},
        ):
            self.agent.chat_step("Consulta las estadísticas del sistema.")

        metrics = self.agent.get_last_request_metrics()
        self.assertEqual(metrics["model_call_count"], 2)
        self.assertGreaterEqual(metrics["tool_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
