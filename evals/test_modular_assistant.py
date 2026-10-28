import unittest
import uuid
from pathlib import Path
from scratch.modular_assistant_core import AssistantMemory, ControlledToolDispatcher

class TestModularAssistantCore(unittest.TestCase):
    def setUp(self):
        self.temp_db = Path(f"scratch/test_assistant_memory_{uuid.uuid4().hex[:8]}.db")
        self.memory = AssistantMemory(db_path=self.temp_db)
        self.dispatcher = ControlledToolDispatcher()

    def tearDown(self):
        del self.memory
        import gc
        gc.collect()
        if self.temp_db.exists():
            try:
                self.temp_db.unlink()
            except Exception:
                pass

    def test_memory_crud_facts(self):
        # Create
        self.memory.set_fact("user_pref", "dark_mode", category="ui")
        self.assertEqual(self.memory.get_fact("user_pref"), "dark_mode")

        # Update
        self.memory.set_fact("user_pref", "light_mode", category="ui")
        self.assertEqual(self.memory.get_fact("user_pref"), "light_mode")

        # List
        facts = self.memory.list_facts()
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0]["key"], "user_pref")

        # Delete
        deleted = self.memory.delete_fact("user_pref")
        self.assertTrue(deleted)
        self.assertIsNone(self.memory.get_fact("user_pref"))

    def test_conversation_history_persistence(self):
        self.memory.append_message("sess_1", "user", "Hola", action_type="PROPOSED")
        self.memory.append_message("sess_1", "assistant", "Respuesta", action_type="VERIFIED")
        
        hist = self.memory.get_recent_history("sess_1", limit=5)
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0]["role"], "user")
        self.assertEqual(hist[0]["action_type"], "PROPOSED")
        self.assertEqual(hist[1]["role"], "assistant")
        self.assertEqual(hist[1]["action_type"], "VERIFIED")

    def test_tool_dispatcher_security_and_sandbox(self):
        # Permitted file read
        res = self.dispatcher.read_file("evals/coding_tasks.json")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("tasks", res["content"])

        # Path traversal prevention
        with self.assertRaises(PermissionError):
            self.dispatcher.read_file("../../Windows/System32/drivers/etc/hosts")

        # Sandbox execution of simple python code
        sandbox_res = self.dispatcher.execute_in_sandbox("x = 40 + 2", "assert x == 42")
        self.assertEqual(sandbox_res["status"], "SUCCESS")
        self.assertTrue(sandbox_res["passed"])

if __name__ == "__main__":
    unittest.main()
