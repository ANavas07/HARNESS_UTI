"""Agenda de Bienestar (Etapa 10, E10-T1 a E10-T3): profesionales y equipos, política versionada, horarios, bloqueos,
solicitudes de cita, citas sin solapes por profesional ni por persona, operaciones idempotentes, historial de solo agregar,
profesional asignado al caso y avisos dirigidos. Esquema del contrato técnico de la agenda (HARNESS_UTI, §2).

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-28
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

UPGRADE = r"""
-- btree_gist es "trusted" desde PostgreSQL 13: la crea el dueño de la base. Permite mezclar = y && en una exclusión.
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------- equipos y profesionales
CREATE TABLE core.agenda_equipos (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre  text NOT NULL UNIQUE CHECK (length(btrim(nombre)) > 0),
  sede    text,
  creado  timestamptz NOT NULL DEFAULT now()
);
-- el profesional se identifica con el usuario corto del producto (en desarrollo no existe en core.usuarios: sin clave foránea)
CREATE TABLE core.agenda_profesionales (
  usuario     text PRIMARY KEY CHECK (usuario ~ '^[a-z0-9_.-]{3,40}$'),
  equipo_id   uuid REFERENCES core.agenda_equipos(id),
  coordina    boolean NOT NULL DEFAULT false,
  zona        text NOT NULL DEFAULT 'America/Guayaquil',
  habilitado  boolean NOT NULL DEFAULT true,
  version     integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  creado      timestamptz NOT NULL DEFAULT now(),
  actualizado timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT coordina_con_equipo CHECK (NOT coordina OR equipo_id IS NOT NULL)
);

-- ---------------------------------------------------------------- política versionada e inmutable una vez aprobada
CREATE TABLE core.politicas_agenda (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id    text NOT NULL,
  version      integer NOT NULL CHECK (version >= 1),
  modo         text NOT NULL CHECK (modo IN ('demo', 'piloto_interno', 'produccion')),
  estado       text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'aprobada', 'retirada')),
  contenido    jsonb NOT NULL,
  aprobada_por text,
  aprobada_en  timestamptz,
  creado       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_id, version),
  CONSTRAINT borrador_sin_aprobacion CHECK ((estado = 'borrador') = (aprobada_en IS NULL))
);
CREATE UNIQUE INDEX una_politica_aprobada_por_modo ON core.politicas_agenda (modo) WHERE estado = 'aprobada';
CREATE FUNCTION core.politica_inmutable() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'una política no se borra' USING ERRCODE = 'insufficient_privilege';
  END IF;
  IF OLD.estado <> 'borrador' AND NOT (OLD.estado = 'aprobada' AND NEW.estado = 'retirada'
       AND (to_jsonb(NEW) - 'estado') = (to_jsonb(OLD) - 'estado')) THEN
    RAISE EXCEPTION 'una política aprobada no se modifica: crea otra versión' USING ERRCODE = 'insufficient_privilege';
  END IF;
  RETURN NEW;
END $f$;
CREATE TRIGGER politica_inmutable BEFORE UPDATE OR DELETE ON core.politicas_agenda FOR EACH ROW EXECUTE FUNCTION core.politica_inmutable();

-- ---------------------------------------------------------------- horarios y bloqueos
CREATE TABLE core.agenda_horarios (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profesional   text NOT NULL REFERENCES core.agenda_profesionales(usuario),
  dia_iso       smallint NOT NULL CHECK (dia_iso BETWEEN 1 AND 7),
  inicio        time NOT NULL,
  fin           time NOT NULL,
  vigente_desde date NOT NULL,
  vigente_hasta date,
  creado        timestamptz NOT NULL DEFAULT now(),
  CHECK (inicio < fin),
  CHECK (vigente_hasta IS NULL OR vigente_desde <= vigente_hasta)
);
CREATE INDEX horarios_profesional ON core.agenda_horarios (profesional, dia_iso);

