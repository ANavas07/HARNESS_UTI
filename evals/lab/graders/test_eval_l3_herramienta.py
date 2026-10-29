"""Grader oculto del eval L3 (herramientas): citas_por_profesional con la tool tipada y app_chat_ro. El agente no ve este archivo."""
import uuid
from datetime import datetime, timezone

import psycopg
import pytest
from pydantic import ValidationError

from api.app.chat import herramientas

NOMBRE = "citas_por_profesional"
SUFIJO = uuid.uuid4().hex[:6]
P1, P2 = f"b.uno{SUFIJO}", f"b.dos{SUFIJO}"


def h():
    assert NOMBRE in herramientas.HERRAMIENTAS, "la herramienta no está registrada"
    return herramientas.HERRAMIENTAS[NOMBRE]


def test_registrada_solo_para_bienestar():
    assert h().roles == frozenset({"bienestar"})
    assert NOMBRE in [x.nombre for x in herramientas.permitidas("bienestar")]
    assert NOMBRE not in [x.nombre for x in herramientas.permitidas("seguimiento")]


@pytest.mark.parametrize("args", [{"fecha": "2026-13-45"}, {"fecha": "jueves"}, {}, {"fecha": "2026-11-05", "extra": 1}])
def test_argumentos_invalidos_los_rechaza_el_esquema(args):
    with pytest.raises(ValidationError):
        h().argumentos.model_validate(args)


def test_las_trazas_reconocen_la_herramienta():
    from shared.trazas import ENUMS
    assert NOMBRE in ENUMS["herramienta"]


def _caso(con, persona):
    corte = con.execute("INSERT INTO core.cortes (id, tipo_corte, periodo_id, ordinal) "
                        "SELECT gen_random_uuid(), 'fin', coalesce(max(periodo_id), 0) + 1, 1 FROM core.cortes RETURNING id").fetchone()[0]
    alerta = con.execute("INSERT INTO core.alertas (corte_id, matricula_id, p_desercion, nivel, modelo_id, umbrales_version) "
                         "VALUES (%s, 1, 0.9, 'alto', 'm0001', 1) RETURNING id", (corte,)).fetchone()[0]
    return con.execute("INSERT INTO core.casos (alerta_id, estado, persona_ref, nivel, prioridad, derivado_por, derivado_en) "
                       "VALUES (%s, 'derivado', %s, 'alto', 20, 'seg.eval', now()) RETURNING id", (alerta, persona)).fetchone()[0]


def _cita(con, prof, inicio_utc, estado="reservada"):
    caso = _caso(con, f"p-{uuid.uuid4().hex[:10]}")
    pol = con.execute("SELECT id FROM core.politicas_agenda WHERE policy_id = 'eval-l3'").fetchone()
    pol = pol[0] if pol else con.execute("INSERT INTO core.politicas_agenda (policy_id, version, modo, estado, contenido, aprobada_por, "
                                         "aprobada_en) VALUES ('eval-l3', 1, 'piloto_interno', 'aprobada', '{}', 'eval', now()) "
                                         "RETURNING id").fetchone()[0]
    sol = con.execute("INSERT INTO core.solicitudes_cita (caso_id, derivado_en, prioridad, nivel, profesional) "
                      "SELECT id, derivado_en, 20, 'alto', %s FROM core.casos WHERE id = %s RETURNING id", (prof, caso)).fetchone()[0]
    con.execute("INSERT INTO core.citas (solicitud_id, caso_id, persona_ref, profesional, rango, rango_ocupado, zona, politica_id, estado, "
                "motivo_cancelacion) SELECT %s, id, persona_ref, %s, tstzrange(%s, %s + interval '15 minutes', '[)'), "
                "tstzrange(%s, %s + interval '15 minutes', '[)'), 'America/Guayaquil', %s, %s, %s FROM core.casos WHERE id = %s",
                (sol, prof, inicio_utc, inicio_utc, inicio_utc, inicio_utc, pol, estado, "eval" if estado == "cancelada" else None, caso))


@pytest.fixture(scope="module")
def datos(cluster):
    u = lambda *a: datetime(*a, tzinfo=timezone.utc)                       # noqa: E731
    with psycopg.connect(cluster.dsn(), autocommit=True) as con:
        con.execute("INSERT INTO core.agenda_profesionales (usuario) VALUES (%s), (%s)", (P1, P2))
        _cita(con, P1, u(2026, 11, 5, 14, 0))                               # jueves 09:00 local
        _cita(con, P1, u(2026, 11, 5, 15, 0))                               # jueves 10:00 local
        _cita(con, P1, u(2026, 11, 6, 4, 30))                               # jueves 23:30 local: cuenta para el jueves
        _cita(con, P1, u(2026, 11, 5, 16, 0), estado="cancelada")           # cancelada: no cuenta
        _cita(con, P2, u(2026, 11, 5, 4, 45))                               # miércoles 23:45 local: no cuenta
        _cita(con, P2, u(2026, 11, 6, 15, 0))                               # viernes: no cuenta


def test_cuenta_las_reservadas_del_dia_local_con_el_usuario_de_solo_lectura(dsn_por_rol, datos):
    with psycopg.connect(dsn_por_rol["chat_ro"]) as con:
        r = h().ejecutar(con, "bienestar", h().argumentos.model_validate({"fecha": "2026-11-05"}))
    propias = [c for c in r["citas"] if c["profesional"] in (P1, P2)]
    assert r["fecha"] == "2026-11-05"
    assert propias == [{"profesional": P1, "reservadas": 3}]


def test_un_dia_sin_citas_devuelve_una_lista_vacia(dsn_por_rol, datos):
    with psycopg.connect(dsn_por_rol["chat_ro"]) as con:
        r = h().ejecutar(con, "bienestar", h().argumentos.model_validate({"fecha": "2026-11-02"}))
    assert r == {"fecha": "2026-11-02", "citas": []}
