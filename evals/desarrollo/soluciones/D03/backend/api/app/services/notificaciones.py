"""Notificaciones dentro de la aplicación (E7-T5): avisos por rol a partir de los eventos de caso, sin datos personales.

  caso.derivado           → Bienestar: llegó un caso nuevo
  caso.escalado           → Seguimiento: riesgo persistente
  intervencion.registrada → Seguimiento: Bienestar actuó sobre un caso

Reprocesar un evento no duplica el aviso (clave única). Cada persona marca como leídos los avisos de su rol.
"""
from __future__ import annotations

import uuid

from psycopg.rows import dict_row, tuple_row

from api.app.services.casos import ErrorCaso, texto_libre

NIVEL = {"bajo": "bajo", "medio": "medio", "alto": "alto", "critico": "crítico"}
RESULTADO = {"contactado": "contactado", "no_contactado": "no se logró contactar", "acepto_apoyo": "aceptó el apoyo",
             "rechazo_apoyo": "rechazó el apoyo", "derivado_externo": "derivado a un servicio externo"}


def desde_evento(con, evento) -> bool:
    """Crea el aviso de un evento de caso. Devuelve si lo creó (False si ya existía)."""
    t = con.cursor(row_factory=tuple_row)                       # vale para cualquier conexión (el consumidor usa dict_row)
    nivel = t.execute("SELECT nivel FROM core.casos WHERE id = %s", (evento.caso_id,)).fetchone()
    nivel = nivel[0] if nivel else None
    if evento.TIPO == "caso.derivado":
        rol, tipo, texto = "bienestar", "caso_derivado", f"Seguimiento te derivó un caso de nivel {NIVEL.get(nivel or '', 'sin dato')}."
    elif evento.TIPO == "caso.escalado":
        rol, tipo, texto = "seguimiento", "caso_escalado", f"Un caso escaló: riesgo persistente en {evento.cortes_persistentes} cortes."
    elif evento.TIPO == "intervencion.registrada":
        resultado = RESULTADO.get(evento.resultado, evento.resultado)
        rol, tipo, texto = "seguimiento", "intervencion_registrada", f"Bienestar registró una intervención: {resultado}."
    else:
        raise ValueError(f"evento sin aviso: {evento.TIPO}")
    fila = t.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave) VALUES (%s, %s, %s, %s, %s) "
                     "ON CONFLICT (clave) DO NOTHING RETURNING id", (rol, tipo, evento.caso_id, texto, f"{tipo}:{evento.clave()}")).fetchone()
    return fila is not None


# Qué ve una persona (E10-T3): los avisos de su rol que no van dirigidos a nadie y los dirigidos a ella. Los obsoletos (una cita que
# se reprogramó o canceló) ya no se muestran ni cuentan.
VISIBLES = "((n.destinatario IS NULL AND n.rol = %(rol)s) OR (n.destinatario = %(usuario)s AND n.rol = %(rol)s)) AND NOT n.obsoleta"
TIPOS_AGENDA = ("cita_reservada", "cita_reprogramada", "cita_cancelada", "cita_sin_resultado", "solicitud_sin_asignar",
                "solicitud_sin_disponibilidad", "espera_excedida", "cita_recordatorio")


def listar(con, rol: str, usuario: str, limite: int = 50) -> list[dict]:
    return con.cursor(row_factory=dict_row).execute(
        "SELECT n.id, n.tipo, n.caso_id, n.texto, n.creado, (l.usuario IS NOT NULL) AS leida FROM core.notificaciones n "
        "LEFT JOIN core.notificaciones_leidas l ON l.notificacion_id = n.id AND l.usuario = %(usuario)s "
        f"WHERE {VISIBLES} ORDER BY (l.usuario IS NOT NULL), n.creado DESC LIMIT %(limite)s",
        {"rol": rol, "usuario": usuario, "limite": limite}).fetchall()


def sin_leer(con, rol: str, usuario: str) -> int:
    return int(con.cursor(row_factory=tuple_row).execute(
        f"SELECT count(*) FROM core.notificaciones n WHERE {VISIBLES} AND NOT EXISTS (SELECT 1 FROM core.notificaciones_leidas l "
        "WHERE l.notificacion_id = n.id AND l.usuario = %(usuario)s)", {"rol": rol, "usuario": usuario}).fetchone()[0])


def marcar_leida(con, notificacion_id: uuid.UUID, rol: str, usuario: str) -> None:
    fila = con.execute(f"SELECT 1 FROM core.notificaciones n WHERE n.id = %(id)s AND {VISIBLES}",
                       {"id": notificacion_id, "rol": rol, "usuario": usuario}).fetchone()
    if fila is None:
        raise ErrorCaso(404, "no existe el aviso")
    con.execute("INSERT INTO core.notificaciones_leidas (notificacion_id, usuario) VALUES (%s, %s) ON CONFLICT DO NOTHING", (notificacion_id, usuario))


def avisar_a(con, destinatario: str, tipo: str, caso_id, texto: str, clave: str) -> bool:
    """Aviso de la agenda dirigido a un profesional de Bienestar (P5). Reprocesar con la misma clave no lo duplica."""
    if tipo not in TIPOS_AGENDA:
        raise ValueError(f"tipo de aviso que no es de la agenda: {tipo}")
    texto = texto_libre(texto, "texto", 300)
    fila = con.execute("INSERT INTO core.notificaciones (rol, tipo, caso_id, texto, clave, destinatario) "
                       "VALUES ('bienestar', %s, %s, %s, %s, %s) ON CONFLICT (clave) DO NOTHING RETURNING id",
                       (tipo, caso_id, texto, clave, destinatario)).fetchone()
    return fila is not None
