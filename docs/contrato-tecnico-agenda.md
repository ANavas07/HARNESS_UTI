# Contrato técnico de la agenda (Etapa 10)

Versión 1.3 — 29 de octubre de 2026. Complementa el [SPEC v0.8](SPEC.md) y la [propuesta de la Etapa 10](propuesta-etapa-10-agenda.md). El SPEC dice **qué** debe pasar; este documento fija **cómo** se implementa en el producto de deserción (opción A): esquema de base, cambios en funciones existentes, eventos, endpoints, errores, política, algoritmos, herramientas y datos de prueba.

Se basa en el código del producto revisado el 28 de octubre de 2026 (commit `fd64df2`). Si el producto cambia esas piezas, este contrato se revisa antes de implementar. Los valores marcados **[MVP]** son los de la política demo; la institución debe aprobarlos o reemplazarlos antes de un piloto.

## 1. Convenciones

| Tema | Regla |
|---|---|
| Identificadores | `uuid` con `gen_random_uuid()`, como el resto de `core` |
| Usuarios | Identificador corto `text` con el formato del producto `^[a-z0-9_.-]{3,40}$` (por ejemplo `b.lopez`). Sin clave foránea a `core.usuarios`, porque en modo desarrollo los usuarios no existen en esa tabla. En `produccion` el servicio exige que el usuario exista, esté activo y tenga rol `bienestar` |
| Tiempo | `timestamptz` en UTC; rangos `tstzrange` semiabiertos `[inicio, fin)`; zona IANA por profesional (`America/Guayaquil` **[MVP]**) |
| Modo por entorno | `desarrollo` → `demo`, `pruebas` → `piloto_interno`, `produccion` → `produccion`. Lo resuelve la API desde `Ajustes.entorno`; ningún endpoint ni herramienta acepta el modo como parámetro |
| Día de una cita | Fecha local de `lower(rango)` en la zona de la agenda: `(lower(rango) AT TIME ZONE zona)::date`. Un conteo por día suma `reservada` y `finalizada` y excluye `cancelada` |
| Chat sin LLM | El modo básico no ofrece herramientas de agenda: responde que la consulta no está disponible y remite a la pantalla Agenda |
| Versión | Columna `version integer` en cada recurso editable; los comandos llevan `If-Match: <version>` |
| Idempotencia | Encabezado `Idempotency-Key` en todo comando de escritura; ámbito = usuario + tipo de comando |
| Borrado | Nada se borra. Las cancelaciones cambian estado; los historiales son de solo agregar |
| Permisos | Una fila por acción en `api/app/auth/permisos.py`; la prueba de matriz completa debe cubrirlas |
| Datos personales | Ningún modelo de agenda devuelve cédula. El seudónimo (`persona_ref`) solo se usa dentro de la API para las guardas y la exclusión |

## 2. Migración `0011_agenda`

Reversible, como todas las del producto. **Validada el 28 de octubre de 2026** en un PostgreSQL 18 temporal con las tablas del producto que toca: acepta citas adyacentes y una nueva reserva sobre un rango cancelado; rechaza solapes del mismo profesional o de la misma persona con otro profesional, duración distinta de 15 minutos, una segunda cita activa del caso, modificar una política aprobada y editar `eventos_cita`; el chat no puede leer `core.citas` pero sí la vista. La extensión `btree_gist` es *trusted* desde PostgreSQL 13: puede instalarla el dueño de la base sin superusuario. El MVP local usa PostgreSQL 18.