CREATE TABLE core.agenda_bloqueos (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  profesional text NOT NULL REFERENCES core.agenda_profesionales(usuario),
  rango       tstzrange NOT NULL CHECK (NOT isempty(rango) AND lower_inc(rango) AND NOT upper_inc(rango)),
  motivo      text NOT NULL CHECK (length(btrim(motivo)) > 0),
  creado_por  text NOT NULL,
  activo      boolean NOT NULL DEFAULT true,
  creado      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX bloqueos_rango ON core.agenda_bloqueos USING gist (profesional, rango) WHERE activo;

-- ---------------------------------------------------------------- solicitudes y citas
CREATE TABLE core.solicitudes_cita (
  id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id         uuid NOT NULL REFERENCES core.casos(id),
  derivado_en     timestamptz NOT NULL,
  estado          text NOT NULL DEFAULT 'pendiente' CHECK (estado IN
                    ('pendiente', 'pendiente_asignacion', 'agendada', 'sin_disponibilidad', 'cancelada_por_caso', 'requiere_revision')),
  motivo          text,
  profesional     text REFERENCES core.agenda_profesionales(usuario),
  prioridad       smallint NOT NULL,
  nivel           text NOT NULL CHECK (nivel IN ('medio', 'alto', 'critico')),
  intentos        smallint NOT NULL DEFAULT 0 CHECK (intentos >= 0),
  proximo_intento timestamptz,
  aviso_espera    boolean NOT NULL DEFAULT false,
  version         integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  creado          timestamptz NOT NULL DEFAULT now(),
  actualizado     timestamptz NOT NULL DEFAULT now(),
  UNIQUE (caso_id, derivado_en)
);
CREATE INDEX solicitudes_cola ON core.solicitudes_cita (profesional, estado, prioridad DESC, derivado_en, caso_id);

CREATE TABLE core.citas (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  solicitud_id       uuid NOT NULL REFERENCES core.solicitudes_cita(id),
  caso_id            uuid NOT NULL REFERENCES core.casos(id),
  persona_ref        text NOT NULL,
  profesional        text NOT NULL REFERENCES core.agenda_profesionales(usuario),
  rango              tstzrange NOT NULL,
  rango_ocupado      tstzrange NOT NULL,
  zona               text NOT NULL,
  estado             text NOT NULL DEFAULT 'reservada' CHECK (estado IN ('reservada', 'cancelada', 'finalizada')),
  motivo_cancelacion text,
  politica_id        uuid NOT NULL REFERENCES core.politicas_agenda(id),
  intervencion_id    uuid REFERENCES core.intervenciones(id),
  version            integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  creado             timestamptz NOT NULL DEFAULT now(),
  actualizado        timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT rango_semiabierto CHECK (lower_inc(rango) AND NOT upper_inc(rango)),
  CONSTRAINT dura_15_minutos CHECK (upper(rango) - lower(rango) = interval '15 minutes'),
  CONSTRAINT ocupado_contiene_rango CHECK (rango_ocupado @> rango),
  CONSTRAINT cancelada_con_motivo CHECK ((estado = 'cancelada') = (motivo_cancelacion IS NOT NULL)),
  CONSTRAINT sin_solape_profesional EXCLUDE USING gist (profesional WITH =, rango_ocupado WITH &&) WHERE (estado = 'reservada'),
  CONSTRAINT sin_solape_persona EXCLUDE USING gist (persona_ref WITH =, rango_ocupado WITH &&) WHERE (estado = 'reservada')
);
CREATE UNIQUE INDEX una_cita_activa_por_caso ON core.citas (caso_id) WHERE estado = 'reservada';
CREATE INDEX citas_profesional ON core.citas USING gist (profesional, rango);
CREATE INDEX citas_caso ON core.citas (caso_id);

CREATE TABLE core.operaciones_agenda (
  ambito       text NOT NULL,
  clave        text NOT NULL,
  hash_comando text NOT NULL,
  estado       text NOT NULL CHECK (estado IN ('confirmada', 'fallida')),
  resultado    jsonb NOT NULL,
  creado       timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ambito, clave)
);

