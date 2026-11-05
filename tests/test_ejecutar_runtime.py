"""Ejecutor de evals de runtime (SPEC §33.5, E10-T39) con LLM controlado: sin red ni modelo.

Necesita el producto (PRODUCTO_BACKEND = su carpeta backend) y PostgreSQL (PG_BIN); sin ellos la suite se omite.
  CA1  cada eval falla con un agente nulo y pasa con su respuesta de referencia
  CA2  dos corridas con el mismo LLM controlado dan el mismo resultado
  CA3  el reporte usa el formato del lab y toma las señales del consumo de la tarea
"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
PRODUCTO = os.environ.get("PRODUCTO_BACKEND", "")
MUESTRA = [ROOT / "evals" / "runtime" / f for f in ("F01-manana.yaml", "P01-reprogramar-jueves-tarde.yaml", "M04-dos-citas-manana.yaml",
                                                     "X01-seguimiento-agenda-ajena.yaml", "V03-inyeccion-en-agenda.yaml", "B02-historial-que-no-cabe.yaml")]


def correr(*args):
    import ejecutar_runtime
    salida = io.StringIO()
    with contextlib.redirect_stdout(salida):
        ejecutar_runtime.main([*map(str, MUESTRA), "--producto", PRODUCTO, *args])
    return json.loads(salida.getvalue().strip().splitlines()[-1])["resumen"]


HAY_EVALS = all(p.is_file() for p in MUESTRA)          # en la copia aislada de un eval de desarrollo no existe evals/


@unittest.skipUnless(HAY_EVALS and PRODUCTO and Path(PRODUCTO, "api", "app", "chat", "agente.py").is_file(),
                     "requiere evals/, PRODUCTO_BACKEND y PostgreSQL")
class EjecutorRuntime(unittest.TestCase):
    def test_ca1_la_referencia_pasa_y_el_agente_nulo_falla_en_cada_eval(self):
        guion, nulo = correr("--modelo", "guion", "--corridas", "1", "--sin-reporte"), correr("--modelo", "nulo", "--corridas", "1", "--sin-reporte")
        self.assertEqual((guion["aprobadas"], guion["corridas"], guion["gate"]), (6, 6, True))
        self.assertEqual((nulo["aprobadas"], nulo["gate"]), (0, False))

    def test_ca2_el_mismo_llm_controlado_da_el_mismo_resultado(self):
        uno, dos = (correr("--modelo", "guion", "--corridas", "2", "--sin-reporte") for _ in range(2))
        self.assertEqual(uno, dos)

    def test_ca3_el_reporte_tiene_pasos_y_consumo_por_corrida(self):
        with tempfile.TemporaryDirectory() as tmp:
            correr("--modelo", "guion", "--corridas", "1", "--salida", tmp)
            [carpeta] = Path(tmp).iterdir()
            resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
            corrida = json.loads((carpeta / "P01-reprogramar-jueves-tarde.json").read_text(encoding="utf-8"))["corridas"][0]
        self.assertEqual({f["id"] for f in resumen["por_eval"]}, {p.stem for p in MUESTRA})
        self.assertTrue(corrida["ok"] and corrida["consumo"]["ruta"] in ("O1", "O2") and corrida["consumo"]["llamadas"] >= 2)
        self.assertEqual([p["accion"] for p in corrida["propuestas"]], ["reprogramar"] * len(corrida["propuestas"]))
        self.assertIn("propuesta_igual", {p["tipo"] for p in corrida["pasos"]})


    def test_loop_fase_a_cada_corrida_deja_su_trayectoria_jsonl(self):
        """docs/loop-agente.md §8: en los evals (datos sintéticos) la trayectoria lleva argumentos y resultado por paso."""
        with tempfile.TemporaryDirectory() as tmp:
            correr("--modelo", "guion", "--corridas", "1", "--salida", tmp)
            [carpeta] = Path(tmp).iterdir()
            pasos = [json.loads(l) for l in (carpeta / "trayectorias" / "P01-reprogramar-jueves-tarde-1.jsonl").read_text(encoding="utf-8").splitlines()]
        assert [p["paso"] for p in pasos] == [0, 1] and [p["decision"] for p in pasos] == ["herramienta", "respuesta"]
        [h] = pasos[0]["herramientas"]
        assert (h["nombre"], h["argumentos"]["cita"], h["status"]) == ("proponer_reprogramacion", "C-0A03", "ok")
        assert all(p["dur_ms"] >= 0 and p["tokens_entrada"] > 0 for p in pasos)


ROTURA = sorted((ROOT / "evals" / "runtime-rotura").glob("*.yaml"))


@unittest.skipUnless(ROTURA and PRODUCTO and Path(PRODUCTO, "api", "app", "chat", "agente.py").is_file(),
                     "requiere evals/runtime-rotura, PRODUCTO_BACKEND y PostgreSQL")
class RoturaDelLoop(unittest.TestCase):
    """docs/loop-agente.md §9 y §10 (fase D): averías simuladas con sus controles, la referencia pasa y el agente nulo falla."""
    def correr(self, *args, salida=None):
        import ejecutar_runtime
        texto = io.StringIO()
        extra = ["--salida", salida] if salida else ["--sin-reporte"]
        with contextlib.redirect_stdout(texto):
            ejecutar_runtime.main([*map(str, ROTURA), "--producto", PRODUCTO, "--corridas", "1", *extra, *args])
        return json.loads(texto.getvalue().strip().splitlines()[-1])["resumen"]

    def test_la_referencia_pasa_y_el_agente_nulo_falla(self):
        guion, nulo = self.correr("--modelo", "guion"), self.correr("--modelo", "nulo")
        self.assertEqual((guion["aprobadas"], guion["corridas"]), (len(ROTURA), len(ROTURA)))
        self.assertEqual(nulo["aprobadas"], 0)

    def test_la_herramienta_caida_llega_al_modelo_como_fallo_y_no_tumba_la_corrida(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.correr("--modelo", "guion", salida=tmp)
            [carpeta] = Path(tmp).iterdir()
            corrida = json.loads((carpeta / "R01-agenda-caida.json").read_text(encoding="utf-8"))["corridas"][0]
        [h] = corrida["trayectoria"][0]["herramientas"]
        self.assertEqual((h["nombre"], h["ejecutada"], h["error_code"]), ("consultar_agenda", False, "herramienta_no_responde"))
        self.assertIsNone(corrida["error"])
        self.assertNotIn("avería simulada", json.dumps(corrida, ensure_ascii=False))     # el detalle técnico no llega al modelo

    def test_el_servidor_transitorio_falla_solo_las_primeras_llamadas_de_generacion(self):
        import ejecutar_runtime
        ejecutar_runtime.importar_producto(PRODUCTO)
        from shared.llm import ErrorTransitorio

        class Cliente:
            def __init__(self):
                self.rutas = []

            def _post(self, cuerpo, ruta="/v1/chat/completions"):
                self.rutas.append(ruta)
                return {}
        c = Cliente()
        cuenta = ejecutar_runtime.servidor_transitorio(c, 1)
        c._post({}, "/tokenize")
        with self.assertRaises(ErrorTransitorio):
            c._post({})
        c._post({})
        self.assertEqual((cuenta, c.rutas), ({"aplica": True, "lanzadas": 1}, ["/tokenize", "/v1/chat/completions"]))
        self.assertEqual(ejecutar_runtime.servidor_transitorio(object(), 1), {"aplica": False, "lanzadas": 0})


@unittest.skipUnless(HAY_EVALS, "requiere evals/")
class FormatoDeLosEvals(unittest.TestCase):
    """Sin producto: el conjunto cumple §33.5 (60 evals, categorías y críticos) y cada uno tiene su referencia."""
    def test_sesenta_evals_con_las_categorias_del_spec(self):
        import yaml
        evals = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "evals" / "runtime").glob("*.yaml"))]
        por = {}
        for e in evals:
            por.setdefault(e["categoria"], []).append(e)
        self.assertEqual({k: len(v) for k, v in por.items()}, {
            "fechas_relativas_y_zona": 12, "consulta_de_agenda_y_derivaciones": 10, "propuestas_de_reprogramacion_y_cancelacion": 10,
            "datos_faltantes_o_ambiguos": 8, "permisos_y_alcance": 8, "texto_adversarial": 8, "presupuesto_y_compactacion": 4})
        criticas = {"propuestas_de_reprogramacion_y_cancelacion", "datos_faltantes_o_ambiguos", "permisos_y_alcance", "texto_adversarial"}
        for e in evals:
            self.assertEqual(bool(e["critico"]), e["categoria"] in criticas, e["id"])
            self.assertEqual(e["corridas"], 10, e["id"])
            self.assertTrue(e["referencia"] and "responder" in e["referencia"][-1], e["id"])


if __name__ == "__main__":
    unittest.main()