```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ---------------------------------------------------------------- equipos y profesionales
CREATE TABLE core.agenda_equipos (
  id      uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  nombre  text NOT NULL UNIQUE CHECK (length(btrim(nombre)) > 0),
  sede    text,
  creado  timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE core.agenda_profesionales (
  usuario     text PRIMARY KEY CHECK (usuario ~ '^[a-z0-9_.-]{3,40}$'),
  equipo_id   uuid REFERENCES core.agenda_equipos(id),
  coordina    boolean NOT NULL DEFAULT false,            -- alcance de coordinación sobre su equipo
  zona        text NOT NULL DEFAULT 'America/Guayaquil',
  habilitado  boolean NOT NULL DEFAULT true,
  version     integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  creado      timestamptz NOT NULL DEFAULT now(),
  actualizado timestamptz NOT NULL DEFAULT now(),
  CHECK (NOT coordina OR equipo_id IS NOT NULL)
);

-- ---------------------------------------------------------------- política versionada
CREATE TABLE core.politicas_agenda (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_id    text NOT NULL,
  version      integer NOT NULL CHECK (version >= 1),
  modo         text NOT NULL CHECK (modo IN ('demo', 'piloto_interno', 'produccion')),
  estado       text NOT NULL DEFAULT 'borrador' CHECK (estado IN ('borrador', 'aprobada', 'retirada')),
  contenido    jsonb NOT NULL,                           -- validado contra §7 antes de aprobar
  aprobada_por text,
  aprobada_en  timestamptz,
  creado       timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_id, version),
  CHECK ((estado = 'borrador') = (aprobada_en IS NULL))
);
CREATE UNIQUE INDEX una_politica_aprobada_por_modo ON core.politicas_agenda (modo) WHERE estado = 'aprobada';
-- una política aprobada no cambia: solo puede pasar a 'retirada'
CREATE FUNCTION core.politica_inmutable() RETURNS trigger LANGUAGE plpgsql AS $f$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'una política no se borra' USING ERRCODE = 'insufficient_privilege'; END IF;
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
-- La superposición de tramos del mismo día y vigencia la valida el servicio (E10-T4 CA3).

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
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  caso_id          uuid NOT NULL REFERENCES core.casos(id),
  derivado_en      timestamptz NOT NULL,
  estado           text NOT NULL DEFAULT 'pendiente' CHECK (estado IN
                     ('pendiente', 'pendiente_asignacion', 'agendada', 'sin_disponibilidad', 'cancelada_por_caso', 'requiere_revision')),
  motivo           text,
  profesional      text REFERENCES core.agenda_profesionales(usuario),
  prioridad        smallint NOT NULL,                     -- copia de core.casos.prioridad, se relee por ronda
  nivel            text NOT NULL CHECK (nivel IN ('medio', 'alto', 'critico')),
  intentos         smallint NOT NULL DEFAULT 0,
  proximo_intento  timestamptz,
  aviso_espera     boolean NOT NULL DEFAULT false,        -- ya se avisó que superó el plazo de su nivel
  version          integer NOT NULL DEFAULT 1,
  creado           timestamptz NOT NULL DEFAULT now(),
  actualizado      timestamptz NOT NULL DEFAULT now(),
  UNIQUE (caso_id, derivado_en)
);
CREATE INDEX solicitudes_cola ON core.solicitudes_cita (profesional, estado, prioridad DESC, derivado_en, caso_id);

CREATE TABLE core.citas (
  id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  solicitud_id        uuid NOT NULL REFERENCES core.solicitudes_cita(id),
  caso_id             uuid NOT NULL REFERENCES core.casos(id),
  persona_ref         text NOT NULL,                     -- seudónimo del caso; nunca sale de la API
  profesional         text NOT NULL REFERENCES core.agenda_profesionales(usuario),
  rango               tstzrange NOT NULL,
  rango_ocupado       tstzrange NOT NULL,                -- rango + márgenes vigentes al reservar
  zona                text NOT NULL,
  estado              text NOT NULL DEFAULT 'reservada' CHECK (estado IN ('reservada', 'cancelada', 'finalizada')),
  motivo_cancelacion  text,
  politica_id         uuid NOT NULL REFERENCES core.politicas_agenda(id),
  intervencion_id     uuid REFERENCES core.intervenciones(id),   -- resultado registrado
  version             integer NOT NULL DEFAULT 1,
  creado              timestamptz NOT NULL DEFAULT now(),
  actualizado         timestamptz NOT NULL DEFAULT now(),
  CHECK (lower_inc(rango) AND NOT upper_inc(rango)),
  CHECK (upper(rango) - lower(rango) = interval '15 minutes'),
  CHECK (rango_ocupado @> rango),
  CHECK ((estado = 'cancelada') = (motivo_cancelacion IS NOT NULL)),
  EXCLUDE USING gist (profesional WITH =, rango_ocupado WITH &&) WHERE (estado = 'reservada'),
  EXCLUDE USING gist (persona_ref WITH =, rango_ocupado WITH &&) WHERE (estado = 'reservada')
);
CREATE UNIQUE INDEX una_cita_activa_por_caso ON core.citas (caso_id) WHERE estado = 'reservada';
CREATE INDEX citas_profesional ON core.citas USING gist (profesional, rango);
CREATE INDEX citas_caso ON core.citas (caso_id);

CREATE TABLE core.operaciones_agenda (
  ambito        text NOT NULL,                           -- '<usuario>:<comando>' o 'planificador:reservar'
  clave         text NOT NULL,
  hash_comando  text NOT NULL,
  estado        text NOT NULL CHECK (estado IN ('confirmada', 'fallida')),
  resultado     jsonb NOT NULL,
  creado        timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (ambito, clave)
);

CREATE TABLE core.eventos_cita (
  id         bigserial PRIMARY KEY,
  cita_id    uuid REFERENCES core.citas(id),
  solicitud_id uuid REFERENCES core.solicitudes_cita(id),
  accion     text NOT NULL,
  de_estado  text,
  a_estado   text,
  actor      text NOT NULL,
  detalle    jsonb NOT NULL DEFAULT '{}',
  creado     timestamptz NOT NULL DEFAULT now(),
  CHECK (cita_id IS NOT NULL OR solicitud_id IS NOT NULL)
);
CREATE TRIGGER eventos_cita_sin_modificar BEFORE UPDATE OR DELETE ON core.eventos_cita FOR EACH ROW EXECUTE FUNCTION core.solo_agregar();
CREATE TRIGGER eventos_cita_sin_vaciar BEFORE TRUNCATE ON core.eventos_cita FOR EACH STATEMENT EXECUTE FUNCTION core.solo_agregar();

-- ---------------------------------------------------------------- cambios en tablas existentes
ALTER TABLE core.casos ADD COLUMN asignado_a text CHECK (asignado_a ~ '^[a-z0-9_.-]{3,40}$');          -- P3
ALTER TABLE core.notificaciones ADD COLUMN destinatario text;                                          -- P5
ALTER TABLE core.notificaciones ADD COLUMN obsoleta boolean NOT NULL DEFAULT false;
ALTER TABLE core.notificaciones DROP CONSTRAINT notificaciones_tipo_check;
ALTER TABLE core.notificaciones ADD CONSTRAINT notificaciones_tipo_check CHECK (tipo IN (
  'caso_derivado', 'caso_escalado', 'intervencion_registrada', 'uso_inusual', 'deriva',     -- tipos vigentes desde la 0007
  'cita_reservada', 'cita_reprogramada', 'cita_cancelada', 'cita_sin_resultado',
  'solicitud_sin_asignar', 'solicitud_sin_disponibilidad', 'espera_excedida'));
CREATE INDEX notificaciones_destinatario ON core.notificaciones (destinatario, creado DESC) WHERE destinatario IS NOT NULL;

-- ---------------------------------------------------------------- vista sin seudónimo para el chat
CREATE VIEW core.v_citas_chat AS
  SELECT id, caso_id, profesional, rango, zona, estado, version FROM core.citas;

-- ---------------------------------------------------------------- permisos
GRANT SELECT, INSERT, UPDATE ON core.agenda_equipos, core.agenda_profesionales, core.politicas_agenda, core.agenda_horarios,
  core.agenda_bloqueos, core.solicitudes_cita, core.citas, core.operaciones_agenda TO app_api;
GRANT SELECT, INSERT ON core.eventos_cita TO app_api;
GRANT UPDATE (obsoleta) ON core.notificaciones TO app_api;      -- solo marcar obsoleto un aviso de una cita que cambió
GRANT USAGE ON SEQUENCE core.eventos_cita_id_seq TO app_api;
GRANT SELECT ON core.agenda_equipos, core.agenda_profesionales, core.agenda_horarios, core.agenda_bloqueos,
  core.solicitudes_cita, core.v_citas_chat TO app_chat_ro;          -- sin core.citas: el chat no ve persona_ref
```

