"""Línea de tiempo de una trayectoria del ciclo del agente (docs/loop-agente.md §8, laboratorio días 9–10). Sin red ni producto."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

PASOS = [
    {"paso": 0, "ts": "2026-11-05T14:02:11.000+00:00", "decision": "herramienta", "dur_ms": 812, "tokens_entrada": 1840, "tokens_salida": 41,
     "herramientas": [{"nombre": "consultar_agenda", "argumentos": {"desde": "mañana"}, "status": "ok", "error_code": None}]},
    {"paso": 1, "ts": "2026-11-05T14:02:12.000+00:00", "decision": "herramienta", "dur_ms": 640, "tokens_entrada": 2100, "tokens_salida": 38,
     "herramientas": [{"nombre": "consultar_agenda", "argumentos": {"desde": "mañana"}, "status": "ok", "error_code": None}]},
    {"paso": 2, "ts": "2026-11-05T14:02:13.000+00:00", "decision": "respuesta", "dur_ms": 905, "tokens_entrada": 2300, "tokens_salida": 60,
     "herramientas": [], "texto": "Mañana tienes C-0A01 a las 10:00."},
]


class LineaDeTiempo(unittest.TestCase):
    def setUp(self):
        import linea_de_tiempo
        self.m = linea_de_tiempo
        self.tmp = tempfile.TemporaryDirectory()
        self.archivo = Path(self.tmp.name) / "F01-manana-1.jsonl"
        self.archivo.write_text("".join(json.dumps(p, ensure_ascii=False) + "\n" for p in PASOS), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_la_tabla_muestra_cada_paso_con_su_costo(self):
        salida = io.StringIO()
        with contextlib.redirect_stdout(salida):
            self.m.main([str(self.archivo)])
        texto = salida.getvalue()
        self.assertIn("consultar_agenda", texto)
        self.assertIn("1840", texto)
        self.assertIn("respuesta", texto)
        self.assertIn("total: 3 pasos · 2357 ms · 6240 + 139 tokens", texto)

    def test_marca_las_iteraciones_que_no_aportaron(self):
        """El paso 1 repite la misma llamada con los mismos argumentos que el paso 0: no aportó nada nuevo."""
        resumen = self.m.resumir(self.m.leer(self.archivo))
        self.assertEqual(resumen["sin_aporte"], [1])
        self.assertEqual(resumen["paso_mas_caro"], 2)

    def test_genera_un_html_con_una_barra_por_paso(self):
        html = Path(self.tmp.name) / "linea.html"
        with contextlib.redirect_stdout(io.StringIO()):
            self.m.main([str(self.archivo), "--html", str(html)])
        contenido = html.read_text(encoding="utf-8")
        self.assertEqual(contenido.count('class="barra'), 3)
        self.assertIn("sin aporte", contenido)


if __name__ == "__main__":
    unittest.main()
