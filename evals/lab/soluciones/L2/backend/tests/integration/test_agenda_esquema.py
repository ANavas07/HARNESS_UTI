"""Esquema de la agenda (E10-T1): la base impide citas solapadas, dobles citas activas y cambios a lo que es de solo agregar."""
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
from alembic import command
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.integration.conftest import alembic_cfg
from tests.integration.test_migraciones import foto

BASE_DIA = datetime(2026, 11, 5, 14, 0, tzinfo=timezone.utc)          # jueves 09:00 en Guayaquil


@pytest.fixture
def con(cluster):
    """Cada prueba en una transacción que se deshace: no deja datos para las demás."""
    with psycopg.connect(cluster.dsn()) as c:
        yield c
        c.rollback()


def caso(con, persona="p1", nivel="critico", prioridad=30) -> uuid.UUID:
    corte = con.execute("INSERT INTO core.cortes (id, tipo_corte, periodo_id, ordinal) "
                        "SELECT gen_random_uuid(), 'fin', coalesce(max(periodo_id), 0) + 1, 1 FROM core.cortes RETURNING id").fetchone()[0]
    alerta = con.execute("INSERT INTO core.alertas (corte_id, matricula_id, p_desercion, nivel, modelo_id, umbrales_version) "
                         "VALUES (%s, 1, 0.9, %s, 'm0001', 1) RETURNING id", (corte, nivel)).fetchone()[0]
    return con.execute("INSERT INTO core.casos (alerta_id, estado, persona_ref, nivel, prioridad, derivado_por, derivado_en) "
                       "VALUES (%s, 'derivado', %s, %s, %s, 'seguimiento.1', now()) RETURNING id",
                       (alerta, persona, nivel, prioridad)).fetchone()[0]


def profesional(con, usuario="b.lopez"):
    con.execute("INSERT INTO core.agenda_profesionales (usuario) VALUES (%s) ON CONFLICT DO NOTHING", (usuario,))
    return usuario


def politica(con) -> uuid.UUID:
    fila = con.execute("SELECT id FROM core.politicas_agenda WHERE policy_id = 'prueba'").fetchone()
    if fila:
        return fila[0]
    return con.execute("INSERT INTO core.politicas_agenda (policy_id, version, modo, estado, contenido, aprobada_por, aprobada_en) "
                       "VALUES ('prueba', 1, 'demo', 'aprobada', '{}', 'admin', now()) RETURNING id").fetchone()[0]


def solicitud_de(con, caso_id, prof="b.lopez") -> uuid.UUID:
    """La solicitud de la derivación vigente del caso, creándola si aún no existe."""
    fila = con.execute("SELECT s.id FROM core.solicitudes_cita s JOIN core.casos c ON c.id = s.caso_id AND c.derivado_en = s.derivado_en "
                       "WHERE s.caso_id = %s", (caso_id,)).fetchone()
    return fila[0] if fila else solicitud(con, caso_id, prof)


def solicitud(con, caso_id, prof="b.lopez") -> uuid.UUID:
    return con.execute("INSERT INTO core.solicitudes_cita (caso_id, derivado_en, prioridad, nivel, profesional) "
                       "SELECT id, derivado_en, prioridad, nivel, %s FROM core.casos WHERE id = %s RETURNING id", (prof, caso_id)).fetchone()[0]


def cita(con, caso_id, inicio: datetime, prof="b.lopez", minutos=15, margen=0, estado="reservada"):
    persona = con.execute("SELECT persona_ref FROM core.casos WHERE id = %s", (caso_id,)).fetchone()[0]
    profesional(con, prof)
    fin = inicio + timedelta(minutes=minutos)
    ocupado = (inicio - timedelta(minutes=margen), fin + timedelta(minutes=margen))
    motivo = "prueba" if estado == "cancelada" else None
    return con.execute(
        "INSERT INTO core.citas (solicitud_id, caso_id, persona_ref, profesional, rango, rango_ocupado, zona, politica_id, estado, "
        "motivo_cancelacion) VALUES (%s, %s, %s, %s, tstzrange(%s, %s, '[)'), tstzrange(%s, %s, '[)'), 'America/Guayaquil', %s, %s, %s) "
        "RETURNING id",
        (solicitud_de(con, caso_id, prof), caso_id, persona, prof, inicio, fin, *ocupado, politica(con), estado, motivo),
    ).fetchone()[0]