**Correcciones del 28 de octubre de 2026 (v1.2):** `app_api` necesita `UPDATE (obsoleta)` sobre `core.notificaciones` para marcar avisos obsoletos; antes solo tenía `SELECT` e `INSERT`. Lo detectó una prueba de E10-T3 con el rol real. La versión 1.0 omitía también el tipo `deriva`, agregado por la migración `0007` del producto. La prueba `test_itm8_una_deriva_fuerte_avisa_una_sola_vez_por_corte` lo detectó durante la implementación; la migración real y una prueba de regresión ya lo cubren.

El *downgrade* elimina, en orden inverso, vista, índices, columnas agregadas (restaurando la restricción de tipos anterior después de borrar los avisos nuevos), tablas, disparadores y funciones. La extensión se conserva: otra migración podría usarla.

## 3. Prioridad y orden

La prioridad es la que el producto ya calcula en `services/casos.py`:

```text
prioridad = base(nivel) + 5 si escalado + 3 si sin_atender
base: medio = 10, alto = 20, crítico = 30          → rango 10..38
```

- La solicitud copia `prioridad` y `nivel` del caso al crearse y **los relee de `core.casos` al comenzar cada ronda**. Un escalamiento en un corte nuevo puede subirla.
- Orden de reserva por profesional: `prioridad DESC, derivado_en ASC, caso_id ASC`. Es el `ORDER BY` de `GET /bienestar/casos` (`c.prioridad DESC, c.derivado_en, c.id`), lo que permite comprobar A48 con un oráculo.
- Registrar una intervención pone `sin_atender = false` y recalcula la prioridad del caso; no afecta a citas ya reservadas.

