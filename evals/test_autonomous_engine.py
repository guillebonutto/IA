import unittest
import socket
from pathlib import Path
from scratch.autonomous_improvement_engine import (
    AutonomousImprovementEngine,
    verify_dataset_and_benchmark_hashes,
    EXPECTED_HASHES,
    PORT,
    PROD_PORT
)

class TestAutonomousEngineSafeguards(unittest.TestCase):

    def test_benchmark_hash_integrity(self):
        """Verifica que el motor detecte la inmutabilidad de benchmarks y datasets."""
        self.assertTrue(verify_dataset_and_benchmark_hashes())

    def test_ports_not_colliding(self):
        """Verifica que los puertos experimental y producción estén disjuntos."""
        self.assertNotEqual(PORT, PROD_PORT)
        self.assertEqual(PORT, 8083)
        self.assertEqual(PROD_PORT, 8089)

    def test_state_persistence(self):
        """Verifica que el motor cargue y guarde su estado estructurado."""
        engine = AutonomousImprovementEngine()
        self.assertIn("engine_status", engine.state)
        self.assertIn("best_baseline", engine.state)
        self.assertIn("history", engine.state)

if __name__ == "__main__":
    unittest.main()