def rechaza(con, fn, *args, **kwargs):
    """La base rechaza la operación (savepoint: la transacción de la prueba sigue viva)."""
    with pytest.raises(psycopg.errors.IntegrityError):
        with con.transaction():
            fn(con, *args, **kwargs)


# ---------------------------------------------------------------- CA1: reversible
@pytest.fixture(scope="module")
def base_agenda(cluster):
    with psycopg.connect(cluster.dsn(base="postgres"), autocommit=True) as c:
        c.execute("DROP DATABASE IF EXISTS agenda_migracion")
        c.execute("CREATE DATABASE agenda_migracion")
    return cluster.dsn(base="agenda_migracion"), alembic_cfg(cluster.url_sqlalchemy(base="agenda_migracion"))


def test_bajar_la_agenda_y_volver_a_subirla_deja_el_mismo_esquema(base_agenda):
    dsn, cfg = base_agenda
    command.upgrade(cfg, "head")
    antes = foto(dsn)
    command.downgrade(cfg, "0010")
    sin_agenda = foto(dsn)
    assert not any(c[1] in ("citas", "solicitudes_cita", "agenda_profesionales") for c in sin_agenda["columnas"])
    assert not any(c[2] in ("asignado_a", "destinatario", "obsoleta") for c in sin_agenda["columnas"])
    command.upgrade(cfg, "head")
    assert foto(dsn) == antes


def test_bajar_con_avisos_de_agenda_no_deja_tipos_huerfanos(base_agenda):
    dsn, cfg = base_agenda
    command.upgrade(cfg, "head")
    with psycopg.connect(dsn, autocommit=True) as c:
        cid = caso(c)
        c.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave, destinatario) "
                  "VALUES ('bienestar', 'cita_reservada', %s, 'Nueva cita', 'k-agenda', 'b.lopez')", (cid,))
    command.downgrade(cfg, "0010")
    command.upgrade(cfg, "head")


# ---------------------------------------------------------------- CA2 y CA3: citas
def test_adyacentes_se_aceptan_y_un_minuto_de_margen_las_vuelve_incompatibles(con):
    cita(con, caso(con, "p1"), BASE_DIA)
    cita(con, caso(con, "p2"), BASE_DIA + timedelta(minutes=15))                      # [09:00, 09:15) y [09:15, 09:30)
    rechaza(con, cita, caso(con, "p3"), BASE_DIA + timedelta(minutes=30), margen=1)   # su margen invade 09:29


def test_el_mismo_profesional_no_tiene_dos_citas_solapadas(con):
    cita(con, caso(con, "p1"), BASE_DIA)
    rechaza(con, cita, caso(con, "p2"), BASE_DIA + timedelta(minutes=5))


def test_la_misma_persona_no_tiene_dos_citas_solapadas_ni_con_otro_profesional(con):
    """El producto ya impide dos casos abiertos por persona; la exclusión cubre una cita que quedó activa de un caso cerrado
    (la divergencia que corrige la conciliación) mientras la persona tiene un caso nuevo."""
    anterior = caso(con, "p1")
    cita(con, anterior, BASE_DIA)
    con.execute("UPDATE core.casos SET estado = 'cerrado', motivo_cierre = 'resuelto' WHERE id = %s", (anterior,))
    rechaza(con, cita, caso(con, "p1", nivel="alto", prioridad=20), BASE_DIA + timedelta(minutes=5), prof="b.mora")


