"""Línea de tiempo de una trayectoria del ciclo del agente (docs/loop-agente.md §8, laboratorio días 9–10).

Lee las trayectorias JSONL que deja `ejecutar_runtime.py` (una línea por paso) y muestra cada paso con su decisión, sus herramientas,
duración y tokens. Marca los pasos que no aportaron, es decir, los que repiten una llamada (misma herramienta y argumentos) que ya se
hizo, y el paso más caro. Con `--html` escribe además una página con una barra por paso.

Uso: python scripts/linea_de_tiempo.py reports/evals/runtime/<corrida>/trayectorias/P01-...-1.jsonl [--html linea.html]
"""
from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path


def leer(ruta: Path) -> list[dict]:
    return [json.loads(linea) for linea in Path(ruta).read_text(encoding="utf-8").splitlines() if linea.strip()]


def _firma(h: dict) -> str:
    return h["nombre"] + json.dumps(h.get("argumentos", {}), sort_keys=True, ensure_ascii=False)


def resumir(pasos: list[dict]) -> dict:
    vistas, sin_aporte = set(), []
    for p in pasos:
        firmas = [_firma(h) for h in p.get("herramientas", [])]
        if firmas and all(f in vistas for f in firmas):
            sin_aporte.append(p["paso"])
        vistas.update(firmas)
    costo = {p["paso"]: (p.get("tokens_entrada") or 0) + (p.get("tokens_salida") or 0) for p in pasos}
    return {"pasos": len(pasos), "dur_ms": sum(p.get("dur_ms") or 0 for p in pasos),
            "entrada": sum(p.get("tokens_entrada") or 0 for p in pasos), "salida": sum(p.get("tokens_salida") or 0 for p in pasos),
            "sin_aporte": sin_aporte, "paso_mas_caro": max(costo, key=costo.get) if costo else None}


def _accion(p: dict) -> str:
    if not p.get("herramientas"):
        return p.get("decision", "?")
    return ", ".join(f"{h['nombre']} → {h.get('error_code') or h.get('status') or '?'}" for h in p["herramientas"])


def tabla(pasos: list[dict], r: dict) -> str:
    filas = [f"{'paso':>4}  {'decisión':<11} {'ms':>6} {'entrada':>8} {'salida':>7}  acción"]
    for p in pasos:
        marca = "  ← sin aporte" if p["paso"] in r["sin_aporte"] else ""
        filas.append(f"{p['paso']:>4}  {p.get('decision', '?'):<11} {p.get('dur_ms') or 0:>6} {p.get('tokens_entrada') or 0:>8} "
                     f"{p.get('tokens_salida') or 0:>7}  {_accion(p)}{marca}")
    filas.append(f"total: {r['pasos']} pasos · {r['dur_ms']} ms · {r['entrada']} + {r['salida']} tokens"
                 + (f" · sin aporte: {r['sin_aporte']}" if r["sin_aporte"] else ""))
    return "\n".join(filas)


def pagina(nombre: str, pasos: list[dict], r: dict) -> str:
    maximo = max((p.get("dur_ms") or 0 for p in pasos), default=1) or 1
    barras = []
    for p in pasos:
        ancho = max(2, round(100 * (p.get("dur_ms") or 0) / maximo))
        clase = "barra sin" if p["paso"] in r["sin_aporte"] else "barra"
        nota = " · sin aporte" if p["paso"] in r["sin_aporte"] else ""
        barras.append(f'<div class="fila"><span class="et">{p["paso"]} · {html.escape(p.get("decision", "?"))}</span>'
                      f'<div class="{clase}" style="width:{ancho}%"></div>'
                      f'<span class="det">{p.get("dur_ms") or 0} ms · {p.get("tokens_entrada") or 0}+{p.get("tokens_salida") or 0} tokens · '
                      f'{html.escape(_accion(p))}{nota}</span></div>')
    return f"""<!doctype html><html lang="es"><head><meta charset="utf-8"><title>Línea de tiempo · {html.escape(nombre)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;color:#1d1730}}.fila{{display:grid;grid-template-columns:140px 1fr;gap:4px 12px;
margin:10px 0}}.barra{{height:14px;border-radius:7px;background:#7c5cd6}}.barra.sin{{background:#d9822b}}.det{{grid-column:2;font-size:13px;
color:#5b5470}}.et{{font-weight:600;font-size:14px}}</style></head><body><h1>{html.escape(nombre)}</h1>
<p>{r['pasos']} pasos · {r['dur_ms']} ms · {r['entrada']} + {r['salida']} tokens</p>{''.join(barras)}</body></html>"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("trayectorias", nargs="+")
    ap.add_argument("--html", help="escribe una página con la línea de tiempo (de la primera trayectoria)")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")                       # la consola de Windows (cp1252) no imprime «→»
    for i, ruta in enumerate(a.trayectorias):
        pasos = leer(Path(ruta))
        r = resumir(pasos)
        print(f"== {Path(ruta).stem}")
        print(tabla(pasos, r))
        if a.html and i == 0:
            Path(a.html).write_text(pagina(Path(ruta).stem, pasos, r), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
