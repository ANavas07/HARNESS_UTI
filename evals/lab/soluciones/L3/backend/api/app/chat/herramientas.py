"""Herramientas del chat (E6-T7): SOLO LECTURA, con el usuario de base de datos `app_chat_ro` (no puede leer `pii` ni escribir).
Cada herramienta declara qué roles la pueden usar y valida sus argumentos con un esquema; nunca devuelve la cédula.
Los números que da el chat salen de aquí: el LLM solo los redacta.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Callable, Literal

from psycopg.rows import dict_row
from pydantic import BaseModel, ConfigDict, Field

from shared.contratos.enums import Perfil
from shared.contratos.variables import DESCRIPCION_PERFIL

MIN_REGISTROS = 10          # con menos retiros no se informa una distribución de motivos


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArgsTasa(Args):
    dimension: Literal["carrera", "modalidad", "sede", "nivel", "global"] = Field(description="cómo agrupar")
    grupo: str | None = Field(default=None, max_length=80, description="texto a buscar dentro del grupo (p. ej. parte del nombre de la carrera)")


class ArgsMotivos(Args):
    modalidad: str | None = Field(default=None, max_length=40)
    carrera: str | None = Field(default=None, max_length=80)


class ArgsCorte(Args):
    tipo_corte: Literal["fin", "inicial"] = "fin"


class ArgsPerfil(Args):
    perfil: Perfil


class ArgsCaso(Args):
    caso_id: uuid.UUID


class ArgsFecha(Args):
    fecha: date = Field(description="día en hora de America/Guayaquil (YYYY-MM-DD)")


def _cur(con):
    return con.cursor(row_factory=dict_row)


def _patron(texto: str | None) -> str | None:
    return None if not texto else f"%{texto.strip()}%"


def tasa_desercion(con, rol: str, a: ArgsTasa) -> dict:
    filas = _cur(con).execute(
        "SELECT grupo, estudiantes, desertores, round((tasa * 100)::numeric, 1)::float AS tasa_pct, hasta_periodo FROM ml.tasas_historicas "
        "WHERE dimension = %s AND (%s::text IS NULL OR grupo ILIKE %s) ORDER BY estudiantes DESC LIMIT 10",
        (a.dimension, _patron(a.grupo), _patron(a.grupo))).fetchall()
    if not filas:
        return {"aviso": "no hay datos para ese grupo (o tiene menos de 10 estudiantes y no se publica)"}
    return {"resultados": filas, "nota": "tasa de deserción en periodos ya cerrados (los 4 periodos más recientes aún no se pueden afirmar)"}


def motivos_retiro(con, rol: str, a: ArgsMotivos) -> dict:
    filas = _cur(con).execute(
        "SELECT motivo, sum(registros)::int AS retiros FROM ml.motivos_retiro WHERE calidad = 'CAUSA IDENTIFICADA' "
        "AND (%s::text IS NULL OR modalidad ILIKE %s) AND (%s::text IS NULL OR carrera ILIKE %s) GROUP BY motivo ORDER BY retiros DESC",
        (_patron(a.modalidad), _patron(a.modalidad), _patron(a.carrera), _patron(a.carrera))).fetchall()
    total = sum(f["retiros"] for f in filas)
    if total < MIN_REGISTROS:
        return {"aviso": f"muy pocos retiros con motivo para concluir ({total})"}
    return {"total_retiros_con_motivo": total, "motivos": [{**f, "porcentaje": round(100 * f["retiros"] / total, 1)} for f in filas[:6]],
            "nota": "solo retiros FORMALES (aprox. una cuarta parte de la deserción); el abandono silencioso no declara motivo"}


def resumen_ultimo_corte(con, rol: str, a: ArgsCorte) -> dict:
    c = _cur(con).execute("SELECT id, periodo_id, estado, creado, finalizado FROM core.cortes WHERE tipo_corte = %s ORDER BY periodo_id DESC LIMIT 1",
                          (a.tipo_corte,)).fetchone()
    if c is None:
        return {"aviso": f"todavía no hay cortes de tipo {a.tipo_corte}"}
    niveles = dict(con.execute("SELECT nivel, count(*) FROM core.alertas WHERE corte_id = %s GROUP BY nivel", (c["id"],)).fetchall())
    perfiles = dict(con.execute("SELECT coalesce(perfil, 'sin_perfil'), count(*) FROM core.alertas WHERE corte_id = %s GROUP BY 1", (c["id"],)).fetchall())
    return {"periodo_id": c["periodo_id"], "estado": c["estado"], "pedido": str(c["creado"]), "alertas_por_nivel": niveles,
            "alertas_por_perfil": perfiles, "total_alertas": sum(niveles.values())}


def estrategias_para_grupo(con, rol: str, a: ArgsPerfil) -> dict:
    filas = _cur(con).execute("SELECT motivo, titulo, accion, responsable, momento, nivel_evidencia, evidencia FROM ml.estrategias "
                              "WHERE estado = 'aprobada' AND perfil = %s ORDER BY motivo", (a.perfil,)).fetchall()
    if not filas:
        return {"aviso": "Bienestar todavía no aprobó estrategias para este grupo"}
    return {"estrategias": [{**{k: v for k, v in f.items() if k != "evidencia"},
                             "fuentes": [f"{e.get('titulo')} ({e.get('anio')})" for e in (f["evidencia"] or [])][:3]} for f in filas]}


def describir_grupo(con, rol: str, a: ArgsPerfil) -> dict:
    return {"perfil": a.perfil, "descripcion": DESCRIPCION_PERFIL[a.perfil]}


def estado_caso(con, rol: str, a: ArgsCaso) -> dict:
    c = _cur(con).execute("SELECT id, estado, nivel, prioridad, escalado, sin_atender, derivado_por, extract(day FROM now() - creado)::int AS dias "
                          "FROM core.casos WHERE id = %s", (a.caso_id,)).fetchone()
    if c is None or (rol == "bienestar" and c["derivado_por"] is None):       # Bienestar: solo lo que le derivaron
        return {"error": "no existe el caso o no tienes acceso"}
    ultima = _cur(con).execute("SELECT tipo, resultado, creado::date::text AS fecha FROM core.intervenciones WHERE caso_id = %s ORDER BY creado DESC LIMIT 1",
                               (a.caso_id,)).fetchone()
    n = con.execute("SELECT count(*) FROM core.intervenciones WHERE caso_id = %s", (a.caso_id,)).fetchone()[0]
    return {"estado": c["estado"], "nivel": c["nivel"], "prioridad": c["prioridad"], "escalado": c["escalado"], "sin_atender": c["sin_atender"],
            "dias_abierto": c["dias"], "intervenciones": n, "ultima_intervencion": ultima}


def citas_por_profesional(con, rol: str, a: ArgsFecha) -> dict:
    # vista sin el seudónimo de la persona: app_chat_ro no puede leer core.citas
    filas = _cur(con).execute(
        "SELECT profesional, count(*)::int AS reservadas FROM core.v_citas_chat WHERE estado = 'reservada' "
        "AND (lower(rango) AT TIME ZONE 'America/Guayaquil')::date = %s GROUP BY profesional ORDER BY profesional", (a.fecha,)).fetchall()
    return {"fecha": a.fecha.isoformat(), "citas": filas}


@dataclass(frozen=True)
class Herramienta:
    nombre: str
    descripcion: str
    argumentos: type[Args]
    roles: frozenset[str]
    ejecutar: Callable[[object, str, Args], dict]

    def esquema(self) -> dict:
        return {"type": "function", "function": {"name": self.nombre, "description": self.descripcion,
                                                 "parameters": self.argumentos.model_json_schema()}}


AMBOS = frozenset({"seguimiento", "bienestar"})
HERRAMIENTAS = {h.nombre: h for h in [
    Herramienta("tasa_desercion", "Tasa histórica de deserción por carrera, modalidad, sede, nivel o de toda la universidad.", ArgsTasa, AMBOS,
                tasa_desercion),       # type: ignore[arg-type]
    Herramienta("motivos_retiro", "Motivos más frecuentes de los retiros formales, opcionalmente por modalidad o carrera.", ArgsMotivos, AMBOS,
                motivos_retiro),       # type: ignore[arg-type]
    Herramienta("resumen_ultimo_corte", "Resumen del último corte: alertas por nivel y por perfil.", ArgsCorte, AMBOS,
                resumen_ultimo_corte),  # type: ignore[arg-type]
    Herramienta("estrategias_para_grupo", "Estrategias de retención APROBADAS por Bienestar para un grupo, con sus fuentes.", ArgsPerfil, AMBOS,
                estrategias_para_grupo),  # type: ignore[arg-type]
    Herramienta("describir_grupo", "Qué caracteriza a un grupo (perfil) de estudiantes en riesgo.", ArgsPerfil, AMBOS,
                describir_grupo),      # type: ignore[arg-type]
    Herramienta("estado_caso", "Estado de un caso por su número (id): nivel, prioridad, marcas e intervenciones. Sin datos personales.",
                ArgsCaso, AMBOS, estado_caso),  # type: ignore[arg-type]
    Herramienta("citas_por_profesional", "Cuántas citas reservadas tiene cada profesional de Bienestar en un día.",
                ArgsFecha, frozenset({"bienestar"}), citas_por_profesional),  # type: ignore[arg-type]
]}


def permitidas(rol: str) -> list[Herramienta]:
    return [h for h in HERRAMIENTAS.values() if rol in h.roles]
