"""Grader oculto del eval L2 (entorno): ningún tipo de aviso anterior a la agenda se pierde. El agente no ve este archivo."""
import uuid

import psycopg
import pytest


@pytest.fixture
def con(cluster):
    with psycopg.connect(cluster.dsn()) as c:
        yield c
        c.rollback()


def un_caso(con) -> uuid.UUID:
    corte = con.execute("INSERT INTO core.cortes (id, tipo_corte, periodo_id, ordinal) "
                        "SELECT gen_random_uuid(), 'fin', coalesce(max(periodo_id), 0) + 1, 1 FROM core.cortes RETURNING id").fetchone()[0]
    alerta = con.execute("INSERT INTO core.alertas (corte_id, matricula_id, p_desercion, nivel, modelo_id, umbrales_version) "
                         "VALUES (%s, 1, 0.9, 'alto', 'm0001', 1) RETURNING id", (corte,)).fetchone()[0]
    return con.execute("INSERT INTO core.casos (alerta_id, estado, persona_ref, nivel, prioridad) VALUES (%s, 'nuevo', %s, 'alto', 20) "
                       "RETURNING id", (alerta, f"p-{uuid.uuid4().hex[:10]}")).fetchone()[0]


@pytest.mark.parametrize("tipo,con_caso", [("caso_derivado", True), ("caso_escalado", True), ("intervencion_registrada", True),
                                           ("uso_inusual", False), ("deriva", False)])
def test_los_tipos_de_aviso_anteriores_a_la_agenda_siguen_validos(con, tipo, con_caso):
    cid = un_caso(con) if con_caso else None
    con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave) VALUES ('admin', %s, %s, 'aviso', %s)",
                (tipo, cid, f"eval-l2:{tipo}:{uuid.uuid4()}"))


def test_los_tipos_de_la_agenda_siguen_disponibles(con):
    cid = un_caso(con)
    con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave) VALUES ('bienestar', 'cita_reservada', %s, 'aviso', %s)",
                (cid, f"eval-l2:agenda:{uuid.uuid4()}"))
