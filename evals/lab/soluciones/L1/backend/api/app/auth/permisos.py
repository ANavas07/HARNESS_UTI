"""Matriz de permisos (E4-T1): qué rol puede hacer cada acción. Es la ÚNICA fuente: los routers piden `exigir(usuario, accion)`
y una prueba recorre la matriz completa contra la API (una acción sin fila aquí rompe esa prueba)."""
from __future__ import annotations

from fastapi import HTTPException

from shared.contratos.enums import ROLES

PERMISOS: dict[str, frozenset[str]] = {
    "iniciar_corte": frozenset({"seguimiento", "admin"}),
    "reejecutar_corte": frozenset({"seguimiento", "admin"}),
    "ver_corte": frozenset({"seguimiento", "admin"}),
    "listar_alertas": frozenset({"seguimiento", "admin"}),
    "bandeja_seguimiento": frozenset({"seguimiento"}),
    "ver_caso": frozenset({"seguimiento", "bienestar"}),          # Bienestar: solo los que le derivaron
    "derivar_caso": frozenset({"seguimiento"}),                   # el agente y Bienestar nunca derivan
    "descartar_caso": frozenset({"seguimiento"}),
    "bandeja_bienestar": frozenset({"bienestar"}),
    "registrar_intervencion": frozenset({"bienestar"}),
    "cerrar_caso": frozenset({"seguimiento", "bienestar"}),
    "ver_estrategias": frozenset({"seguimiento", "bienestar", "admin"}),
    "revisar_estrategias": frozenset({"bienestar"}),               # Bienestar aprueba o retira lo que propone el agente
    "usar_chat": frozenset({"seguimiento", "bienestar"}),         # CU-9 del SPEC v0.2
    "ver_tablero": frozenset({"seguimiento", "bienestar", "admin"}),   # Bienestar: solo cifras de sus casos; nadie ve identidad
    "buscar_por_cedula": frozenset({"seguimiento", "bienestar"}),
    "exportar_resumen": frozenset({"seguimiento", "bienestar", "admin"}),
    "exportar_listados": frozenset({"seguimiento", "bienestar"}),      # con identidad: solo Seguimiento y confirmándolo
    "ver_notificaciones": frozenset({"seguimiento", "bienestar", "admin"}),     # admin: avisos de uso inusual
    "administrar_usuarios": frozenset({"admin"}),                               # §7.2 del v0.2: los roles los asigna Administración
    "administrar_modelos": frozenset({"admin"}),                                # §8.5 del v0.2: promoción manual
    "ver_operacion": frozenset({"admin"}),                                      # §7.7 del v0.2
    "ver_trazabilidad": frozenset({"admin"}),
    "ver_politica_agenda": frozenset({"admin"}),                                # Etapa 10: política vigente de la agenda
}
VEN_IDENTIDAD = frozenset({"seguimiento", "bienestar"})           # admin: nunca (SPEC v0.2, roles)

assert all(r in ROLES for roles in PERMISOS.values() for r in roles), "rol desconocido en la matriz de permisos"


def puede(rol: str, accion: str) -> bool:
    if accion not in PERMISOS:
        raise KeyError(f"acción sin fila en la matriz de permisos: {accion}")
    return rol in PERMISOS[accion]


def exigir(usuario, accion: str) -> None:
    if not puede(usuario.rol, accion):
        raise HTTPException(403, f"el rol {usuario.rol} no puede: {accion}")
