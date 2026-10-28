"""Pruebas del contexto acotado para solicitudes de programación."""

import unittest
from unittest.mock import Mock, patch

from agent.core import LocalAgent, PROGRAMMING_TASK_GUIDANCE


class TestAgentProgrammingGuidance(unittest.TestCase):
    def setUp(self):
        self.agent = LocalAgent()
        self.sent_messages = []
        self.agent._call_llm = Mock(side_effect=self.respond)

    def respond(self, messages, **kwargs):
        return self.respond_with("Respuesta de prueba", messages, **kwargs)

    def respond_with(self, content, messages, **kwargs):
        self.sent_messages.append([dict(message) for message in messages])
        return {"is_tool_call": False, "content": content}

    def test_programming_request_gets_contract_and_simplicity_guidance_once(self):
        response = self.agent.chat_step("Implementa en Python una función de suma.")

        user_content = self.sent_messages[0][-1]["content"]
        self.assertEqual(response, "Respuesta de prueba")
        self.assertIn("identifica los nombres públicos", user_content)
        self.assertIn("Considera entradas vacías", user_content)
        self.assertIn("revisa imports", user_content)
        self.assertIn("conserva los contenedores vacíos", user_content)
        self.assertIn("finalízalo antes de crear los callbacks", user_content)
        self.assertIn("separa core, pre-release y +build", user_content)
        self.assertIn("orden de finalización", user_content)
        self.assertEqual(user_content.count(PROGRAMMING_TASK_GUIDANCE), 1)
        self.agent._call_llm.assert_called_once()

    def test_normal_conversation_is_unchanged(self):
        request = "¿Qué diferencia hay entre una estrella y un planeta?"

        response = self.agent.chat_step(request)

        self.assertEqual(response, "Respuesta de prueba")
        self.assertEqual(self.sent_messages[0][-1]["content"], request)
        self.agent._call_llm.assert_called_once()

    @patch("evals.coding_evaluator.execute_code_test")
    def test_explicit_acceptance_tests_get_review_guidance_without_extra_call(self, mock_execute):
        self.agent._call_llm = Mock(side_effect=lambda messages, **kwargs: self.respond_with(
            "```python\ndef suma(a, b):\n    return a + b\n```",
            messages,
            **kwargs,
        ))
        mock_execute.return_value = {"status": "PASS", "passed": True, "error": ""}
        request = (
            "Implementa en Python una función suma.\n\n"
            "Pruebas de aceptación:\n"
            "```python\nassert suma(1, 2) == 3\n```"
        )

        response = self.agent.chat_step(request)

        self.assertIn("Código aprobado por las pruebas de aceptación", response)
        self.assertTrue(
            self.sent_messages[0][-1]["content"].startswith(
                request + PROGRAMMING_TASK_GUIDANCE
            )
        )
        self.assertIn("no invoques herramientas", self.sent_messages[0][-1]["content"])
        self.agent._call_llm.assert_called_once()


if __name__ == "__main__":
    unittest.main()
