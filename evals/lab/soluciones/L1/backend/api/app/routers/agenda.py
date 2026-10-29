"""Agenda de Bienestar (Etapa 10): consulta de la política vigente para Administración."""
import psycopg
from fastapi import APIRouter, Depends, HTTPException, Request
from psycopg.rows import dict_row

from api.app.auth.permisos import exigir
from api.app.auth.usuario import Usuario, usuario_actual
from api.app.esquemas import PoliticaAgendaVigente
from api.app.services import politica_agenda

router = APIRouter()


@router.get("/agenda/politica", response_model=PoliticaAgendaVigente)
def politica_vigente(request: Request, usuario: Usuario = Depends(usuario_actual)):
    exigir(usuario, "ver_politica_agenda")
    modo = "demo" if request.app.state.ajustes.entorno == "desarrollo" else "produccion"
    with psycopg.connect(request.app.state.ajustes.dsn, row_factory=dict_row) as con:
        vigente = politica_agenda.vigente(con, modo)
    if vigente is None:
        raise HTTPException(404, f"no hay una política de agenda vigente para el modo {modo}")
    return vigente
