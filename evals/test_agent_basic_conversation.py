"""Focused tests for everyday local chat routing."""

import unittest
from unittest.mock import Mock, patch

from agent.core import LocalAgent
from agent.tools import AgentTools


class TestAgentBasicConversation(unittest.TestCase):
    def test_simple_greeting_is_answered_without_model_or_tools(self):
        agent = LocalAgent()
        agent._call_llm = Mock(side_effect=AssertionError("model must not be called"))
        progress = []

        response = agent.chat_step("Hola", progress_callback=progress.append)

        self.assertEqual(response, "¡Hola! ¿En qué puedo ayudarte?")
        agent._call_llm.assert_not_called()
        self.assertEqual(
            progress,
            [{"type": "response", "content": "¡Hola! ¿En qué puedo ayudarte?"}],
        )
        self.assertEqual(agent.history[-2]["role"], "user")
        self.assertEqual(agent.history[-1]["role"], "assistant")

    def test_only_standalone_greetings_take_the_short_route(self):
        self.assertTrue(LocalAgent.is_simple_greeting("  ¡Hola! "))
        self.assertTrue(LocalAgent.is_simple_greeting("Buenos días."))
        self.assertFalse(LocalAgent.is_simple_greeting("Hola, lista los archivos"))
        self.assertFalse(LocalAgent.is_simple_greeting("¿Qué hora es?"))
        self.assertFalse(LocalAgent.is_simple_greeting("Escribe código en Python"))

    def test_non_greeting_requests_keep_model_path(self):
        agent = LocalAgent()
        agent._call_llm = Mock(return_value={
            "is_tool_call": False,
            "content": "Son las 12:34.",
        })

        response = agent.chat_step("¿Qué hora es?")

        self.assertEqual(response, "Son las 12:34.")
        agent._call_llm.assert_called_once()

    def test_datetime_tool_returns_local_time_and_is_registered(self):
        from datetime import datetime

        fixed_time = datetime.fromisoformat("2026-10-28T12:34:56-03:00")
        with patch("agent.tools.datetime") as datetime_type:
            datetime_type.now.return_value.astimezone.return_value = fixed_time
            result = AgentTools.get_datetime()

        self.assertEqual(result["local_datetime"], "2026-10-28T12:34:56-03:00")
        self.assertEqual(result["timezone"], "UTC-03:00")
        names = {
            declaration["function"]["name"]
            for declaration in AgentTools().get_tools_declarations()
        }
        self.assertIn("get_datetime", names)
