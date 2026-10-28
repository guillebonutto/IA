"""Pruebas del recorte de historial del agente."""

import io
import json
import unittest
from unittest.mock import patch

from agent.core import (
    MAX_HISTORY_CONTEXT_BYTES,
    SYSTEM_PROMPT,
    LocalAgent,
)


class TestAgentHistory(unittest.TestCase):
    def setUp(self):
        self.agent = LocalAgent()

    def test_short_history_is_preserved(self):
        original = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "consulta reciente"},
            {"role": "assistant", "content": "respuesta reciente"},
        ]
        self.agent.history = [dict(message) for message in original]

        self.agent._trim_history()

        self.assertEqual(self.agent.history, original)

    def test_oversized_history_discards_old_turns_and_meets_byte_budget(self):
        latest_user = {"role": "user", "content": "consulta actual"}
        latest_assistant = {"role": "assistant", "content": "respuesta actual"}
        self.agent.history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "invalid", "content": "rol no admitido"},
            {"role": "user", "content": "historial antiguo " * 1200},
            {"role": "assistant", "content": "respuesta antigua " * 1200},
            latest_user,
            latest_assistant,
        ]

        self.agent._trim_history()

        self.assertNotIn("historial antiguo " * 2, self.agent.history[1]["content"])
        self.assertEqual(self.agent.history[-2:], [latest_user, latest_assistant])
        self.assertLessEqual(
            self.agent._history_size_bytes(self.agent.history),
            MAX_HISTORY_CONTEXT_BYTES,
        )

    def test_current_user_message_is_never_truncated(self):
        current_user = {"role": "user", "content": "mensaje actual " * 100}
        self.agent.history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            current_user,
        ]

        self.agent._trim_history(max_bytes=100)

        self.assertEqual(self.agent.history[-1], current_user)
        self.assertEqual(len(self.agent.history[-1]["content"]), len(current_user["content"]))

    def test_all_system_messages_are_preserved_while_old_turns_are_removed(self):
        first_system = {"role": "system", "content": SYSTEM_PROMPT}
        extra_system = {"role": "system", "content": "Política adicional"}
        current_user = {"role": "user", "content": "mensaje actual"}
        self.agent.history = [
            first_system,
            extra_system,
            {"role": "user", "content": "consulta antigua"},
            {"role": "assistant", "content": "respuesta antigua"},
            current_user,
        ]

        self.agent._trim_history(max_messages=3)

        self.assertEqual(self.agent.history[:2], [first_system, extra_system])
        self.assertEqual(self.agent.history[-1], current_user)
        self.assertNotIn({"role": "user", "content": "consulta antigua"}, self.agent.history)

    def test_tool_call_and_results_remain_as_one_recent_turn(self):
        old_user = {"role": "user", "content": "consulta anterior"}
        old_assistant = {"role": "assistant", "content": "respuesta anterior"}
        current_user = {"role": "user", "content": "consulta que usa herramienta"}
        tool_call = {
            "role": "assistant",
            "tool_calls": [{
                "id": "call-1",
                "type": "function",
                "function": {"name": "lookup", "arguments": "{}"},
            }],
            "content": None,
        }
        tool_result = {"role": "tool", "tool_call_id": "call-1", "content": "resultado"}
        final_assistant = {"role": "assistant", "content": "respuesta con resultado"}
        self.agent.history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            old_user,
            old_assistant,
            current_user,
            tool_call,
            tool_result,
            final_assistant,
        ]

        self.agent._trim_history(max_messages=5)

        self.assertEqual(self.agent.history[1:], [
            current_user,
            tool_call,
            tool_result,
            final_assistant,
        ])
        self.assertEqual(self.agent.history[2]["tool_calls"][0]["id"], "call-1")
        self.assertEqual(self.agent.history[3]["tool_call_id"], "call-1")

    @patch("agent.core.urllib.request.urlopen")
    def test_outgoing_model_request_uses_bounded_valid_history(self, mock_urlopen):
        mock_urlopen.return_value = io.BytesIO(
            b'{"choices":[{"message":{"content":"respuesta"}}]}'
        )
        current_user = {"role": "user", "content": "consulta actual"}
        self.agent.history = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "historial antiguo " * 1200},
            {"role": "assistant", "content": "respuesta antigua " * 1200},
            current_user,
        ]

        self.agent._call_llm(self.agent.history, allow_tools=False)

        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        sent_messages = payload["messages"]
        self.assertLessEqual(
            self.agent._history_size_bytes(sent_messages),
            MAX_HISTORY_CONTEXT_BYTES,
        )
        self.assertEqual(sent_messages[-1], current_user)
        self.assertTrue(all(
            message["role"] in {"system", "user", "assistant", "tool"}
            for message in sent_messages
        ))


if __name__ == "__main__":
    unittest.main()
