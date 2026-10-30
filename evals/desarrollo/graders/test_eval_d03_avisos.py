"""Grader oculto del eval D03: el tipo `cita_recordatorio` existe en la base, en el servicio y en la API, y ningún tipo de aviso
anterior se pierde (el fallo F1 de la fase 10.A). El agente no ve este archivo."""
import uuid
from datetime import datetime, timezone

import psycopg
import pytest

from api.app.esquemas import Aviso
from api.app.services import notificaciones

ANTERIORES = [("caso_derivado", True), ("caso_escalado", True), ("intervencion_registrada", True), ("uso_inusual", False),
              ("deriva", False), ("cita_reservada", True), ("cita_reprogramada", True), ("cita_cancelada", True),
              ("cita_sin_resultado", True), ("solicitud_sin_asignar", True), ("solicitud_sin_disponibilidad", True),
              ("espera_excedida", True)]


@pytest.fixture
def con(cluster):
    with psycopg.connect(cluster.dsn()) as c:
        yield c
        c.rollback()


@pytest.fixture
def con_api(dsn_por_rol):
    with psycopg.connect(dsn_por_rol["api"]) as c:
        yield c
        c.rollback()


def un_caso(con) -> uuid.UUID:
    corte = con.execute("INSERT INTO core.cortes (id, tipo_corte, periodo_id, ordinal) "
                        "SELECT gen_random_uuid(), 'fin', coalesce(max(periodo_id), 0) + 1, 1 FROM core.cortes RETURNING id").fetchone()[0]
    alerta = con.execute("INSERT INTO core.alertas (corte_id, matricula_id, p_desercion, nivel, modelo_id, umbrales_version) "
                         "VALUES (%s, 1, 0.9, 'alto', 'm0001', 1) RETURNING id", (corte,)).fetchone()[0]
    return con.execute("INSERT INTO core.casos (alerta_id, estado, persona_ref, nivel, prioridad) VALUES (%s, 'nuevo', %s, 'alto', 20) "
                       "RETURNING id", (alerta, f"p-{uuid.uuid4().hex[:10]}")).fetchone()[0]


@pytest.mark.parametrize("tipo,con_caso", ANTERIORES)
def test_ningun_tipo_de_aviso_anterior_se_pierde(con, tipo, con_caso):
    cid = un_caso(con) if con_caso else None
    con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave) VALUES ('bienestar', %s, %s, 'aviso', %s)",
                (tipo, cid, f"eval-d03:{tipo}:{uuid.uuid4()}"))


def test_la_agenda_crea_el_recordatorio_dirigido(con_api):
    cid = un_caso(con_api)
    assert notificaciones.avisar_a(con_api, "b.lopez", "cita_recordatorio", cid, "Mañana tienes una cita.", f"d03:{uuid.uuid4()}")
    assert [a["tipo"] for a in notificaciones.listar(con_api, "bienestar", "b.lopez") if a["caso_id"] == cid] == ["cita_recordatorio"]


def test_la_api_publica_el_tipo_nuevo():
    Aviso.model_validate({"id": uuid.uuid4(), "tipo": "cita_recordatorio", "caso_id": uuid.uuid4(), "texto": "x",
                          "creado": datetime.now(timezone.utc), "leida": False})
