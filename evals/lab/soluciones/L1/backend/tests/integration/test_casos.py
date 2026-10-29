"""Etapa 4: casos, Seguimiento, Bienestar, escalamiento, sin matrícula y permisos, contra PostgreSQL real y la API.

Cada prueba usa sus propios periodos y matrículas (bloques que no se cruzan con otras pruebas): no hace falta vaciar tablas, que
además son de solo agregar.
"""
import itertools
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from api.app.auth.permisos import PERMISOS
from api.app.main import crear_app
from api.app.services import casos
from api.app.services.identidades import SinSal, cargar, seudonimo
from shared.bus import Bus
from shared.cifrado import SinClave
from shared.config.ajustes import Ajustes
from shared.eventos import AlertaGenerada
from tests.claves import CIFRADOR, CLAVE_PRUEBA

SAL = "sal-de-pruebas"
_bloques = itertools.count(1)


def cab(rol, usuario=None):
    return {"X-Usuario": usuario or f"{rol}.prueba", "X-Rol": rol}


SEG, BIEN, ADM = cab("seguimiento"), cab("bienestar"), cab("admin")


@pytest.fixture(scope="module")
def api(dsn_por_rol, tmp_path_factory):
    return TestClient(crear_app(Ajustes(dsn=dsn_por_rol["api"], almacen=tmp_path_factory.mktemp("alm"), entorno="desarrollo", identidad_clave=CLAVE_PRUEBA)))


class Mundo:
    """Arma cortes, identidades y alertas de una prueba, en su propio bloque de periodos y matrículas."""

    def __init__(self, dsn_api, admin):
        b = next(_bloques)
        self.dsn, self.admin = dsn_api, admin
        self.periodo = 10_000 + 100 * b
        self.matricula = 9_000_000 + 10_000 * b
        self.bus = Bus(dsn_api, "pruebas")

    def corte(self, tipo="fin"):
        self.periodo += 1
        cid = uuid.uuid4()
        self.admin.execute("INSERT INTO core.cortes (id, tipo_corte, periodo_id, ordinal) VALUES (%s, %s, %s, 1)", (cid, tipo, self.periodo))
        return cid

    def persona(self, n_matriculas=4):
        """Una persona con identidad cargada y varias matrículas (una por periodo)."""
        cedula = f"17{uuid.uuid4().int % 10**8:08d}"
        ms = [self.matricula + i for i in range(n_matriculas)]
        self.matricula += n_matriculas
        with psycopg.connect(self.dsn) as con:
            cargar(con, [(m, cedula) for m in ms], SAL, CIFRADOR)
        return ms

    def alerta(self, corte, matricula, nivel="alto", tipo="fin", perfil=None):
        ev = AlertaGenerada(corte_id=corte, tipo_corte=tipo, matricula_id=matricula, p_desercion=0.8, nivel=nivel, perfil=perfil,
                            explicacion=[{"variable": "promedio_notas_nivel", "aporte": 1.2}], modelo_id="m0001", umbrales_version=1)
        with psycopg.connect(self.dsn) as con:
            return casos.registrar_alerta(con, ev, self.bus, "api.alertas")

    def caso_de(self, alerta_id):
        return self.admin.execute("SELECT caso_id FROM core.alertas WHERE id = %s", (alerta_id,)).fetchone()[0]

    def caso(self, caso_id):
        return self.admin.execute("SELECT estado, nivel, prioridad, escalado, sin_atender, cortes_persistentes, motivo_cierre "
                                  "FROM core.casos WHERE id = %s", (caso_id,)).fetchone()

    def accion(self, fn, *args):
        with psycopg.connect(self.dsn) as con, con.transaction():
            return fn(con, *args)

    def derivar(self, caso_id):
        self.accion(lambda con: casos.derivar(con, self.bus, caso_id, "seg.prueba"))

    def intervenir(self, caso_id, tipo="tutoria_academica", resultado="contactado"):
        return self.accion(lambda con: casos.registrar_intervencion(con, self.bus, caso_id, "bien.prueba", "bienestar", tipo, resultado))


@pytest.fixture
def mundo(dsn_por_rol, admin):
    return Mundo(dsn_por_rol["api"], admin)