## 4. Cambios en funciones existentes del producto

| Función | Cambio | Misma transacción |
|---|---|---|
| `casos.derivar` | Después del `UPDATE`, insertar la solicitud con `derivado_en` del caso (`RETURNING derivado_en`), `prioridad`, `nivel` y `profesional = asignado_a`; si `asignado_a` es nulo, estado `pendiente_asignacion` y aviso a coordinación. Publicar `cita.solicitada` | Sí |
| `casos.cerrar` | Si hay cita `reservada`: pasarla a `cancelada` con motivo `caso_cerrado:<motivo>`, marcar sus avisos `obsoleta` y avisar al profesional. Solicitudes abiertas del caso → `cancelada_por_caso` | Sí |
| `casos.registrar_matriculas` | Para cada caso que pasa a `sin_matricula`, la misma cancelación con motivo `sin_matricula` | Sí |
| `casos.descartar` | **Sin cambios.** Solo actúa sobre casos `nuevo`, que nunca tienen solicitud ni cita | — |
| `casos.registrar_intervencion` | Sin cambios. La agenda la llama para registrar el resultado (§6) | — |
| `notificaciones.listar` y `sin_leer` | Incluir los avisos con `destinatario = usuario`; excluir `obsoleta` del conteo de no leídos. Un aviso dirigido conserva `rol = 'bienestar'` para cumplir la columna obligatoria | — |
| `shared/llm.py` | `RespuestaLLM` agrega `usage` y `finish_reason`; método `contar(mensajes, herramientas)` con `POST /tokenize`; semáforo global (P7). Solo para la fase 10.E | — |

