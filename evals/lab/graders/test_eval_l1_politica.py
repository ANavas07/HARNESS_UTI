"""Grader oculto del eval L1 (contexto): GET /agenda/politica según el contrato de la tarea. El agente no ve este archivo."""
import psycopg
import pytest
from fastapi.testclient import TestClient

from api.app.main import crear_app
from api.app.services import politica_agenda
from shared.config.ajustes import Ajustes
from tests.claves import CLAVE_PRUEBA

CAMPOS = {"id", "policy_id", "version", "modo", "contenido", "aprobada_por", "aprobada_en"}


def cab(rol):
    return {"X-Usuario": f"{rol}.eval", "X-Rol": rol}


@pytest.fixture(scope="module")
def api(dsn_por_rol, tmp_path_factory):
    return TestClient(crear_app(Ajustes(dsn=dsn_por_rol["api"], almacen=tmp_path_factory.mktemp("alm"), entorno="desarrollo",
                                        identidad_clave=CLAVE_PRUEBA)))


@pytest.fixture(scope="module")
def con_admin(cluster):
    with psycopg.connect(cluster.dsn(), autocommit=True) as c:
        yield c


def test_sin_politica_vigente_responde_404(api, con_admin):
    con_admin.execute("UPDATE core.politicas_agenda SET estado = 'retirada' WHERE estado = 'aprobada'")
    assert api.get("/agenda/politica", headers=cab("admin")).status_code == 404


def test_administracion_recibe_la_politica_vigente_del_modo_demo(api, con_admin):
    with con_admin.transaction():
        vigente = politica_agenda.cargar_demo(con_admin)
    r = api.get("/agenda/politica", headers=cab("admin"))
    assert r.status_code == 200, r.text
    datos = r.json()
    assert CAMPOS <= set(datos)
    assert datos["id"] == str(vigente["id"]) and datos["modo"] == "demo" and datos["policy_id"] == "agenda-bienestar-demo"
    assert datos["version"] == vigente["version"] and datos["aprobada_por"] == "mvp_local"
    assert datos["contenido"]["schedule"]["duration_minutes"] == 15


@pytest.mark.parametrize("rol", ["seguimiento", "bienestar"])
def test_seguimiento_y_bienestar_no_pueden_usarlo(api, rol):
    assert api.get("/agenda/politica", headers=cab(rol)).status_code == 403


def test_en_produccion_no_devuelve_la_politica_demo(dsn_por_rol, tmp_path):
    """Fuera de desarrollo el modo es produccion: la política demo vigente no cuenta."""
    from api.app.auth.usuario import Usuario, usuario_actual
    app = crear_app(Ajustes(dsn=dsn_por_rol["api"], almacen=tmp_path, entorno="produccion", identidad_clave=CLAVE_PRUEBA))
    app.dependency_overrides[usuario_actual] = lambda: Usuario("admin.eval", "admin")   # sin Entra ID en la prueba
    assert TestClient(app).get("/agenda/politica").status_code == 404
