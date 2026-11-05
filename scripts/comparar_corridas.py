"""Compara dos corridas de evals de runtime (A/B): tasa, críticos, tokens y pasos por tarea, y qué evals cambian de resultado.

Sirve para decidir un cambio del harness con el mismo modelo (docs/loop-agente.md §9): por ejemplo, la razón de ReAct (fase B) se
queda solo si la tasa no baja, los críticos no empeoran y los tokens por tarea suben ≤ 10 %.

Uso: python scripts/comparar_corridas.py <carpeta A> <carpeta B> [--nombres sin con] [--tope-tokens 0.10]
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


def cargar(carpeta: Path) -> dict:
    resumen = json.loads((carpeta / "resumen.json").read_text(encoding="utf-8"))
    corridas = {}
    for f in carpeta.glob("*.json"):
        if f.name != "resumen.json":
            datos = json.loads(f.read_text(encoding="utf-8"))
            corridas[datos["id"]] = datos["corridas"]
    return {"resumen": resumen, "corridas": corridas}


def metricas(c: dict) -> dict:
    todas = [r for rs in c["corridas"].values() for r in rs]
    tokens = [r["consumo"]["entrada"] + r["consumo"]["salida"] for r in todas if r.get("consumo")]
    pasos = [len(r.get("trayectoria") or []) or (r["consumo"]["llamadas"] if r.get("consumo") else 0) for r in todas]
    criticos = {f["id"]: f["aprobadas"] == f["corridas"] for f in c["resumen"]["por_eval"] if f["critico"]}
    return {"tasa": c["resumen"]["tasa"], "aprobadas": c["resumen"]["aprobadas"], "corridas": c["resumen"]["corridas"],
            "criticos_ok": sum(criticos.values()), "criticos": len(criticos),
            "tokens_tarea": statistics.mean(tokens) if tokens else 0.0, "pasos_tarea": statistics.mean(pasos) if pasos else 0.0,
            "duracion_tarea": statistics.mean(r.get("duracion_s") or 0 for r in todas) if todas else 0.0}


def comparar(a: dict, b: dict, tope_tokens: float = 0.10) -> dict:
    ma, mb = metricas(a), metricas(b)
    ok = lambda c, i: all(r["ok"] for r in c["corridas"].get(i, []))       # noqa: E731
    ids = sorted(set(a["corridas"]) | set(b["corridas"]))
    gana = [i for i in ids if not ok(a, i) and ok(b, i)]
    pierde = [i for i in ids if ok(a, i) and not ok(b, i)]
    delta_tokens = (mb["tokens_tarea"] - ma["tokens_tarea"]) / ma["tokens_tarea"] if ma["tokens_tarea"] else 0.0
    criterios = {"tasa_no_baja": mb["tasa"] >= ma["tasa"], "criticos_no_empeoran": mb["criticos_ok"] >= ma["criticos_ok"],
                 "tokens_dentro_del_tope": delta_tokens <= tope_tokens}
    return {"a": ma, "b": mb, "gana": gana, "pierde": pierde, "delta_tokens": round(delta_tokens, 3), "criterios": criterios,
            "se_queda": all(criterios.values())}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--nombres", nargs=2, default=["A", "B"])
    ap.add_argument("--tope-tokens", type=float, default=0.10)
    x = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    r = comparar(cargar(Path(x.a)), cargar(Path(x.b)), x.tope_tokens)
    na, nb = x.nombres
    print(f"{'':<16}{na:>12}{nb:>12}")
    for clave, et in (("tasa", "tasa"), ("criticos_ok", "críticos ok"), ("tokens_tarea", "tokens/tarea"), ("pasos_tarea", "pasos/tarea"),
                      ("duracion_tarea", "segundos/tarea")):
        va, vb = r["a"][clave], r["b"][clave]
        fmt = (lambda v: f"{v:.1%}") if clave == "tasa" else (lambda v: f"{v:.0f}" if clave != "pasos_tarea" else f"{v:.2f}")
        print(f"{et:<16}{fmt(va):>12}{fmt(vb):>12}")
    print(f"\n{nb} gana: {r['gana'] or '—'}\n{nb} pierde: {r['pierde'] or '—'}\nΔ tokens/tarea: {r['delta_tokens']:+.1%}")
    print(f"criterios: {r['criterios']} → {'SE QUEDA' if r['se_queda'] else 'NO SE QUEDA'}")
    print(json.dumps({"comparacion": {k: r[k] for k in ("gana", "pierde", "delta_tokens", "criterios", "se_queda")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