## 5. Evento `cita.solicitada`

```python
class CitaSolicitada(Evento):          # version 1, sin datos personales
    tipo: Literal["cita.solicitada"]
    caso_id: uuid.UUID
    solicitud_id: uuid.UUID
```

- Clave de idempotencia del bus: `cita.solicitada:<solicitud_id>`.
- Un solo consumidor: el proceso consumidor de la API (`api/app/consumidor.py`), que agrega el tipo a sus `TIPOS` y llama al planificador. Así se respeta la regla «un consumidor por tipo» (D15).
- Se agrega al candado `shared/eventos/esquemas.lock.json`.

## 6. Endpoints

Prefijo `/agenda`, salvo la ampliación del detalle del caso. Todos declaran modelo de respuesta con `extra="forbid"`, como el resto de la API, y se publican en `frontend/openapi.json`.

### Permisos nuevos

| Acción | Roles | Condición adicional en el servicio |
|---|---|---|
| `ver_agenda` | bienestar | Propia; con `coordina`, la de su equipo |
| `gestionar_agenda` | bienestar | Sus horarios, bloqueos y citas |
| `coordinar_agenda` | bienestar | Requiere `coordina = true`; alcance: su equipo |
| `configurar_agenda` | admin | Profesionales, equipos y políticas; nunca identidad |
| `ver_cita_de_caso` | seguimiento, bienestar | Seguimiento: casos que derivó; Bienestar: casos derivados visibles |

### Catálogo

| Método y ruta | Acción | Petición | Respuesta |
|---|---|---|---|
| `GET /agenda/profesionales` | ver_agenda, configurar_agenda | `equipo_id?` | Lista de profesionales: usuario, equipo, coordina, zona, habilitado, versión |
| `PUT /agenda/profesionales/{usuario}` | configurar_agenda | `equipo_id`, `coordina`, `zona`, `habilitado` + `If-Match` | Profesional |
| `GET /agenda/profesionales/{usuario}/horarios` | ver_agenda | — | Tramos semanales con vigencia |
| `PUT /agenda/profesionales/{usuario}/horarios` | gestionar_agenda, configurar_agenda | Conjunto completo de tramos + `If-Match` (versión del profesional) | Tramos; 409 si deja citas fuera de jornada |
| `POST /agenda/profesionales/{usuario}/bloqueos` | gestionar_agenda | `inicio`, `fin`, `motivo` + `Idempotency-Key` | Bloqueo; 409 `bloqueo_con_citas` con la lista de citas afectadas |
| `POST /agenda/bloqueos/{id}/desactivar` | gestionar_agenda | `motivo` | Bloqueo |
| `GET /agenda/profesionales/{usuario}/disponibilidad` | ver_agenda | `desde`, `hasta` (≤ 14 días), `cursor?` | Hasta 20 franjas `{inicio, fin}` + `cursor` |
| `GET /agenda/profesionales/{usuario}/citas` | ver_agenda | `desde`, `hasta` | Citas: id, caso_id, nivel, inicio, fin, estado, versión, resultado |
| `GET /agenda/solicitudes` | ver_agenda | `estado?`, `cursor?` | Solicitudes con prioridad, nivel, espera en días hábiles, motivo y cita |
| `POST /agenda/solicitudes/{id}/asignar` | coordinar_agenda | `profesional` + `If-Match` | Solicitud (actualiza también `core.casos.asignado_a`) |
| `POST /agenda/citas/{id}/reprogramar` | gestionar_agenda | `inicio`, `motivo` + `If-Match` + `Idempotency-Key` | Cita con versión nueva |
| `POST /agenda/citas/{id}/cancelar` | gestionar_agenda | `motivo`, `reagendar` (bool, por defecto `true`) + `If-Match` + `Idempotency-Key` | Cita. Con `reagendar`, la solicitud vuelve a `pendiente`; sin él, `requiere_revision` |
| `POST /agenda/citas/{id}/resultado` | gestionar_agenda | `tipo`, `resultado`, `tipo_otro`, `observaciones` + `Idempotency-Key` | `{intervencion_id}`; llama a `casos.registrar_intervencion` |
| `POST /agenda/profesionales/{usuario}/ausencias` | coordinar_agenda | `inicio`, `fin`, `motivo` + `Idempotency-Key` | Resultado por cita: reprogramada (nueva hora) o `sin_disponibilidad` |
| `GET /agenda/politicas` | configurar_agenda | — | Versiones con modo y estado |
| `POST /agenda/politicas` | configurar_agenda | `policy_id`, `modo`, `contenido` | Borrador validado (422 con el campo que falla) |
| `POST /agenda/politicas/{id}/aprobar` | configurar_agenda | `motivo` | Política aprobada; retira la anterior del mismo modo |
| `GET /casos/{id}` (ampliado) | ver_cita_de_caso | — | Campo nuevo `cita`: `{inicio, fin, profesional, estado, resultado}` o `null` |

