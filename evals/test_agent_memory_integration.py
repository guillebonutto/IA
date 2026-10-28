"""Pruebas de integración entre la memoria local y el contexto del agente."""

import logging
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from agent.core import LocalAgent, MAX_MEMORY_CONTEXT_CHARS, MEMORY_CONTEXT_HEADER
from agent.memory import LocalMemory


class TestAgentMemoryIntegration(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.memory = LocalMemory(
            db_path=str(Path(self.temp_dir.name) / "memory.db"),
            base_dir=self.temp_dir.name,
        )
        self.agent = LocalAgent(memory=self.memory)
        self.model_response = {"is_tool_call": False, "content": "Respuesta de prueba"}
        self.sent_messages = []
        self.agent._call_llm = Mock(side_effect=self._respond_to_model_call)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _respond_to_model_call(self, messages, **kwargs):
        self.sent_messages.append([dict(message) for message in messages])
        return self.model_response

    def test_relevant_document_is_added_to_model_context(self):
        self.memory.add_document(
            source="knowledge/python-memory.txt",
            title="SQLite FTS5",
            content="SQLite FTS5 indexa documentación local para búsquedas de texto completo.",
        )
        self.memory.search_knowledge = Mock(wraps=self.memory.search_knowledge)
        query = "¿Cómo buscar documentación local con SQLite FTS5?"

        response = self.agent.chat_step(query)

        user_content = self.sent_messages[0][-1]["content"]
        self.assertEqual(response, "Respuesta de prueba")
        self.assertIn("SQLite FTS5", user_content)
        self.assertIn("CONOCIMIENTO TÉCNICO DESTILADO DE REFERENCIA", user_content)
        self.memory.search_knowledge.assert_called_once_with(query, limit=2)
        self.assertEqual(self.agent._call_llm.call_count, 1)

    def test_no_results_preserve_original_message_without_empty_context(self):
        response = self.agent.chat_step("Consulta sobre un tema inexistente")

        user_content = self.sent_messages[0][-1]["content"]
        self.assertEqual(response, "Respuesta de prueba")
        self.assertEqual(user_content, "Consulta sobre un tema inexistente")
        self.assertNotIn(MEMORY_CONTEXT_HEADER, user_content)
        self.assertEqual(self.agent._call_llm.call_count, 1)

    def test_action_request_skips_memory_retrieval(self):
        self.memory.search_knowledge = Mock()

        self.agent.chat_step("Lee el archivo README.md")

        self.memory.search_knowledge.assert_not_called()
        self.assertEqual(
            self.sent_messages[0][-1]["content"],
            "Lee el archivo README.md",
        )

    def test_memory_context_is_bounded_and_duplicate_snippets_are_removed(self):
        snippet = "información técnica relevante " * 300
        self.memory.search_knowledge = Mock(return_value=[
            {"title": "Documento A", "snippet": snippet},
            {"title": "Documento duplicado", "snippet": snippet},
        ])

        self.agent.chat_step("Consulta de memoria")

        user_content = self.sent_messages[0][-1]["content"]
        added_context = user_content.split(MEMORY_CONTEXT_HEADER, 1)[1]
        self.assertLessEqual(len(MEMORY_CONTEXT_HEADER) + len(added_context), MAX_MEMORY_CONTEXT_CHARS)
        self.assertEqual(added_context.count("• "), 1)
        self.assertEqual(self.agent._call_llm.call_count, 1)

    def test_retrieval_error_is_logged_and_chat_continues_without_context(self):
        self.memory.search_knowledge = Mock(side_effect=RuntimeError("storage unavailable"))

        with self.assertLogs("agent.core", level=logging.ERROR) as captured:
            response = self.agent.chat_step("Consulta con error de memoria")

        user_content = self.sent_messages[0][-1]["content"]
        self.assertEqual(response, "Respuesta de prueba")
        self.assertEqual(user_content, "Consulta con error de memoria")
        self.assertIn("No se pudo recuperar contexto de memoria", captured.output[0])
        self.assertEqual(self.agent._call_llm.call_count, 1)

    def test_database_search_error_is_logged_and_chat_continues_without_context(self):
        connection = sqlite3.connect(self.memory.db_path)
        with connection:
            connection.execute("DROP TABLE doc_index")
        connection.close()

        with self.assertLogs("agent.memory", level=logging.ERROR) as captured:
            response = self.agent.chat_step("Consulta con índice de memoria ausente")

        user_content = self.sent_messages[0][-1]["content"]
        self.assertEqual(response, "Respuesta de prueba")
        self.assertEqual(user_content, "Consulta con índice de memoria ausente")
        self.assertIn("No se pudo buscar en la base de conocimiento local", captured.output[0])
        self.assertEqual(self.agent._call_llm.call_count, 1)


if __name__ == "__main__":
    unittest.main()