def test_un_caso_tiene_a_lo_sumo_una_cita_activa(con):
    c = caso(con)
    cita(con, c, BASE_DIA)
    rechaza(con, cita, c, BASE_DIA + timedelta(days=1))


def test_una_cita_cancelada_libera_la_franja_y_el_caso(con):
    c = caso(con)
    cita(con, c, BASE_DIA, estado="cancelada")
    cita(con, c, BASE_DIA)                                                           # mismo caso, misma franja


@pytest.mark.parametrize("minutos", [10, 14, 16, 30])
def test_una_cita_dura_exactamente_15_minutos(con, minutos):
    rechaza(con, cita, caso(con), BASE_DIA, minutos=minutos)


@pytest.mark.parametrize("limites", ["[]", "(]", "()"])
def test_una_cita_es_un_rango_semiabierto(con, limites):
    """[inicio, fin): con un extremo cerrado, dos citas adyacentes se solaparían en un instante."""
    c = caso(con)
    profesional(con)
    with pytest.raises(psycopg.errors.IntegrityError), con.transaction():
        con.execute("INSERT INTO core.citas (solicitud_id, caso_id, persona_ref, profesional, rango, rango_ocupado, zona, politica_id) "
                    "VALUES (%s, %s, 'p1', 'b.lopez', tstzrange(%s, %s, %s), tstzrange(%s, %s, '[]'), 'America/Guayaquil', %s)",
                    (solicitud(con, c), c, BASE_DIA, BASE_DIA + timedelta(minutes=15), limites, BASE_DIA - timedelta(minutes=1),
                     BASE_DIA + timedelta(minutes=16), politica(con)))


def test_cancelar_exige_motivo(con):
    cid = cita(con, caso(con), BASE_DIA)
    with pytest.raises(psycopg.errors.IntegrityError), con.transaction():
        con.execute("UPDATE core.citas SET estado = 'cancelada' WHERE id = %s", (cid,))


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(a=st.integers(0, 480), b=st.integers(0, 480), margen=st.sampled_from([0, 5, 10]))
def test_la_exclusion_coincide_con_un_oraculo_independiente(con, a, b, margen):
    """Para dos citas del mismo profesional, la base acepta la segunda si y solo si los rangos con margen no se cruzan."""
    with con.transaction(force_rollback=True):
        i1, i2 = BASE_DIA + timedelta(minutes=a), BASE_DIA + timedelta(minutes=b)
        cita(con, caso(con, "p1"), i1, margen=margen)
        ocupado = lambda i: (i - timedelta(minutes=margen), i + timedelta(minutes=15 + margen))  # noqa: E731
        (x1, y1), (x2, y2) = ocupado(i1), ocupado(i2)
        se_cruzan = x1 < y2 and x2 < y1
        if se_cruzan:
            rechaza(con, cita, caso(con, "p2"), i2, margen=margen)
        else:
            cita(con, caso(con, "p2"), i2, margen=margen)


# ---------------------------------------------------------------- CA4: solo agregar e inmutables
def test_los_eventos_de_cita_no_se_modifican_ni_se_borran(con):
    cid = cita(con, caso(con), BASE_DIA)
    con.execute("INSERT INTO core.eventos_cita (cita_id, accion, actor) VALUES (%s, 'reservar', 'planificador')", (cid,))
    for sql in ("UPDATE core.eventos_cita SET actor = 'x'", "DELETE FROM core.eventos_cita"):
        with pytest.raises(psycopg.errors.InsufficientPrivilege), con.transaction():
            con.execute(sql)


def test_una_politica_aprobada_no_cambia_pero_se_puede_retirar(con):
    pid = politica(con)
    with pytest.raises(psycopg.errors.InsufficientPrivilege), con.transaction():
        con.execute("UPDATE core.politicas_agenda SET contenido = '{\"x\": 1}' WHERE id = %s", (pid,))
    con.execute("UPDATE core.politicas_agenda SET estado = 'retirada' WHERE id = %s", (pid,))