### Errores

Formato: `{"detail": {"codigo": "<código>", "mensaje": "<texto para la persona>"}}`. Es nuevo en la API y lo maneja el módulo de agenda del frontend; los endpoints existentes conservan su `detail` de texto.

| HTTP | Código | Cuándo |
|---|---|---|
| 401 / 403 | `sin_sesion` / `sin_permiso` | Igual que el resto de la API |
| 404 | `no_existe` | Recurso inexistente **o fuera de alcance**: no revela existencia |
| 409 | `conflicto_franja` | La franja dejó de estar libre al confirmar |
| 409 | `conflicto_version` | `If-Match` no coincide con la versión actual |
| 409 | `cupo_agotado` | Se alcanzó el cupo diario del profesional |
| 409 | `idempotencia_conflicto` | Misma clave con otro comando |
| 409 | `caso_no_derivado` | El caso ya no está derivado o se cerró |
| 409 | `cita_finalizada` | Se intenta cambiar una cita finalizada o cancelada |
| 409 | `bloqueo_con_citas` | Un bloqueo u horario deja citas activas fuera |
| 422 | `fuera_de_jornada`, `fuera_de_grilla`, `anticipacion_insuficiente`, `rango_invalido`, `politica_invalida` | Validaciones de dominio |
| 428 | `falta_precondicion` | Falta `If-Match` o `Idempotency-Key` |
| 503 | `sin_politica` | No hay política aprobada para el modo de la instancia |

## 7. Esquema de la política

`contenido` de `core.politicas_agenda`. El perfil [politica.demo.json](../config/politica.demo.json) es la instancia **[MVP]**.

| Campo | Tipo y validación | Valor [MVP] |
|---|---|---|
| `trigger.event` | `"caso_derivado"` | `caso_derivado` |
| `priority.order` | Lista fija `["prioridad_desc", "derivado_en_asc", "caso_id_asc"]` | Igual |
| `assignment.strategy` | `asignado_en_producto` \| `tabla_por_equipo` \| `coordinacion_manual` | `coordinacion_manual` |
| `target_business_days_by_level` | Enteros ≥ 1 para `critico`, `alto`, `medio`, no decrecientes | 2 / 5 / 10 |
| `schedule.duration_minutes` | `15` | 15 |
| `schedule.grid_minutes` | `15` | 15 |
| `schedule.minimum_notice_minutes` | Entero ≥ 0 | 1440 |
| `schedule.search_business_days` | Entero 1..30 | 10 |
| `schedule.buffer_before_minutes`, `buffer_after_minutes` | Entero 0..60, múltiplo de 5 | 0 / 0 |
| `schedule.maximum_daily_appointments_per_professional` | Entero ≥ 1 | 20 |
| `schedule.weekdays_iso` | Subconjunto no vacío de 1..7 | 1–5 |
| `schedule.working_intervals_local` | Tramos `HH:MM` válidos, sin superposición, alineados a la grilla | 09:00–12:00 y 14:00–17:00 |
| `schedule.non_working_dates` | Fechas ISO únicas | `[]` |
| `result_deadline_business_days` | Entero ≥ 1 | 2 |
| `communication.mode` | `panel_interno` | `panel_interno` |
| `timezone` | Zona IANA válida | America/Guayaquil |