# ---------------------------------------------------------------- E4-T3 identidades
def test_el_seudonimo_es_estable_con_la_sal_y_cambia_sin_ella():
    assert seudonimo("1712345678", "a") == seudonimo("171-234-5678", "a") != seudonimo("1712345678", "b")
    assert "1712345678" not in seudonimo("1712345678", "a")
    with pytest.raises(SinSal):
        seudonimo("1712345678", "")


def test_cargar_dos_veces_no_duplica_y_sin_sal_falla(dsn_por_rol, admin):
    filas = [(9_999_001, "0912345678"), (9_999_002, "0912345678")]          # misma persona, dos periodos
    with psycopg.connect(dsn_por_rol["api"]) as con:
        assert cargar(con, filas, SAL, CIFRADOR) == 2
        assert cargar(con, filas, SAL, CIFRADOR) == 0
        with pytest.raises(SinSal):
            cargar(con, filas, "", CIFRADOR)
        with pytest.raises(SinSal):                                          # falta de configuración, aunque no haya filas
            cargar(con, [], "", CIFRADOR)
        with pytest.raises(SinClave):                                        # E9-T5: sin clave no se carga identidad
            cargar(con, [(9_999_003, "0912345679")], SAL, None)
    guardadas = admin.execute("SELECT identificacion FROM pii.identidades WHERE matricula_id IN (9999001, 9999002)").fetchall()
    assert all(v.startswith("v1:") and "0912345678" not in v for (v,) in guardadas)          # E9-T5: se guarda cifrada
    shas = admin.execute("SELECT DISTINCT identificacion_sha FROM pii.identidades WHERE matricula_id IN (9999001, 9999002)").fetchall()
    assert len(shas) == 1


# ---------------------------------------------------------------- E4-T4 alerta → caso
def test_una_alerta_abre_un_caso_y_las_siguientes_de_la_persona_se_agregan(mundo):
    m = mundo.persona()
    c1, c2 = mundo.corte(), mundo.corte()
    a1 = mundo.alerta(c1, m[0], "medio")
    caso = mundo.caso_de(a1)
    assert mundo.caso(caso)[:3] == ("nuevo", "medio", casos.prioridad("medio", False, False))
    a2 = mundo.alerta(c2, m[1], "critico")                                   # otra matrícula, misma persona
    assert mundo.caso_de(a2) == caso
    assert mundo.caso(caso)[1] == "critico" and mundo.caso(caso)[2] >= casos.BASE_PRIORIDAD["critico"]
    assert mundo.alerta(c2, m[1], "critico") is None                         # repetir la alerta no hace nada
    assert mundo.admin.execute("SELECT count(*) FROM core.casos WHERE persona_ref = (SELECT persona_ref FROM core.alertas WHERE id = %s)",
                               (a1,)).fetchone()[0] == 1


def test_la_base_impide_dos_casos_abiertos_de_la_misma_persona(mundo):
    m = mundo.persona()
    a = mundo.alerta(mundo.corte(), m[0])
    with pytest.raises(psycopg.errors.UniqueViolation):
        mundo.admin.execute("INSERT INTO core.casos (alerta_id, persona_ref) SELECT %s, persona_ref FROM core.alertas WHERE id = %s", (a, a))


def test_cada_alerta_publica_alerta_registrada_sin_identidad(mundo):
    a = mundo.alerta(mundo.corte(), mundo.persona()[0], perfil="inicio_bajo_rendimiento")
    payload = mundo.admin.execute("SELECT payload FROM bus.eventos WHERE tipo = 'alerta.registrada' AND payload->>'alerta_id' = %s",
                                  (str(a),)).fetchone()[0]
    assert payload["perfil"] == "inicio_bajo_rendimiento" and "matricula_id" not in payload


