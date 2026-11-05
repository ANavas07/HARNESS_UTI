"""Comparador A/B de corridas de evals de runtime (docs/loop-agente.md §9). Sin red ni producto."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))


def corrida(carpeta: Path, resultados: dict[str, tuple[bool, bool, int, int]]):
    """resultados: id → (crítico, ok, tokens, pasos)."""
    carpeta.mkdir(parents=True)
    por_eval = []
    for i, (critico, ok, tokens, pasos) in resultados.items():
        r = {"corrida": 1, "ok": ok, "consumo": {"entrada": tokens - 50, "salida": 50, "llamadas": pasos}, "trayectoria": [{}] * pasos,
             "duracion_s": 3.0}
        (carpeta / f"{i}.json").write_text(json.dumps({"id": i, "corridas": [r]}), encoding="utf-8")
        por_eval.append({"id": i, "critico": critico, "aprobadas": int(ok), "corridas": 1})
    aprobadas = sum(ok for _, ok, _, _ in resultados.values())
    (carpeta / "resumen.json").write_text(json.dumps({"tasa": aprobadas / len(resultados), "aprobadas": aprobadas, "corridas": len(resultados),
                                                      "por_eval": por_eval}), encoding="utf-8")


class Comparador(unittest.TestCase):
    def setUp(self):
        import comparar_corridas
        self.m = comparar_corridas
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def comparar(self, a, b, tope=0.10):
        corrida(self.dir / "a", a)
        corrida(self.dir / "b", b)
        return self.m.comparar(self.m.cargar(self.dir / "a"), self.m.cargar(self.dir / "b"), tope)

    def test_se_queda_si_mejora_sin_pasar_el_tope_de_tokens(self):
        r = self.comparar({"P01": (True, False, 5000, 2), "F01": (False, True, 5000, 2)},
                          {"P01": (True, True, 5300, 2), "F01": (False, True, 5300, 2)})
        self.assertEqual((r["gana"], r["pierde"], r["delta_tokens"], r["se_queda"]), (["P01"], [], 0.06, True))

    def test_no_se_queda_si_cuesta_mas_del_tope(self):
        r = self.comparar({"F01": (False, True, 5000, 2)}, {"F01": (False, True, 5600, 2)})
        self.assertFalse(r["criterios"]["tokens_dentro_del_tope"])
        self.assertFalse(r["se_queda"])

    def test_no_se_queda_si_empeora_un_critico(self):
        r = self.comparar({"P01": (True, True, 5000, 2), "F01": (False, False, 5000, 2)},
                          {"P01": (True, False, 5000, 2), "F01": (False, True, 5000, 2)})
        self.assertEqual((r["gana"], r["pierde"]), (["F01"], ["P01"]))
        self.assertFalse(r["criterios"]["criticos_no_empeoran"])
        self.assertFalse(r["se_queda"])


if __name__ == "__main__":
    unittest.main()
