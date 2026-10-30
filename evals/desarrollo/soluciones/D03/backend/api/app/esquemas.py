"""Modelos de respuesta de la API (E5-T1): son el contrato publicado (`frontend/openapi.json`) del que se generan los tipos del
frontend. FastAPI filtra cada respuesta a los campos declarados: un campo que no está aquí nunca sale, aunque la consulta lo
traiga. La cédula (`identificacion`) solo existe en los modelos de caso y llega vacía a quien no debe verla.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from shared.contratos.enums import EstadoCaso, FuentePropuesta, MotivoCierre, NivelAlerta, Perfil, ResultadoIntervencion, Rol, TipoAccion, TipoCorte


class Salud(BaseModel):
    estado: Literal["ok", "degradado"]
    servicio: str
    bd: str


class Yo(BaseModel):
    usuario: str
    rol: Rol
    acciones: list[str]
    entorno: str


class CorteCreado(BaseModel):
    corte_id: uuid.UUID
    creado: bool


class PeriodoDisponible(BaseModel):
    periodo_id: int
    ordinal: int
    inicio: date
    fin: date


class ListaPeriodos(BaseModel):
    periodos: list[PeriodoDisponible]


class EstadoCorte(BaseModel):
    id: uuid.UUID
    tipo_corte: TipoCorte
    periodo_id: int
    ordinal: int
    estado: str
    ejecuciones: int
    alertas_esperadas: int | None
    alertas_registradas: int
    finalizado: datetime | None
    creado: datetime
    eventos: dict[str, int]
    situacion: Literal["en_curso", "calculado", "fallido"]


class Reejecucion(BaseModel):
    eventos_reintentados: int


class Aporte(BaseModel):
    variable: str
    aporte: float


class Alerta(BaseModel):
    id: uuid.UUID
    corte_id: uuid.UUID
    matricula_id: int
    p_desercion: float
    nivel: NivelAlerta
    perfil: Perfil | None
    explicacion: list[Aporte]
    explicacion_texto: str
    modelo_id: str
    umbrales_version: int
    creado: datetime


class ListaAlertas(BaseModel):
    alertas: list[Alerta]


class CasoResumen(BaseModel):
    id: uuid.UUID
    estado: EstadoCaso
    nivel: NivelAlerta | None
    prioridad: int
    escalado: bool
    sin_atender: bool
    cortes_persistentes: int
    antiguedad_dias: int
    creado: datetime
    actualizado: datetime
    derivado_en: datetime | None
    motivo_cierre: MotivoCierre | None
    alerta_id: uuid.UUID
    matricula_id: int
    p_desercion: float
    perfil: Perfil | None
    explicacion: list[Aporte]
    explicacion_texto: str
    propuesta_tipo: str | None
    propuesta_texto: str | None
    propuesta_fuente: FuentePropuesta | None
    identificacion: str | None = None              # solo Seguimiento y Bienestar (matriz de permisos)


class ListaCasos(BaseModel):
    casos: list[CasoResumen]
    total: int = 0
    desplazamiento: int = 0
    limite: int = 200
    criticos: int = 0
    escalados: int = 0
    sin_atender: int = 0


class AlertaDeCaso(BaseModel):
    id: uuid.UUID
    corte_id: uuid.UUID
    nivel: NivelAlerta
    p_desercion: float
    perfil: Perfil | None
    explicacion: list[Aporte]
    explicacion_texto: str
    propuesta_texto: str | None
    creado: datetime


class EntradaHistorial(BaseModel):
    accion: str
    de_estado: str | None
    a_estado: str | None
    actor: str
    detalle: dict
    creado: datetime


class Intervencion(BaseModel):
    id: uuid.UUID
    tipo: TipoAccion
    tipo_otro: str
    resultado: ResultadoIntervencion
    observaciones: str
    registrado_por: str
    nivel_antes: str | None
    nivel_despues: str | None
    creado: datetime


class CasoDetalle(CasoResumen):
    alertas: list[AlertaDeCaso]
    historial: list[EntradaHistorial]
    intervenciones: list[Intervencion]


class ResultadoAccion(BaseModel):
    estado: EstadoCaso
    motivo_cierre: MotivoCierre | None = None


class IntervencionCreada(BaseModel):
    intervencion_id: uuid.UUID


class Evidencia(BaseModel):
    id: str
    titulo: str
    anio: int | None
    url: str


class Estrategia(BaseModel):
    id: uuid.UUID
    version: int
    perfil: Perfil
    motivo: str
    titulo: str
    accion: str
    tipo_intervencion: str
    responsable: Literal["seguimiento", "bienestar"]
    momento: str
    evidencia: list[Evidencia]
    nivel_evidencia: Literal["alta", "media", "baja", "sin_evidencia"]
    fuente: Literal["llm", "plantilla"]
    estado: Literal["borrador", "aprobada", "retirada"]
    generado_por: str
    creado: datetime
    revisado_por: str | None
    revisado_en: datetime | None
    motivo_revision: str | None


class ListaEstrategias(BaseModel):
    estrategias: list[Estrategia]


class ResultadoRevision(BaseModel):
    estado: Literal["aprobada", "retirada"]


class Conversacion(BaseModel):
    id: uuid.UUID
    creado: datetime
    titulo: str | None = None


class DatoGrafico(BaseModel):
    etiqueta: str
    valor: float | str


class Grafico(BaseModel):
    """Armado con el resultado de una herramienta (nunca con el texto del modelo)."""
    tipo: Literal["barras", "indicadores"]
    titulo: str
    unidad: str
    nota: str | None
    datos: list[DatoGrafico]


class EstadoChat(BaseModel):
    modo: Literal["llm", "basico", "no_disponible"]


class ListaConversaciones(BaseModel):
    conversaciones: list[Conversacion]


class MensajeChat(BaseModel):
    autor: Literal["usuario", "asistente", "herramienta"]
    contenido: str
    herramienta: str | None
    graficos: list[Grafico] = []
    a2ui: list[dict] = []
    creado: datetime
    trace_id: uuid.UUID | None = None


class HistorialChat(BaseModel):
    id: uuid.UUID
    mensajes: list[MensajeChat]


class RespuestaChat(BaseModel):
    respuesta: str
    herramientas: list[str]
    graficos: list[Grafico] = []
    a2ui: list[dict] = []
    modo: Literal["llm", "basico"] = "llm"
    trace_id: uuid.UUID | None = None


class EventoTraza(BaseModel):
    ts: datetime
    span_id: uuid.UUID | None = None
    parent_span_id: uuid.UUID | None = None
    operacion: str
    fase: Literal["inicio", "fin", "evento"]
    estado: Literal["ok", "error"] | None = None
    duracion_ms: float | None = None
    error_tipo: str | None = None
    modo: str | None = None
    resultado: str | None = None
    herramienta: str | None = None
    paso: int | None = None
    llamadas: int | None = None
    graficos: int | None = None
    registros: int | None = None


class TrazaResumen(BaseModel):
    id: uuid.UUID
    estado: Literal["pendiente", "ejecutando", "finalizado", "error"]
    creado: datetime
    actualizado: datetime


class TrazaDetalle(TrazaResumen):
    eventos: list[EventoTraza]
    disponible: bool
    truncada: bool


class ListaTrazas(BaseModel):
    trazas: list[TrazaResumen]
    total: int


class CorteTablero(BaseModel):
    id: uuid.UUID
    tipo_corte: TipoCorte
    periodo_id: int
    estado: str
    creado: datetime


class FiltrosTablero(BaseModel):
    carrera: str | None
    modalidad: str | None
    nivel: NivelAlerta | None


class AlertasTablero(BaseModel):
    total: int
    por_nivel: dict[str, int]
    por_perfil: dict[str, int]
    por_modalidad: dict[str, int]
    por_carrera: dict[str, int]


class CasosTablero(BaseModel):
    total: int
    por_estado: dict[str, int]
    escalados: int
    sin_atender: int
    derivados: int
    cobertura_intervencion: float | None
    dias_alerta_a_derivacion_mediana: float | None
    descartados: int
    tasa_descarte: float | None
    motivos_descarte: dict[str, int]


class Efectividad(BaseModel):
    intervenciones_medidas: int
    bajaron: int
    porcentaje_bajaron: float | None
    por_tipo: dict[str, dict[str, int]]
    nota: str


class PuntoEvolucion(BaseModel):
    periodo_id: int
    alertas: int
    criticos: int


class TasaCarrera(BaseModel):
    grupo: str
    estudiantes: int
    tasa_pct: float


class Tablero(BaseModel):
    """Sin corte del tipo pedido, solo `aviso`."""
    corte: CorteTablero | None
    aviso: str | None = None
    filtros: FiltrosTablero | None = None
    alertas: AlertasTablero | None = None
    casos: CasosTablero | None = None
    efectividad: Efectividad | None = None
    evolucion: list[PuntoEvolucion] = []
    tasas_por_carrera: list[TasaCarrera] = []


class CasoEncontrado(BaseModel):
    id: uuid.UUID
    estado: EstadoCaso
    nivel: NivelAlerta
    prioridad: int
    creado: datetime


class ResultadoBusqueda(BaseModel):
    """Vacío = la persona no está en seguimiento (o no es visible para el rol). Nunca devuelve la cédula."""
    casos: list[CasoEncontrado]


class Aviso(BaseModel):
    id: uuid.UUID
    tipo: Literal["caso_derivado", "caso_escalado", "intervencion_registrada", "uso_inusual", "deriva",
                  # avisos dirigidos de la agenda (E10-T3); la lista coincide con notificaciones.TIPOS_AGENDA
                  "cita_reservada", "cita_reprogramada", "cita_cancelada", "cita_sin_resultado", "solicitud_sin_asignar",
                  "solicitud_sin_disponibilidad", "espera_excedida", "cita_recordatorio"]
    caso_id: uuid.UUID | None                 # los avisos de uso inusual y de deriva no se refieren a un caso
    texto: str
    creado: datetime
    leida: bool


class ListaAvisos(BaseModel):
    avisos: list[Aviso]
    sin_leer: int


class AvisoLeido(BaseModel):
    estado: Literal["leida"]


class UsuarioSistema(BaseModel):
    id: uuid.UUID
    correo: str
    usuario: str
    rol: Rol
    activo: bool
    vinculado: bool
    creado_por: str
    creado: datetime
    actualizado: datetime
    ultimo_ingreso: datetime | None


class ListaUsuarios(BaseModel):
    usuarios: list[UsuarioSistema]


class ComparacionSombra(BaseModel):
    periodo_id: int
    estado_corte: str
    estado: Literal["ok", "fallo"]
    n_puntuados: int | None
    alertas_activo: int | None
    alertas_sombra: int | None
    en_comun: int | None
    p_media_activo: float | None
    p_media_sombra: float | None
    psi: float | None
    detalle: str
    activo_id: str
    creado: datetime


class EventoModelo(BaseModel):
    accion: str
    por: str
    motivo: str
    fecha: str


class Modelo(BaseModel):
    id: str
    tipo_corte: TipoCorte
    estado: Literal["candidato", "sombra", "activo", "retirado"]
    algoritmo: str | None
    metricas: dict
    verificaciones: dict
    registrado: datetime
    historial: list[EventoModelo]
    comparaciones: list[ComparacionSombra]
    cortes_en_sombra: int


class ListaModelos(BaseModel):
    modelos: list[Modelo]


class ResultadoModelo(BaseModel):
    estado: Literal["sombra", "activo", "retirado"]


class CorteOperacion(BaseModel):
    id: uuid.UUID
    tipo_corte: TipoCorte
    periodo_id: int
    estado: str
    creado: datetime
    finalizado: datetime | None
    ejecuciones: int
    alertas_esperadas: int | None
    alertas_registradas: int
    segundos: float | None


class ColaTipo(BaseModel):
    tipo: str
    estado: str
    n: int


class Cola(BaseModel):
    por_tipo: list[ColaTipo]
    pendientes: int
    muertos: int
    segundos_pendiente_mas_viejo: float | None
    hechos_24h: int


class ModeloEnUso(BaseModel):
    id: str
    tipo_corte: TipoCorte
    estado: str
    registrado: datetime


class ResumenCorteP(BaseModel):
    periodo_id: int
    modelo_id: str
    n: int
    p_media: float | None
    por_nivel: dict[str, int]


class Deriva(BaseModel):
    tipo_corte: TipoCorte
    ultimo: ResumenCorteP
    anterior: ResumenCorteP | None
    psi: float | None
    lectura: Literal["estable", "moderada", "fuerte"] | None
    umbral: float


class Operacion(BaseModel):
    cortes: list[CorteOperacion]
    cola: Cola
    modelos: list[ModeloEnUso]
    deriva: list[Deriva]