# ---------------------------------------------------------------- E4-T2 CA3 inmutabilidad
def test_el_historial_y_las_intervenciones_no_se_modifican_ni_borran(mundo):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    mundo.derivar(caso)
    i = mundo.intervenir(caso)
    for sql in ("UPDATE core.historial_casos SET actor = 'x' WHERE caso_id = %s", "DELETE FROM core.historial_casos WHERE caso_id = %s",
                "UPDATE core.intervenciones SET resultado = 'no_contactado' WHERE caso_id = %s",
                "DELETE FROM core.intervenciones WHERE caso_id = %s"):
        with psycopg.connect(mundo.dsn) as con, pytest.raises(psycopg.errors.InsufficientPrivilege):
            con.execute(sql, (caso,))
    mundo.admin.execute("UPDATE core.intervenciones SET nivel_despues = 'bajo' WHERE id = %s", (i,))     # completar una vez: sí
    with pytest.raises(psycopg.errors.InsufficientPrivilege):
        mundo.admin.execute("UPDATE core.intervenciones SET nivel_despues = 'alto' WHERE id = %s", (i,))  # cambiarlo: no


# ---------------------------------------------------------------- E4-T5 Seguimiento
def test_derivar_publica_el_evento_y_solo_desde_nuevo(mundo, api):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    r = api.post(f"/casos/{caso}/derivar", json={"nota": "prioridad por asistencia"}, headers=SEG)
    assert r.status_code == 200 and mundo.caso(caso)[0] == "derivado"
    assert mundo.admin.execute("SELECT count(*) FROM bus.eventos WHERE tipo = 'caso.derivado' AND payload->>'caso_id' = %s",
                               (str(caso),)).fetchone()[0] == 1
    assert api.post(f"/casos/{caso}/derivar", json={}, headers=SEG).status_code == 409
    assert api.post(f"/casos/{caso}/descartar", json={"motivo": "ya atendido"}, headers=SEG).status_code == 409


@pytest.mark.parametrize("cuerpo, codigo", [({}, 422), ({"motivo": "   "}, 422), ({"motivo": "llamar al 0991234567"}, 422),
                                           ({"motivo": "dato duplicado del periodo"}, 200)])
def test_descartar_exige_un_motivo_sin_datos_personales(mundo, api, cuerpo, codigo):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    assert api.post(f"/casos/{caso}/descartar", json=cuerpo, headers=SEG).status_code == codigo
    assert mundo.caso(caso)[0] == ("cerrado" if codigo == 200 else "nuevo")
    if codigo == 200:
        assert mundo.caso(caso)[6] == "descartado"


def test_la_bandeja_ordena_por_prioridad_muestra_antiguedad_e_identidad_solo_a_quien_corresponde(mundo, api):
    c = mundo.corte()
    medio = mundo.caso_de(mundo.alerta(c, mundo.persona()[0], "medio"))
    critico = mundo.caso_de(mundo.alerta(c, mundo.persona()[0], "critico"))
    filas = api.get("/casos", params={"limite": 1000}, headers=SEG).json()["casos"]
    ids = [f["id"] for f in filas]
    assert ids.index(str(critico)) < ids.index(str(medio))
    fila = next(f for f in filas if f["id"] == str(critico))
    assert fila["antiguedad_dias"] == 0 and len(fila["identificacion"]) == 10 and fila["explicacion_texto"].startswith("Lo que más pesa")
    p = [f["prioridad"] for f in filas]
    assert p == sorted(p, reverse=True)


# ---------------------------------------------------------------- E4-T6 Bienestar
def test_bienestar_solo_ve_y_toca_lo_que_le_derivaron(mundo, api):
    c = mundo.corte()
    derivado = mundo.caso_de(mundo.alerta(c, mundo.persona()[0]))
    no_derivado = mundo.caso_de(mundo.alerta(c, mundo.persona()[0]))
    mundo.derivar(derivado)
    ids = {f["id"] for f in api.get("/bienestar/casos", params={"limite": 1000}, headers=BIEN).json()["casos"]}
    assert str(derivado) in ids and str(no_derivado) not in ids
    assert api.get(f"/casos/{no_derivado}", headers=BIEN).status_code == 404          # ni siquiera revela que existe
    cuerpo = {"tipo": "tutoria_academica", "resultado": "contactado"}
    assert api.post(f"/casos/{no_derivado}/intervenciones", json=cuerpo, headers=BIEN).status_code == 404
    assert api.post(f"/casos/{no_derivado}/cerrar", json={"motivo": "resuelto"}, headers=BIEN).status_code == 404
    assert api.get(f"/casos/{derivado}", headers=BIEN).status_code == 200