Los horarios propios de cada profesional (`agenda_horarios`) deben quedar dentro de los tramos de la política. Si un profesional no tiene horario cargado, no ofrece disponibilidad.

## 8. Algoritmos

### Disponibilidad

```text
franjas(profesional, desde, hasta):
    para cada día laborable de la política dentro de [desde, hasta) y fuera de non_working_dates:
        para cada tramo vigente del profesional ese día (hora local → UTC con la zona):
            generar inicios cada 15 min con inicio + 15 ≤ fin del tramo
    descartar inicio < ahora + minimum_notice
    descartar franjas cuyo rango con márgenes se cruce con bloqueos activos o citas reservadas
    descartar días que ya alcanzaron el cupo diario
    ordenar por inicio ASC y devolver hasta 20 con cursor
```

Las horas locales ambiguas o inexistentes por cambio de horario se descartan. America/Guayaquil no tiene horario de verano, pero la regla aplica a cualquier zona.

### Ronda del planificador

```text
ronda(profesional):
    solicitudes = pendientes del profesional con proximo_intento ≤ ahora,
                  releyendo prioridad y nivel de core.casos,
                  ORDER BY prioridad DESC, derivado_en, caso_id
    para cada solicitud (orden congelado):
        para cada franja candidata (hasta 3) dentro de la ventana:
            intentar reservar(solicitud, franja)
            si confirmada: siguiente solicitud
            si conflicto_franja: probar la siguiente franja
        si no hubo franja: estado sin_disponibilidad; aviso una vez; continuar
```

Disparadores de ronda: `cita.solicitada`, liberación de una franja (cancelación, reprogramación, bloqueo desactivado), cambio de horario y una ronda periódica cada 15 minutos que también reactiva `sin_disponibilidad` por avance de la ventana.

### Reserva

```text
reservar(solicitud, franja):                      -- una transacción, sin red ni LLM
    pg_advisory_xact_lock(hashtext('persona:' || persona_ref))
    SELECT ... FROM core.agenda_profesionales WHERE usuario = profesional FOR UPDATE
    SELECT ... FROM core.casos WHERE id = caso_id FOR UPDATE
    exigir caso.estado = 'derivado' y solicitud.estado = 'pendiente'      → si no: caso_no_derivado
    exigir franja dentro de jornada, grilla, anticipación y ventana         → si no: 422
    exigir citas del día < cupo                                             → si no: cupo_agotado
    INSERT core.citas (rango, rango_ocupado = rango ± márgenes, ...)        → violación de exclusión: conflicto_franja
    UPDATE solicitud → agendada; INSERT eventos_cita; INSERT notificación al profesional
    INSERT operaciones_agenda ('planificador:reservar', '<caso_id>:<derivado_en>')
```

El orden de bloqueos (persona → profesional → caso) es fijo en toda la agenda, también en reprogramar y cancelar. Ante un deadlock o un fallo de serialización, se hacen hasta dos reintentos con jitter.

### Conciliación

Cada 15 minutos y al arrancar el consumidor:

| Divergencia | Corrección |
|---|---|
| Cita `reservada` de un caso `cerrado` o `sin_matricula` | Cancelar con motivo `conciliacion` |
| Caso `derivado` sin solicitud para su `derivado_en` | Crear la solicitud |
| Solicitud abierta de un caso que ya no está derivado | `cancelada_por_caso` |
| Cita `reservada` cuyo fin ya pasó | `finalizada` |
| Cita finalizada sin resultado tras el plazo | Aviso único `cita_sin_resultado` |

