"""Solucion de referencia de D02: --check valida sin escribir reportes."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/calcular_rutas.py"
EVIDENCE = ROOT / "reports/llm/qwen-medicion.json"
OUTPUT = ROOT / "reports/llm/qwen-rutas.json"


def run_check(*args):
    return subprocess.run([sys.executable, str(SCRIPT), "--check", *args],
                          cwd=ROOT, capture_output=True, text=True)


class CheckModeTests(unittest.TestCase):
    def test_check_accepts_real_evidence_without_writing(self):
        before = OUTPUT.read_bytes()
        result = run_check()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(OUTPUT.read_bytes(), before)

    def test_check_rejects_smaller_context_without_traceback(self):
        report = copy.deepcopy(json.loads(EVIDENCE.read_text(encoding="utf-8")))
        report["context_tokens"] = 4096
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "medicion.json"
            path.write_text(json.dumps(report), encoding="utf-8")
            result = run_check("--input", str(path))
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
