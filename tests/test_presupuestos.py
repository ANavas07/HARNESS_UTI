"""Regresion de limites usando la evidencia real; no requiere red."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from calcular_rutas import calculate
from medir_qwen import QwenClient


class ContextBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads((ROOT / "reports/llm/qwen-medicion.json").read_text(encoding="utf-8"))

    def test_real_samples_and_all_routes_fit_discovered_context(self):
        result = calculate(self.evidence)
        self.assertEqual(result["context_tokens"], 8192)
        self.assertEqual(result["samples"], 9)
        for sample in self.evidence["samples"]:
            self.assertEqual(sample["prompt_tokens"], sample["tokenized_prompt_tokens"])
            self.assertLessEqual(sample["prompt_tokens"] + sample["max_tokens"] + 820, 8192)
        for route in result["routes"]:
            self.assertLessEqual(route["reserved_tokens_per_call"], 8192)
            self.assertLessEqual(route["max_input_per_call"], result["input_policy_cap"])

    def test_smaller_server_window_rejects_old_routes(self):
        report = copy.deepcopy(self.evidence)
        report["context_tokens"] = 4096
        with self.assertRaises(ValueError):
            calculate(report)

    def test_mismatched_tokenizer_cannot_calibrate_routes(self):
        report = copy.deepcopy(self.evidence)
        report["samples"][0]["prompt_count_matches"] = False
        with self.assertRaises(ValueError):
            calculate(report)

    def test_oversized_prompt_is_rejected_before_generation(self):
        client = QwenClient()
        client.count = lambda messages: 7300

        def forbidden_request(*args, **kwargs):
            self.fail("No se debe generar si entrada + salida + margen excede el contexto")

        client.request = forbidden_request
        with self.assertRaisesRegex(ValueError, "context_budget_exceeded"):
            client.stream([], max_tokens=128, context=8192, margin=820)


if __name__ == "__main__":
    unittest.main()
