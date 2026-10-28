"""Runner de evals con controles y agentes simulados; no requiere red ni modelo."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D02 = ROOT / "evals/desarrollo/D02-calculador-check.yaml"
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import yaml
except ImportError:
    yaml = None


# En la copia aislada de un eval no existe evals/: esta suite se omite alli.
@unittest.skipUnless(yaml and D02.is_file(), "requiere PyYAML y evals/")
class EvalRunnerTests(unittest.TestCase):
    def setUp(self):
        import ejecutar_eval
        self.runner = ejecutar_eval
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "reportes"

    def tearDown(self):
        self.tmp.cleanup()

    def run_eval(self, *args, spec=D02):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = self.runner.main([str(spec), "--origen", "trabajo", "--salida", str(self.out), *args])
        summaries = sorted(self.out.rglob("*-resumen.json"))
        records = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted(self.out.rglob("*.json")) if not p.name.endswith("-resumen.json")]
        return code, json.loads(summaries[-1].read_text(encoding="utf-8")), records

    def agent(self, body):
        script = Path(self.tmp.name) / "agente.py"
        script.write_text(body, encoding="utf-8")
        return f'"{sys.executable}" "{script}"'

    def custom_spec(self, **changes):
        spec = yaml.safe_load(D02.read_text(encoding="utf-8"))
        spec.update(changes)
        path = Path(self.tmp.name) / "eval.yaml"
        path.write_text(yaml.safe_dump(spec, allow_unicode=True), encoding="utf-8")
        return path

    def test_controls_fail_on_base_and_pass_with_reference(self):
        code, summary, records = self.run_eval("--control", "negativo")
        self.assertEqual((code, summary["cumple"]), (0, True))
        self.assertEqual(records[0]["resultado"], "failed")
        code, summary, records = self.run_eval("--control", "positivo")
        self.assertEqual((code, summary["cumple"]), (0, True))
        self.assertEqual(records[-1]["resultado"], "accepted")

    def test_simulated_agent_is_accepted_and_reports_signals(self):
        solution = (ROOT / "evals/desarrollo/soluciones/D02").as_posix()
        command = self.agent(
            "import json, os, shutil\n"
            f"shutil.copytree({solution!r}, os.environ['EVAL_REPO'], dirs_exist_ok=True)\n"
            "json.dump({'intentos_hasta_verde': 2, 'comandos_fallidos': 0},"
            " open(os.environ['EVAL_SENALES'], 'w'))\n")
        code, summary, records = self.run_eval("--agente", command, "--corridas", "1")
        self.assertEqual(code, 0)
        self.assertEqual(records[0]["resultado"], "accepted")
        self.assertEqual(records[0]["senales"]["intentos_hasta_verde"], 2)
        self.assertIsNone(records[0]["senales"]["tokens_entrada"])
        self.assertEqual(summary["mediana_comandos_fallidos"], 0)

    def test_changes_outside_scope_fail_the_grader(self):
        solution = (ROOT / "evals/desarrollo/soluciones/D02").as_posix()
        command = self.agent(
            "import os, pathlib, shutil\n"
            f"shutil.copytree({solution!r}, os.environ['EVAL_REPO'], dirs_exist_ok=True)\n"
            "pathlib.Path(os.environ['EVAL_REPO'], 'README.md').write_text('borrado')\n")
        code, summary, records = self.run_eval("--agente", command, "--corridas", "1")
        self.assertEqual((code, records[0]["resultado"]), (1, "failed"))
        self.assertEqual([s["paso"] for s in records[0]["grader"] if not s["ok"]], [7])

    def test_agent_over_deadline_is_budget_exceeded(self):
        spec = self.custom_spec(presupuesto={"ruta": "R1", "tiempo_max_s": 1})
        command = self.agent("import time\ntime.sleep(20)\n")
        code, summary, records = self.run_eval("--agente", command, "--corridas", "1", spec=spec)
        self.assertEqual((code, records[0]["resultado"]), (1, "budget_exceeded"))
        self.assertLess(records[0]["tiempos_s"]["agente"], 15)

    def test_unsupported_grader_step_is_environment_error(self):
        spec = self.custom_spec(grader=[{"nombre": "http", "http": "GET /", "status": 200}])
        code, summary, records = self.run_eval("--control", "negativo", spec=spec)
        self.assertEqual(records[0]["resultado"], "environment_error")

    def test_blocked_and_runtime_evals_are_refused(self):
        for blocked in ("desarrollo/D01-disponibilidad.yaml", "runtime/C01-reprogramar.yaml"):
            with contextlib.redirect_stderr(io.StringIO()):
                code = self.runner.main([str(ROOT / "evals" / blocked), "--control", "negativo",
                                         "--salida", str(self.out)])
            self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