def test_solo_hay_una_politica_aprobada_por_modo(con):
    politica(con)
    with pytest.raises(psycopg.errors.UniqueViolation), con.transaction():
        con.execute("INSERT INTO core.politicas_agenda (policy_id, version, modo, estado, contenido, aprobada_por, aprobada_en) "
                    "VALUES ('otra', 1, 'demo', 'aprobada', '{}', 'admin', now())")


def test_una_solicitud_por_caso_y_derivacion(con):
    c = caso(con)
    profesional(con)
    solicitud(con, c)
    rechaza(con, solicitud, c)


def test_coordinar_exige_equipo(con):
    with pytest.raises(psycopg.errors.CheckViolation), con.transaction():
        con.execute("INSERT INTO core.agenda_profesionales (usuario, coordina) VALUES ('c.ruiz', true)")


# ---------------------------------------------------------------- cambios en tablas existentes
def test_los_avisos_admiten_destinatario_y_tipos_de_agenda(con):
    cid = caso(con)
    con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave, destinatario) "
                "VALUES ('bienestar', 'cita_reservada', %s, 'Nueva cita', 'k1', 'b.lopez')", (cid,))
    assert con.execute("SELECT obsoleta FROM core.notificaciones WHERE clave = 'k1'").fetchone()[0] is False


@pytest.mark.parametrize("tipo,con_caso", [("caso_derivado", True), ("caso_escalado", True), ("intervencion_registrada", True),
                                           ("uso_inusual", False), ("deriva", False)])
def test_los_tipos_de_aviso_anteriores_siguen_validos(con, tipo, con_caso):
    """Regresión: la agenda amplía la lista de tipos; no puede perder ninguno de las etapas 7 a 9 (p. ej. 'deriva' de la 0007)."""
    cid = caso(con) if con_caso else None
    con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave) VALUES ('admin', %s, %s, 'aviso', %s)",
                (tipo, cid, f"regresion:{tipo}"))


def test_un_caso_admite_un_profesional_asignado_con_formato_valido(con):
    cid = caso(con)
    con.execute("UPDATE core.casos SET asignado_a = 'b.lopez' WHERE id = %s", (cid,))
    with pytest.raises(psycopg.errors.CheckViolation), con.transaction():
        con.execute("UPDATE core.casos SET asignado_a = 'Nombre Con Espacios' WHERE id = %s", (cid,))


# ---------------------------------------------------------------- CA5: permisos
def test_solo_la_api_escribe_y_el_chat_no_ve_el_seudonimo(dsn_por_rol, cluster):
    with psycopg.connect(cluster.dsn(), autocommit=True) as c:
        cid = cita(c, caso(c, "p-permisos"), BASE_DIA + timedelta(days=30), prof="b.permisos")
    try:
        with psycopg.connect(dsn_por_rol["chat_ro"]) as c:
            assert c.execute("SELECT count(*) FROM core.v_citas_chat WHERE id = %s", (cid,)).fetchone()[0] == 1
            columnas = [d.name for d in c.execute("SELECT * FROM core.v_citas_chat LIMIT 0").description]
            assert "persona_ref" not in columnas
        with psycopg.connect(dsn_por_rol["chat_ro"]) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT persona_ref FROM core.citas")
        with psycopg.connect(dsn_por_rol["worker"]) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT 1 FROM core.citas")
        with psycopg.connect(dsn_por_rol["chat_ro"]) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("INSERT INTO core.agenda_profesionales (usuario) VALUES ('intruso')")
        with psycopg.connect(dsn_por_rol["api"]) as c, pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("DELETE FROM core.citas WHERE id = %s", (cid,))
    finally:
        with psycopg.connect(cluster.dsn(), autocommit=True) as c:      # limpiar: la prueba usa autocommit
            c.execute("UPDATE core.citas SET estado = 'cancelada', motivo_cancelacion = 'limpieza' WHERE id = %s", (cid,))
