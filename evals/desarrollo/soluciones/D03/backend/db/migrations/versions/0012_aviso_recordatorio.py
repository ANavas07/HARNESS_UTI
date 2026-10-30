"""Aviso de recordatorio de cita (eval D03 del harness): agrega el tipo `cita_recordatorio` a core.notificaciones conservando
todos los tipos anteriores (los de la 0007 y los de la agenda de la 0011).

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-29
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

ANTERIORES = """'caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva',
  'cita_reservada', 'cita_reprogramada', 'cita_cancelada', 'cita_sin_resultado',
  'solicitud_sin_asignar', 'solicitud_sin_disponibilidad', 'espera_excedida'"""


def upgrade() -> None:
    op.execute(f"""
ALTER TABLE core.notificaciones DROP CONSTRAINT notificaciones_tipo_check;
ALTER TABLE core.notificaciones ADD CONSTRAINT notificaciones_tipo_check CHECK (tipo IN ({ANTERIORES}, 'cita_recordatorio'));
""")


def downgrade() -> None:
    op.execute(f"""
DELETE FROM core.notificaciones_leidas WHERE notificacion_id IN (SELECT id FROM core.notificaciones WHERE tipo = 'cita_recordatorio');
DELETE FROM core.notificaciones WHERE tipo = 'cita_recordatorio';
ALTER TABLE core.notificaciones DROP CONSTRAINT notificaciones_tipo_check;
ALTER TABLE core.notificaciones ADD CONSTRAINT notificaciones_tipo_check CHECK (tipo IN ({ANTERIORES}));
""")
