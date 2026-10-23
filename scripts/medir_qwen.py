"""Mediciones secuenciales y acotadas de Qwen/vLLM con datos sinteticos.

Python 3.10+, sin dependencias. No ejecuta herramientas ni escribe citas.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
from urllib.error import HTTPError
from urllib.request import Request, urlopen


class QwenClient:
    def __init__(self):
        self.base = os.getenv("QWEN_BASE_URL", "http://172.16.8.69:8000/v1").rstrip("/")
        self.model = os.getenv("QWEN_MODEL", "Qwen/Qwen3-8B-AWQ")
        self.timeout = float(os.getenv("QWEN_TIMEOUT_SECONDS", "45"))
        self.key = os.getenv("QWEN_API_KEY", "")
        self.server = self.base[:-3] if self.base.endswith("/v1") else self.base

    def request(self, url, payload=None):
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = "Bearer " + self.key
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        return urlopen(Request(url, data=data, headers=headers), timeout=self.timeout)

    def json(self, url, payload=None):
        with self.request(url, payload) as response:
            return json.load(response)

    def discover(self):
        models = self.json(self.base + "/models")
        selected = next((m for m in models["data"] if m["id"] == self.model), None)
        if selected is None:
            raise ValueError("El modelo configurado no aparece en /v1/models")
        context = selected.get("max_model_len")
        if not isinstance(context, int) or context <= 0:
            raise ValueError("El servidor no informa max_model_len; no asumir un contexto")
        return selected

    def count(self, messages, tools=None):
        payload = {
            "model": self.model, "messages": messages,
            "add_generation_prompt": True,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if tools is not None:
            payload["tools"] = tools
        result = self.json(self.server + "/tokenize", payload)
        return int(result["count"])

    def stream(self, messages, max_tokens, context, margin):
        prompt_count = self.count(messages)
        if prompt_count + max_tokens + margin > context:
            raise ValueError("context_budget_exceeded antes de generar")
        payload = {
            "model": self.model, "messages": messages,
            "temperature": 0.3, "max_tokens": max_tokens,
            "stream": True, "stream_options": {"include_usage": True},
            "chat_template_kwargs": {"enable_thinking": False},
        }
        start = time.perf_counter()
        first = last = None
        usage = None
        finish = None
        text_parts = []
        done = False
        with self.request(self.base + "/chat/completions", payload) as response:
            for raw in response:
                if time.perf_counter() - start > self.timeout:
                    raise TimeoutError("Plazo de generacion agotado")
                line = raw.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                body = line[5:].strip()
                if body == "[DONE]":
                    done = True
                    break
                item = json.loads(body)
                if item.get("error"):
                    raise RuntimeError(str(item["error"]))
                if item.get("usage"):
                    usage = item["usage"]
                for choice in item.get("choices", []):
                    delta = choice.get("delta", {})
                    content = delta.get("content") or ""
                    reasoning = delta.get("reasoning_content") or delta.get("reasoning") or ""
                    if content or reasoning:
                        now = time.perf_counter()
                        first = now if first is None else first
                        last = now
                    if content:
                        text_parts.append(content)
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        elapsed = time.perf_counter() - start
        if not done or not usage:
            raise RuntimeError("Stream sin cierre o sin usage; no inventar tokens")
        prompt = int(usage["prompt_tokens"])
        completion = int(usage["completion_tokens"])
        if prompt + completion > context:
            raise RuntimeError("El consumo reportado supera el contexto descubierto")
        # Los chunks pueden agrupar tokens: esta tasa es una aproximacion cliente.
        decode = None
        if first is not None and last is not None and last > first and completion > 1:
            decode = (completion - 1) / (last - first)
        return {
            "tokenized_prompt_tokens": prompt_count,
            "prompt_tokens": prompt, "completion_tokens": completion,
            "total_tokens": int(usage["total_tokens"]),
            "usage": usage, "max_tokens": max_tokens,
            "prompt_count_matches": prompt_count == prompt,
            "context_headroom_reserved": context - prompt - max_tokens - margin,
            "elapsed_s": round(elapsed, 6),
            "ttft_s": round(first - start, 6) if first is not None else None,
            "decode_tokens_per_s_approx": round(decode, 3) if decode else None,
            "end_to_end_output_tokens_per_s": round(completion / elapsed, 3),
            "finish_reason": finish,
            "response_text": "".join(text_parts),
            "quality_evaluated": False,
        }


SYSTEM = (
    "Eres un asistente de laboratorio del harness de calendario. "
    "Todos los datos son sinteticos. No tienes herramientas ni acceso a agendas. "
    "No afirmes haber creado una cita. Sigue la tarea final en espanol."
)


def messages_for(rows, sample_id):
    records = "\n".join(
        f"Caso demo-{sample_id}-{i:04d}: asesor A; riesgo 0.80; "
        "duracion 15 minutos; zona America/Guayaquil; "
        "horario 09:00-12:00; requiere seguimiento."
        for i in range(rows)
    )
    task = (
        "\nTarea: redacta una guia operativa detallada con 30 pasos numerados "
        "para validar elegibilidad, disponibilidad, idempotencia, reserva, "
        "notificacion y recuperacion de errores. No copies todos los casos. "
        "No simules ejecucion de herramientas."
    )
    return [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": records + task}]


def fit_messages(client, target, sample_id):
    """Ajustar por tokenizador real, sin equivalencias palabras/tokens."""
    rows = 1
    messages = messages_for(rows, sample_id)
    count = client.count(messages)
    if count > target:
        raise ValueError("El prompt minimo excede el objetivo")
    # Una estimacion inicial y busqueda binaria; no genera tokens de salida.
    high = max(2, int(target / max(1, count) * 3))
    while client.count(messages_for(high, sample_id)) <= target:
        high *= 2
    low = 1
    while low + 1 < high:
        middle = (low + high) // 2
        if client.count(messages_for(middle, sample_id)) <= target:
            low = middle
        else:
            high = middle
    return messages_for(low, sample_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3, choices=range(1, 4))
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "reports/llm/qwen-medicion.json")
    parser.add_argument("--discover-only", action="store_true")
    args = parser.parse_args()
    client = QwenClient()
    report = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": client.model, "base_url": client.base,
        "hardware_reported_by_user": {"gpus": "4 x RTX 4000 (variante/VRAM sin verificar)",
                                      "ram_gb": 128},
        "settings": {"temperature": 0.3, "enable_thinking": False,
                     "concurrency": 1, "repeats": args.repeats},
        "samples": [], "errors": [],
        "limitations": ["Datos sinteticos; no benchmark de calidad ni de tool calling",
                        "TTFT incluye red, cola y prefill; no tasa pura de prefill",
                        "Caching y carga del servidor no controlados",
                        "No verifica uso efectivo de las cuatro GPU"],
    }

    def save():
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        selected = client.discover()
        context = selected["max_model_len"]
        margin = math.ceil(context * 0.10)
        report["discovered_model"] = selected
        report["context_tokens"] = context
        report["margin_tokens"] = margin
        save()
        print(f"Modelo: {client.model}; contexto: {context}; margen: {margin}", flush=True)
        if args.discover_only:
            return
        # Solo nueve generaciones por defecto, hasta 2 688 tokens de salida.
        # Si hay menor contexto, no lanzar perfiles que no quepan.
        profiles = [("corto", 1000, 128), ("medio", 3000, 256), ("largo", 5000, 512)]
        for repeat in range(args.repeats):
            for name, target, output_cap in profiles:
                if target + output_cap + margin > context:
                    report["errors"].append({"profile": name, "error": "Perfil no cabe"})
                    save()
                    continue
                messages = fit_messages(client, target, f"r{repeat}-{name}")
                measurement = client.stream(messages, output_cap, context, margin)
                measurement.update({"profile": name, "repeat": repeat + 1,
                                    "target_input_tokens": target})
                report["samples"].append(measurement)
                save()
                print(json.dumps({k: v for k, v in measurement.items()
                                  if k not in ("response_text", "usage")}), flush=True)
        summary = {}
        for name, _, _ in profiles:
            samples = [s for s in report["samples"] if s["profile"] == name]
            if samples:
                summary[name] = {"n": len(samples)}
                for field in ("prompt_tokens", "completion_tokens", "elapsed_s", "ttft_s",
                              "decode_tokens_per_s_approx", "end_to_end_output_tokens_per_s"):
                    values = [s[field] for s in samples if s[field] is not None]
                    if values:
                        summary[name][field] = {"min": min(values),
                                               "median": statistics.median(values),
                                               "max": max(values)}
        report["summary"] = summary
        report["status"] = "completed"
    except (HTTPError, OSError, ValueError, KeyError, RuntimeError) as exc:
        report["status"] = "failed"
        report["errors"].append({"type": type(exc).__name__, "message": str(exc)})
        save()
        raise
    finally:
        report["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()


if __name__ == "__main__":
    main()