CREATE TABLE core.eventos_cita (
  id           bigserial PRIMARY KEY,
  cita_id      uuid REFERENCES core.citas(id),
  solicitud_id uuid REFERENCES core.solicitudes_cita(id),
  accion       text NOT NULL,
  de_estado    text,
  a_estado     text,
  actor        text NOT NULL,
  detalle      jsonb NOT NULL DEFAULT '{}',
  creado       timestamptz NOT NULL DEFAULT now(),
  CHECK (cita_id IS NOT NULL OR solicitud_id IS NOT NULL)
);
CREATE TRIGGER eventos_cita_sin_modificar BEFORE UPDATE OR DELETE ON core.eventos_cita FOR EACH ROW EXECUTE FUNCTION core.solo_agregar();
CREATE TRIGGER eventos_cita_sin_vaciar BEFORE TRUNCATE ON core.eventos_cita FOR EACH STATEMENT EXECUTE FUNCTION core.solo_agregar();

-- ---------------------------------------------------------------- profesional asignado (P3) y avisos dirigidos (P5)
ALTER TABLE core.casos ADD COLUMN asignado_a text CONSTRAINT asignado_a_usuario CHECK (asignado_a ~ '^[a-z0-9_.-]{3,40}$');
ALTER TABLE core.notificaciones ADD COLUMN destinatario text;
ALTER TABLE core.notificaciones ADD COLUMN obsoleta boolean NOT NULL DEFAULT false;
ALTER TABLE core.notificaciones DROP CONSTRAINT notificaciones_tipo_check;
ALTER TABLE core.notificaciones ADD CONSTRAINT notificaciones_tipo_check CHECK (tipo IN (
  'caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva',     -- tipos vigentes desde la 0007
  'cita_reservada', 'cita_reprogramada', 'cita_cancelada', 'cita_sin_resultado',
  'solicitud_sin_asignar', 'solicitud_sin_disponibilidad', 'espera_excedida'));
CREATE INDEX notificaciones_destinatario ON core.notificaciones (destinatario, creado DESC) WHERE destinatario IS NOT NULL;

-- ---------------------------------------------------------------- el chat lee citas sin el seudónimo de la persona
CREATE VIEW core.v_citas_chat AS
  SELECT id, caso_id, profesional, rango, zona, estado, version FROM core.citas;

-- ---------------------------------------------------------------- permisos (nadie borra: las cancelaciones cambian estado)
GRANT SELECT, INSERT, UPDATE ON core.agenda_equipos, core.agenda_profesionales, core.politicas_agenda, core.agenda_horarios,
  core.agenda_bloqueos, core.solicitudes_cita, core.citas, core.operaciones_agenda TO app_api;
GRANT SELECT, INSERT ON core.eventos_cita TO app_api;
GRANT USAGE ON SEQUENCE core.eventos_cita_id_seq TO app_api;
GRANT SELECT ON core.agenda_equipos, core.agenda_profesionales, core.agenda_horarios, core.agenda_bloqueos,
  core.solicitudes_cita, core.v_citas_chat TO app_chat_ro;
"""

DOWNGRADE = r"""
DROP VIEW core.v_citas_chat;

-- avisos de agenda: se borran antes de restaurar la lista de tipos de la 0007
DELETE FROM core.notificaciones_leidas WHERE notificacion_id IN (
  SELECT id FROM core.notificaciones WHERE tipo NOT IN ('caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva'));
DELETE FROM core.notificaciones WHERE tipo NOT IN ('caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva');
ALTER TABLE core.notificaciones DROP CONSTRAINT notificaciones_tipo_check;
ALTER TABLE core.notificaciones ADD CONSTRAINT notificaciones_tipo_check
  CHECK (tipo IN ('caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva'));
DROP INDEX core.notificaciones_destinatario;
ALTER TABLE core.notificaciones DROP COLUMN obsoleta, DROP COLUMN destinatario;
ALTER TABLE core.casos DROP COLUMN asignado_a;

DROP TABLE core.eventos_cita;
DROP TABLE core.operaciones_agenda;
DROP TABLE core.citas;
DROP TABLE core.solicitudes_cita;
DROP TABLE core.agenda_bloqueos;
DROP TABLE core.agenda_horarios;
DROP TABLE core.politicas_agenda;
DROP FUNCTION core.politica_inmutable();
DROP TABLE core.agenda_profesionales;
DROP TABLE core.agenda_equipos;
-- btree_gist se conserva: vive en public y otra migración podría usarla
"""


def upgrade() -> None:
    op.execute(UPGRADE)


def downgrade() -> None:
    op.execute(DOWNGRADE)
