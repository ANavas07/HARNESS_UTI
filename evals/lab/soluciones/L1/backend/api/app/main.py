"""API de la plataforma (E2-T8). Es la única que escribe en `core` y la única que lee `pii`."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.app.auth.entra import ValidadorEntra
from api.app.routers import agenda, alertas, busqueda, casos, chat, cortes, estrategias, modelos, notificaciones, salud, sesion, tablero, usuarios
from shared.bus import Bus
from shared.cifrado import Cifrador
from shared.config.ajustes import Ajustes
from shared.llm import ClienteLLM


def crear_app(ajustes: Ajustes | None = None) -> FastAPI:
    ajustes = ajustes or Ajustes.desde_entorno()
    app = FastAPI(title="Permanencia y acompañamiento", docs_url="/docs" if ajustes.entorno == "desarrollo" else None,
                  redoc_url=None)
    app.state.ajustes = ajustes
    app.state.bus = Bus(ajustes.dsn, "api")
    app.state.llm = ClienteLLM.desde_entorno()                # None = chat no disponible (las pantallas siguen)
    app.state.cifrador = Cifrador(ajustes.identidad_clave) if ajustes.identidad_clave else None   # E9-T5: sin clave no se muestra la cédula
    app.state.entra = ValidadorEntra(ajustes.entra_tenant, ajustes.entra_audiencia) if ajustes.entra_tenant else None
    if ajustes.cors_origenes:                         # E5-T2: solo los orígenes configurados (en Docker, mismo origen: ninguno)
        app.add_middleware(CORSMiddleware, allow_origins=list(ajustes.cors_origenes), allow_methods=["GET", "POST"],
                           allow_headers=["Content-Type", "Authorization", "X-Usuario", "X-Rol"], allow_credentials=False)
    # busqueda antes que casos
    for r in (salud, sesion, cortes, alertas, busqueda, casos, estrategias, chat, tablero, notificaciones, usuarios, modelos, agenda):
        app.include_router(r.router)
    return app
