"""Trazas locales por proceso, correlacionadas y con metadatos de lista cerrada.

No registra inputs/outputs, credenciales, estado del grafo ni texto de excepciones.
LLM_TRAZAS=0 desactiva; LLM_TRAZAS_DIR cambia el directorio de archivos JSONL.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Callable, ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")
_contexto: contextvars.ContextVar[tuple[str, str | None] | None] = contextvars.ContextVar("traza_llm", default=None)
_lock = threading.Lock()
_fallo_reportado = False
DIRECTORIO = Path(__file__).resolve().parents[1] / "data" / "logs"
OPERACIONES = {"chat.request", "chat.agent", "chat.basico", "chat.modelo", "chat.herramientas", "chat.tool", "chat.decision",
               "llm.conversar", "llm.http", "intervencion.proponer", "intervencion.fallback", "estrategias.agent",
               *(f"estrategias.{n}" for n in ("contexto", "planificar", "buscar", "evaluar", "reformular", "sintetizar", "verificar"))}
ENUMS = {
    "modo": {"llm", "basico", "no_disponible", "nativo", "json"},
    "resultado": {"ejecutada", "denegada", "argumentos_invalidos", "pii_bloqueada", "verificacion", "respuesta",
                  "solicita_herramientas", "limite_pasos", "reglas", "plantilla", "llm", "llm_error"},
    "herramienta": {"tasa_desercion", "motivos_retiro", "resumen_ultimo_corte", "estrategias_para_grupo", "describir_grupo", "estado_caso",
                    "citas_por_profesional"},
}
CONTADORES = {"paso", "mensajes", "herramientas", "llamadas", "graficos", "registros", "respuesta_caracteres"}


def _seguros(datos: dict) -> dict:
    return {k: v for k, v in datos.items() if
            (k in CONTADORES and type(v) is int and 0 <= v <= 10_000_000) or
            (k in ENUMS and isinstance(v, str) and v in ENUMS[k])}


def _escribir(fila: dict) -> None:
    global _fallo_reportado
    if os.environ.get("LLM_TRAZAS", "1").lower() in {"0", "false", "no"}:
        return
    try:
        directorio = Path(os.environ.get("LLM_TRAZAS_DIR") or DIRECTORIO)
        with _lock:
            directorio.mkdir(parents=True, exist_ok=True)
            archivo = directorio / f"llm-trazas-{os.getpid()}.jsonl"
            if archivo.exists() and archivo.stat().st_size >= 5 * 1024 * 1024:
                anterior = archivo.with_name(archivo.name + ".1")
                if anterior.exists():
                    anterior.replace(archivo.with_name(archivo.name + ".2"))
                archivo.replace(anterior)
            with archivo.open("a", encoding="utf-8") as salida:
                salida.write(json.dumps(fila, ensure_ascii=False) + "\n")
    except (OSError, ValueError):
        if not _fallo_reportado:
            _fallo_reportado = True
            logging.getLogger(__name__).warning("No se pudieron escribir las trazas locales; el aplicativo continúa.")


def _fila(operacion: str, fase: str, **datos) -> dict:
    contexto = _contexto.get()
    return {"ts": datetime.now(timezone.utc).isoformat(), "pid": os.getpid(),
            "trace_id": contexto[0] if contexto else str(uuid.uuid4()), "span_id": contexto[1] if contexto else None,
            "operacion": operacion if operacion in OPERACIONES else "desconocida", "fase": fase, **_seguros(datos)}


@contextmanager
def contexto_traza(trace_id: uuid.UUID):
    """Asocia un ID generado y autorizado por la API."""
    token = _contexto.set((str(trace_id), None))
    try:
        yield
    finally:
        _contexto.reset(token)


def leer_eventos(trace_id: uuid.UUID, proceso: int | None, limite: int = 2000) -> tuple[list[dict], bool]:
    """Lectura filtrada por ID y proceso; una línea parcial no invalida el resto."""
    if proceso is None:
        return [], False
    directorio = Path(os.environ.get("LLM_TRAZAS_DIR") or DIRECTORIO)
    filas = []
    for archivo in directorio.glob(f"llm-trazas-{int(proceso)}.jsonl*"):
        if archivo.is_symlink():
            continue
        try:
            with archivo.open(encoding="utf-8", errors="replace") as entrada:
                for linea in entrada:
                    try:
                        r = json.loads(linea)
                        if (not isinstance(r, dict) or r.get("trace_id") != str(trace_id) or
                                r.get("operacion") not in OPERACIONES or r.get("fase") not in {"inicio", "fin", "evento"}):
                            continue
                        fecha = datetime.fromisoformat(r["ts"])
                        if fecha.tzinfo is None:
                            continue
                        fila = {"ts": fecha.isoformat(), "operacion": r["operacion"], "fase": r["fase"],
                                "span_id": str(uuid.UUID(r["span_id"])) if r.get("span_id") else None,
                                "parent_span_id": str(uuid.UUID(r["parent_span_id"])) if r.get("parent_span_id") else None,
                                **_seguros(r)}
                        if r.get("estado") in {"ok", "error"}:
                            fila["estado"] = r["estado"]
                        ms = r.get("duracion_ms")
                        if isinstance(ms, (int, float)) and not isinstance(ms, bool) and 0 <= ms <= 86_400_000:
                            fila["duracion_ms"] = ms
                        if r.get("error_tipo") in {"ErrorLLM", "SalidaConDatosPersonales", "ValueError", "ValidationError", "HTTPException",
                                                 "TimeoutError", "ConnectionError", "KeyboardInterrupt", "Error"}:
                            fila["error_tipo"] = r["error_tipo"]
                        filas.append(fila)
                    except (ValueError, KeyError, TypeError):
                        continue
        except OSError:
            continue
    filas.sort(key=lambda fila: fila["ts"])
    return filas[:limite], len(filas) > limite


@contextmanager
def tramo(operacion: str, **datos):
    previo = _contexto.get()
    trace_id = previo[0] if previo else str(uuid.uuid4())
    token = _contexto.set((trace_id, str(uuid.uuid4())))
    parent = previo[1] if previo else None
    resumen = _seguros(datos)
    inicio = time.perf_counter()
    _escribir({**_fila(operacion, "inicio", **resumen), "parent_span_id": parent})
    estado, error = "ok", None
    try:
        yield resumen
    except BaseException as exc:
        estado = "error"
        nombre = type(exc).__name__
        error = nombre if nombre in {"ErrorLLM", "SalidaConDatosPersonales", "ValueError", "ValidationError", "HTTPException",
                                    "TimeoutError", "ConnectionError", "KeyboardInterrupt"} else "Error"
        raise
    finally:
        fila = {**_fila(operacion, "fin", **resumen), "parent_span_id": parent, "estado": estado,
                "duracion_ms": round((time.perf_counter() - inicio) * 1000, 3)}
        if error:
            fila["error_tipo"] = error
        _escribir(fila)
        _contexto.reset(token)


def evento(operacion: str, **datos) -> None:
    _escribir(_fila(operacion, "evento", **datos))


def trazado(operacion: str) -> Callable[[Callable[P, T]], Callable[P, T]]:
    def decorar(funcion: Callable[P, T]) -> Callable[P, T]:
        @wraps(funcion)
        def ejecutar(*args: P.args, **kwargs: P.kwargs) -> T:
            with tramo(operacion) as resumen:
                resultado = funcion(*args, **kwargs)
                if isinstance(resultado, dict):
                    for campo in ("graficos", "registros", "llamadas"):
                        if isinstance(resultado.get(campo), list):
                            resumen[campo] = len(resultado[campo])
                    if isinstance(resultado.get("respuesta"), str):
                        resumen["respuesta_caracteres"] = len(resultado["respuesta"])
                return resultado
        return ejecutar
    return decorar