@pytest.mark.parametrize("cuerpo, codigo", [
    ({"tipo": "otro", "resultado": "contactado"}, 422),                                  # "otro" sin texto
    ({"tipo": "otro", "tipo_otro": "  ", "resultado": "contactado"}, 422),
    ({"tipo": "inventado", "resultado": "contactado"}, 422),                             # fuera de la lista
    ({"tipo": "bienestar", "resultado": "quizas"}, 422),
    ({"tipo": "bienestar", "resultado": "contactado", "observaciones": "su correo es ana@uni.edu.ec"}, 422),
    ({"tipo": "otro", "tipo_otro": "visita al hogar", "resultado": "acepto_apoyo"}, 201),
])
def test_las_intervenciones_validan_tipo_resultado_y_textos(mundo, api, cuerpo, codigo):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0], "alto"))
    mundo.derivar(caso)
    assert api.post(f"/casos/{caso}/intervenciones", json=cuerpo, headers=BIEN).status_code == codigo
    estado = mundo.caso(caso)[0]
    assert estado == ("en_intervencion" if codigo == 201 else "derivado")
    if codigo == 201:
        assert mundo.admin.execute("SELECT nivel_antes, registrado_por FROM core.intervenciones WHERE caso_id = %s", (caso,)).fetchone() == \
            ("alto", "bienestar.prueba")


def test_el_servicio_rechaza_tipos_fuera_de_la_lista_aunque_no_pase_por_la_api(mundo):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    mundo.derivar(caso)
    with pytest.raises(casos.ErrorCaso) as e:
        mundo.intervenir(caso, tipo="inventado")
    assert e.value.codigo == 422 and mundo.caso(caso)[0] == "derivado"


def test_cerrar_exige_un_motivo_de_la_lista_y_un_cerrado_no_se_reabre(mundo, api):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    mundo.derivar(caso)
    for motivo in ("porque si", "descartado"):
        assert api.post(f"/casos/{caso}/cerrar", json={"motivo": motivo}, headers=BIEN).status_code == 422
    assert api.post(f"/casos/{caso}/cerrar", json={"motivo": "resuelto"}, headers=BIEN).status_code == 200
    assert api.post(f"/casos/{caso}/cerrar", json={"motivo": "graduado"}, headers=SEG).status_code == 409
    assert api.post(f"/casos/{caso}/intervenciones", json={"tipo": "bienestar", "resultado": "contactado"}, headers=BIEN).status_code == 409
    assert mundo.caso(caso)[0] == "cerrado" and mundo.caso(caso)[6] == "resuelto"


# ---------------------------------------------------------------- E4-T8 escalamiento: tabla de verdad
@pytest.mark.parametrize("antes, despues, intervino, escalado, sin_atender", [
    ("medio", "medio", True, True, False), ("medio", "alto", True, True, False), ("alto", "critico", True, True, False),
    ("alto", "alto", False, False, True), ("medio", "critico", False, False, True),
    ("alto", "medio", True, False, False), ("critico", "alto", False, False, False),
])
def test_escalamiento_por_riesgo_persistente(mundo, antes, despues, intervino, escalado, sin_atender):
    m = mundo.persona()
    c1 = mundo.corte()
    caso = mundo.caso_de(mundo.alerta(c1, m[0], antes))
    mundo.derivar(caso)
    if intervino:
        mundo.intervenir(caso)
    c2 = mundo.corte()                                                       # el corte siguiente se pide DESPUÉS de intervenir
    assert mundo.caso_de(mundo.alerta(c2, m[1], despues)) == caso
    e = mundo.caso(caso)
    assert (e[3], e[4]) == (escalado, sin_atender)
    assert e[0] == ("en_intervencion" if intervino else "derivado")          # escalar nunca cambia el estado ni deriva
    assert e[2] == casos.prioridad(despues, escalado, sin_atender)
    n_escalados = mundo.admin.execute("SELECT count(*) FROM bus.eventos WHERE tipo = 'caso.escalado' AND payload->>'caso_id' = %s",
                                      (str(caso),)).fetchone()[0]
    assert n_escalados == int(escalado) and e[5] == (2 if escalado else 1)