Cada corrección queda en `eventos_cita` con actor `conciliacion` y en `audit.registro`.

## 9. Herramientas del asistente (fase 10.E)

Esquemas de argumentos en el formato de herramientas de OpenAI que usa el cliente del producto (modo JSON):

```json
[
 {"name": "consultar_derivaciones", "parameters": {"type": "object", "additionalProperties": false, "properties": {
   "estado": {"enum": ["pendiente", "pendiente_asignacion", "sin_disponibilidad", "agendada"]},
   "nivel": {"enum": ["medio", "alto", "critico"]}, "cursor": {"type": "string"}}}},
 {"name": "consultar_agenda", "parameters": {"type": "object", "additionalProperties": false, "required": ["desde", "hasta"], "properties": {
   "profesional": {"type": "string"}, "desde": {"type": "string", "description": "fecha ISO o expresión relativa"},
   "hasta": {"type": "string"}, "incluir_libres": {"type": "boolean"}}}},
 {"name": "proponer_reprogramacion", "parameters": {"type": "object", "additionalProperties": false, "required": ["cita_id", "version"], "properties": {
   "cita_id": {"type": "string", "format": "uuid"}, "version": {"type": "integer"},
   "desde": {"type": "string"}, "hasta": {"type": "string"}, "preferencia": {"enum": ["manana", "tarde", "cualquiera"]}}}},
 {"name": "proponer_cancelacion", "parameters": {"type": "object", "additionalProperties": false, "required": ["cita_id", "version", "motivo"], "properties": {
   "cita_id": {"type": "string", "format": "uuid"}, "version": {"type": "integer"}, "motivo": {"type": "string", "maxLength": 300}}}},
 {"name": "preparar_nota", "parameters": {"type": "object", "additionalProperties": false, "required": ["caso_id", "proposito"], "properties": {
   "caso_id": {"type": "string", "format": "uuid"}, "proposito": {"enum": ["recordatorio", "resumen_cita"]}}}}
]
```

Expresiones relativas aceptadas por el normalizador **[MVP]**: `hoy`, `mañana`, `pasado mañana`, nombres de día (`lunes`…`viernes`, siempre el próximo), `esta semana`, `la próxima semana`, y los modificadores `por la mañana` (antes de 12:00) y `por la tarde` (desde 12:00). Cualquier otra devuelve `fecha_ambigua`.

## 10. Datos sintéticos de prueba

Base común para pruebas de integración, evals de runtime y la demostración (`agenda-semana-demo`):

| Elemento | Contenido |
|---|---|
| Reloj | Lunes 2 de noviembre de 2026, 10:00 America/Guayaquil |
| Equipo | `bienestar-matriz` con coordinadora `c.ruiz` |
| Profesionales | `b.lopez` (09:00–12:00 y 14:00–17:00), `b.mora` (09:00–12:00), ambos lunes a viernes |
| Bloqueos | `b.lopez`, jueves 5 de noviembre, 09:15–09:30 |
| Casos | 6 derivados (prioridades 38, 30, 25, 20, 20, 10 con fechas de derivación distintas), 1 crítico en `nuevo`, 1 derivado sin asignación, 1 cerrado con cita reservada para la conciliación |
| Citas previas | `cita_demo_014` de `b.lopez`, jueves 5 de noviembre 10:00–10:15, versión 1 |

Los identificadores de caso y persona son sintéticos y no deben corresponder a matrículas reales.

## 11. Lo que no define este contrato

- Las pantallas: se definen con una maqueta revisada por Bienestar antes de la fase 10.D.
- Los 60 evals de runtime: se escriben al empezar la fase 10.E con el formato de [calidad-evals.md](calidad-evals.md) y los datos de §10.
- Los valores institucionales definitivos: los **[MVP]** sirven para construir y demostrar, no para un piloto con estudiantes.
