"""Deriva presupuestos y proyecciones desde reports/llm/qwen-medicion.json.

No llama al modelo. Los tiempos de herramientas son provisiones, no mediciones.
"""
import argparse
import json
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


ROUTES = [
    # nombre, entrada/llamada, salida/llamada, llamadas/tarea, otros segundos
    ("O1", 3000, 256, 3, 5),
    ("O2", 5000, 768, 4, 10),
    ("R0", 3000, 512, 4, 10),
    ("R1", 5000, 1024, 8, 30),
    ("R2", 5500, 1024, 16, 60),
]


def calculate(report):
    if report.get("status") != "completed":
        raise ValueError("Se requiere una medicion completa; no usar datos inventados")
    samples = report["samples"]
    if not samples or not all(s["prompt_count_matches"] for s in samples):
        raise ValueError("Falta medicion o el tokenizador no coincide con usage")
    context = min(report["context_tokens"], 32768)
    margin = math.ceil(context * 0.10)
    rates = [s["decode_tokens_per_s_approx"] for s in samples
             if s.get("decode_tokens_per_s_approx")]
    if not rates or min(rates) <= 0:
        raise ValueError("No hay tasa de generacion valida")
    v_min = min(rates)
    ttft_max = max(s["ttft_s"] for s in samples if s["ttft_s"] is not None)
    result = {"model": report["model"], "context_tokens": context,
              "margin_tokens": margin, "input_policy_cap": math.floor(context * 0.70),
              "samples": len(samples), "observed_min_decode_tokens_per_s": v_min,
              "observed_max_ttft_s": ttft_max,
              "total_measured_prompt_tokens": sum(s["prompt_tokens"] for s in samples),
              "total_measured_completion_tokens": sum(s["completion_tokens"] for s in samples),
              "routes": []}
    for route, inp, out, calls, other in ROUTES:
        if inp + out + margin > context or inp > math.floor(context * .70):
            raise ValueError(f"Ruta {route} no cabe en el contexto: compactar o reducir")
        projected = calls * (ttft_max + out / v_min) + other
        deadline = math.ceil(projected * 1.25 / 15) * 15
        result["routes"].append({
            "route": route, "max_input_per_call": inp, "max_output_per_call": out,
            "max_calls": calls, "reserved_tokens_per_call": inp + out + margin,
            "headroom_tokens": context - inp - out - margin,
            "max_input_per_task": inp * calls, "max_output_per_task": out * calls,
            "other_time_allowance_s": other,
            "projected_time_s": round(projected, 3), "proposed_deadline_s": deadline,
            "timing_is_projection": True,
        })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=PROJECT_ROOT / "reports/llm/qwen-medicion.json")
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/llm/qwen-rutas.json")
    parser.add_argument("--check", action="store_true", help="Validar sin escribir archivos")
    args = parser.parse_args()
    try:
        result = calculate(json.loads(args.input.read_text(encoding="utf-8")))
    except (ValueError, KeyError, OSError) as exc:
        if not args.check:
            raise
        print(f"check fallido: {exc}", file=sys.stderr)
        sys.exit(1)
    if args.check:
        print(f"check correcto: {len(result['routes'])} rutas caben en {result['context_tokens']} tokens")
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