def test_el_escalamiento_mira_solo_el_corte_anterior_del_mismo_tipo(mundo):
    m = mundo.persona()
    caso = mundo.caso_de(mundo.alerta(mundo.corte("fin"), m[0], "alto"))
    mundo.derivar(caso)
    mundo.intervenir(caso)
    mundo.alerta(mundo.corte("inicial"), m[1], "alto", tipo="inicial")       # otro tipo de corte: no hay cadena
    assert mundo.caso(caso)[3:5] == (False, False)


def test_la_prioridad_ordena_critico_escalado_sin_atender_y_nivel():
    p = casos.prioridad
    assert p("critico", False, False) > p("alto", True, False) > p("alto", False, True) > p("alto", False, False) > p("medio", True, True)
    assert p("medio", False, False) > p(None, False, False) == 0


def test_el_corte_no_se_cierra_hasta_que_llegan_todas_sus_alertas(mundo):
    c = mundo.corte()
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        casos.esperar_alertas(con, c, 2)                                     # el conteo puede llegar antes que las alertas
    mundo.alerta(c, mundo.persona()[0])
    assert mundo.admin.execute("SELECT finalizado FROM core.cortes WHERE id = %s", (c,)).fetchone()[0] is None
    a = mundo.alerta(c, mundo.persona()[0])
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        assert casos.finalizar_si_completo(con, c) is True
        assert casos.finalizar_si_completo(con, c) is False                 # ya cerrado: no se repite
    assert a is not None


def test_un_caso_nuevo_critico_tiene_prioridad_maxima_sin_esperar_dos_cortes(mundo):
    c = mundo.corte()
    critico = mundo.caso(mundo.caso_de(mundo.alerta(c, mundo.persona()[0], "critico")))
    alto_escalado = casos.prioridad("alto", True, False)
    assert critico[2] > alto_escalado and not critico[3]


def test_la_intervencion_recibe_el_nivel_del_corte_siguiente(mundo):
    m, otro = mundo.persona(), mundo.persona()
    c1 = mundo.corte()
    caso_a = mundo.caso_de(mundo.alerta(c1, m[0], "alto"))
    caso_b = mundo.caso_de(mundo.alerta(c1, otro[0], "alto"))
    for c in (caso_a, caso_b):
        mundo.derivar(c)
        mundo.intervenir(c)
    c2 = mundo.corte()
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        casos.registrar_matriculas(con, c2, [m[1], otro[1]], "api.alertas")
    mundo.alerta(c2, m[1], "medio")                                          # A sigue con alerta; B matriculada sin alerta
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        casos.esperar_alertas(con, c2, 1)
    nivel = lambda caso: mundo.admin.execute("SELECT nivel_despues FROM core.intervenciones WHERE caso_id = %s", (caso,)).fetchone()[0]  # noqa: E731
    assert (nivel(caso_a), nivel(caso_b)) == ("medio", "bajo")
    assert mundo.admin.execute("SELECT estado, finalizado IS NOT NULL FROM core.cortes WHERE id = %s", (c2,)).fetchone() == ("calculado", True)


# ---------------------------------------------------------------- E4-T9 sin matrícula, estado y re-ejecución del corte
def test_sin_matricula_y_reincorporacion(mundo):
    m, sigue = mundo.persona(), mundo.persona()
    c1 = mundo.corte()
    caso = mundo.caso_de(mundo.alerta(c1, m[0]))
    caso_sigue = mundo.caso_de(mundo.alerta(c1, sigue[0]))
    mundo.derivar(caso)
    c2 = mundo.corte()
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        casos.registrar_matriculas(con, c2, [sigue[1]], "api.alertas")       # la persona del caso no se matriculó
    assert mundo.caso(caso)[0] == "sin_matricula" and mundo.caso(caso_sigue)[0] == "nuevo"
    mundo.intervenir(caso)                                                   # el equipo mantiene el contacto
    assert mundo.caso(caso)[0] == "sin_matricula"
    c3 = mundo.corte()
    with psycopg.connect(mundo.dsn) as con, con.transaction():
        casos.registrar_matriculas(con, c3, [m[2], sigue[2]], "api.alertas")  # vuelve a matricularse
    assert mundo.caso(caso)[0] == "cerrado" and mundo.caso(caso)[6] == "reincorporado"


def test_reejecutar_un_corte_exige_motivo_reintenta_lo_fallido_y_queda_auditado(mundo, api):
    c = mundo.corte()
    mundo.admin.execute("INSERT INTO bus.eventos (id, tipo, version, clave, payload, estado) VALUES (gen_random_uuid(), 'features.listos', 1, "
                        "%s, %s, 'muerto')", (f"prueba:{c}", psycopg.types.json.Jsonb({"corte_id": str(c)})))
    assert api.get(f"/cortes/{c}", headers=ADM).json()["situacion"] == "fallido"
    assert api.post(f"/cortes/{c}/reejecutar", json={}, headers=ADM).status_code == 422
    assert api.post(f"/cortes/{c}/reejecutar", json={"motivo": "   "}, headers=ADM).status_code == 422
    r = api.post(f"/cortes/{c}/reejecutar", json={"motivo": "faltaba el archivo de notas"}, headers=ADM)
    assert r.status_code == 200 and r.json() == {"eventos_reintentados": 1}
    assert api.get(f"/cortes/{c}", headers=ADM).json()["ejecuciones"] == 2
    assert mundo.admin.execute("SELECT count(*) FROM audit.registro WHERE accion = 'reejecutar_corte' AND entidad_id = %s",
                               (str(c),)).fetchone()[0] == 1
    mundo.admin.execute("UPDATE core.cortes SET finalizado = now() WHERE id = %s", (c,))
    assert api.post(f"/cortes/{c}/reejecutar", json={"motivo": "otra vez"}, headers=ADM).status_code == 409
    assert api.get(f"/cortes/{uuid.uuid4()}", headers=ADM).status_code == 404


# ---------------------------------------------------------------- E4-T1 matriz de permisos completa
def _endpoints(caso, corte):
    return {
        "iniciar_corte": ("post", "/cortes", {"tipo_corte": "fin", "periodo_id": 1, "ordinal": 0}),
        "reejecutar_corte": ("post", f"/cortes/{corte}/reejecutar", {"motivo": "prueba"}),
        "ver_corte": ("get", f"/cortes/{corte}", None),
        "listar_alertas": ("get", f"/alertas?corte_id={corte}", None),
        "bandeja_seguimiento": ("get", "/casos", None),
        "ver_caso": ("get", f"/casos/{caso}", None),
        "derivar_caso": ("post", f"/casos/{caso}/derivar", {}),
        "descartar_caso": ("post", f"/casos/{caso}/descartar", {"motivo": "prueba"}),
        "bandeja_bienestar": ("get", "/bienestar/casos", None),
        "registrar_intervencion": ("post", f"/casos/{caso}/intervenciones", {"tipo": "bienestar", "resultado": "contactado"}),
        "cerrar_caso": ("post", f"/casos/{caso}/cerrar", {"motivo": "resuelto"}),
        "ver_estrategias": ("get", "/estrategias", None),
        "revisar_estrategias": ("post", f"/estrategias/{uuid.uuid4()}/retirar", {"motivo": "prueba"}),
        "usar_chat": ("post", "/chat/conversaciones", None),
        "ver_tablero": ("get", "/estadisticas", None),
        "buscar_por_cedula": ("post", "/casos/buscar", {"cedula": "0000000000"}),
        "exportar_resumen": ("get", "/reportes/pdf", None),
        "exportar_listados": ("get", "/reportes/excel?listados=casos", None),
        "ver_notificaciones": ("get", "/notificaciones", None),
        "administrar_usuarios": ("get", "/usuarios", None),
        "administrar_modelos": ("get", "/modelos", None),
        "ver_operacion": ("get", "/operacion", None),
        "ver_trazabilidad": ("get", "/trazabilidad/trazas", None),
        "ver_politica_agenda": ("get", "/agenda/politica", None),
    }


# la matriz del SPEC §4.1 / docs/arquitectura.md, escrita aparte: si alguien cambia PERMISOS, esta tabla no cambia con él
ESPERADO = {
    "iniciar_corte": {"seguimiento", "admin"}, "reejecutar_corte": {"seguimiento", "admin"}, "ver_corte": {"seguimiento", "admin"},
    "listar_alertas": {"seguimiento", "admin"}, "bandeja_seguimiento": {"seguimiento"}, "ver_caso": {"seguimiento", "bienestar"},
    "derivar_caso": {"seguimiento"}, "descartar_caso": {"seguimiento"}, "bandeja_bienestar": {"bienestar"},
    "registrar_intervencion": {"bienestar"}, "cerrar_caso": {"seguimiento", "bienestar"},
    "ver_estrategias": {"seguimiento", "bienestar", "admin"}, "revisar_estrategias": {"bienestar"}, "usar_chat": {"seguimiento", "bienestar"},
    "ver_tablero": {"seguimiento", "bienestar", "admin"}, "buscar_por_cedula": {"seguimiento", "bienestar"},
    "exportar_resumen": {"seguimiento", "bienestar", "admin"}, "exportar_listados": {"seguimiento", "bienestar"},
    "ver_notificaciones": {"seguimiento", "bienestar", "admin"}, "administrar_usuarios": {"admin"},
    "administrar_modelos": {"admin"}, "ver_operacion": {"admin"}, "ver_trazabilidad": {"admin"}, "ver_politica_agenda": {"admin"},
}


def test_toda_accion_de_la_matriz_tiene_su_endpoint_probado():
    assert set(_endpoints("x", "y")) == set(PERMISOS) == set(ESPERADO)
    assert {a: set(r) for a, r in PERMISOS.items()} == ESPERADO


@pytest.mark.parametrize("rol", ["seguimiento", "bienestar", "admin"])
@pytest.mark.parametrize("accion", sorted(ESPERADO))
def test_matriz_de_permisos(mundo, api, rol, accion):
    """Lo prohibido responde 403; lo permitido nunca 403 (puede ser 200, 404 o 409 según el estado del caso)."""
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    metodo, ruta, cuerpo = _endpoints(caso, mundo.corte())[accion]
    r = getattr(api, metodo)(ruta, headers=cab(rol), **({"json": cuerpo} if cuerpo is not None else {}))
    assert (r.status_code == 403) == (rol not in ESPERADO[accion]), (r.status_code, r.text)


def test_admin_nunca_recibe_identidad(mundo, api):
    c = mundo.corte()
    mundo.alerta(c, mundo.persona()[0])
    alertas = api.get("/alertas", params={"corte_id": str(c)}, headers=ADM).json()["alertas"]
    assert alertas and all("identificacion" not in a for a in alertas)


# ---------------------------------------------------------------- máquina de estados por propiedades
ACCIONES = st.lists(st.sampled_from(["derivar", "descartar", "intervenir", "cerrar"]), min_size=1, max_size=6)


@settings(max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(ACCIONES)
def test_ningun_caso_llega_a_bienestar_sin_seguimiento_ni_sale_de_cerrado(mundo, secuencia):
    caso = mundo.caso_de(mundo.alerta(mundo.corte(), mundo.persona()[0]))
    derivado_por_seguimiento, cerrado = False, False
    for a in secuencia:
        antes = mundo.caso(caso)[0]
        try:
            if a == "derivar":
                mundo.derivar(caso)
            elif a == "descartar":
                mundo.accion(lambda con: casos.descartar(con, caso, "seg.prueba", "prueba"))
            elif a == "intervenir":
                mundo.intervenir(caso)
            else:
                mundo.accion(lambda con: casos.cerrar(con, caso, "seg.prueba", "seguimiento", "resuelto"))
        except casos.ErrorCaso:
            assert mundo.caso(caso)[0] == antes                              # una acción rechazada no cambia nada
            continue
        derivado_por_seguimiento |= a == "derivar"
        despues = mundo.caso(caso)[0]
        assert not cerrado, "un caso cerrado cambió"
        if despues in ("derivado", "en_intervencion"):
            assert derivado_por_seguimiento
        cerrado = despues == "cerrado"
