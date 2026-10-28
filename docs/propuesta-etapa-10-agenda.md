# Propuesta — ETAPA 10: Agenda de Bienestar

Propuesta para incorporar al SPEC_REFINADO del producto «Permanencia y acompañamiento estudiantil (UTI)» como versión 1.10. Redactada el 28 de octubre de 2026 desde el proyecto Harness de calendario, a partir del [SPEC del calendario v0.8](SPEC.md) y la revisión del producto en el commit `fd64df2`. **No modifica el repositorio del producto.** Su equipo decide si la acepta, la ajusta o la rechaza.

Sigue el formato de las etapas 4 a 9: objetivo, fuera de alcance, decisiones de diseño, tareas con entregable, criterios de aceptación, criterio de salida con su gate y pruebas orientadas a encontrar fallos. Como la etapa es grande, se divide en **seis fases**, cada una con su propio gate (G10.A a G10.F). El gate final G10 equivale al hito M9.

| Campo | Valor |
|---|---|
| Versión propuesta del SPEC_REFINADO | 1.10 — se agrega la **Etapa 10** (agenda de Bienestar: citas automáticas al derivar, resultado como intervención, conciliación, pantalla de agenda y herramientas del asistente) |
| Deriva de | SPEC del calendario v0.8 (§1–§32), decisión de arquitectura G8 = opción A (módulo del producto) |
| Stack | El del producto: Python 3.11, FastAPI, PostgreSQL/Alembic, bus sobre PostgreSQL, React + TypeScript, vLLM (Qwen3), pytest, Hypothesis |
| Marcas | **[PROPUESTA]** = valor o regla que la institución (Bienestar o Seguimiento) debe confirmar, como en las etapas anteriores |

---

# ETAPA 10 — Agenda de Bienestar

**Objetivo:** que cada caso que Seguimiento deriva a Bienestar reciba automáticamente una cita de 15 minutos con un profesional de Bienestar, según una política aprobada. El resultado de la cita se registra como intervención del caso, y la cita se cancela si el caso se cierra, se descarta o queda sin matrícula. Todo queda auditado, sin datos personales fuera de `pii` y sin que el sistema decida por las personas.

**Fuera de esta etapa:** aviso directo al estudiante (requiere fuente de contacto y base legal, §7.1 del v0.2), integración con Google Calendar u Outlook, respuesta del estudiante por un canal propio, agendamiento sin derivación previa y escrituras ejecutadas por el asistente sin confirmación humana.

## 10.0 Decisiones de diseño (comunes a todas las fases)

1. **Sin derivación no hay cita.** El disparador es la acción `derivar` de Seguimiento. Ningún nivel de riesgo produce una cita por sí solo. Se conserva el principio §0: el agente nunca deriva ni decide.
2. **Solicitud dentro de la misma transacción.** `casos.derivar` crea una solicitud de cita (`core.solicitudes_cita`) y publica `cita.solicitada` en la misma transacción en que registra la derivación. `casos.cerrar`, `casos.descartar` y el paso a `sin_matricula` cancelan la cita activa en su propia transacción. Con esto no hace falta otro consumidor de `caso.derivado`, que ya consumen los avisos (D15 y D29).
3. **Solo la API escribe en `core`.** El planificador de citas corre en el contexto de la API: un consumidor de `cita.solicitada` más un proceso periódico de rondas (`python -m api.app.agenda.rondas`). Los workers no tocan la agenda. Se respetan las reglas de dependencia (§2.1) y `lint-imports`.
4. **Prioridad = la de la bandeja.** `prioridad DESC`, `derivado_en`, `id`: el mismo orden de `GET /bienestar/casos`. La prioridad se relee antes de cada ronda.
5. **Asignación explícita.** El caso derivado recibe un profesional (`core.casos.asignado_a`) por una regla aprobada **[PROPUESTA]** o por Coordinación de Bienestar. Sin asignación, la solicitud queda `pendiente_asignacion`. Nunca se asigna al azar ni con el LLM.
6. **Restricciones en la base.** Una cita activa por caso (índice único parcial) y exclusión de solapamiento por profesional y por persona sobre rangos `tstzrange` con márgenes (`EXCLUDE USING gist`, requiere la extensión `btree_gist`). La disponibilidad no bloquea; la reserva revalida dentro de una transacción breve, sin red ni LLM.
7. **Resultado = intervención.** El resultado de la cita se registra con el catálogo existente (`TipoAccion`, `ResultadoIntervencion`) mediante `casos.registrar_intervencion`, con el profesional como actor. No hay un segundo registro de resultados.
8. **Avisos dirigidos.** `core.notificaciones` admite un destinatario de usuario además del rol, para avisar al profesional asignado y no a todo Bienestar.
9. **El asistente sigue siendo de solo lectura.** El chat consulta la agenda con `app_chat_ro`. Para reprogramar o cancelar, propone la acción como componente A2UI con un botón que llama al endpoint normal de la API; la persona confirma. El LLM nunca ejecuta escrituras.
10. **Política versionada e inmutable** (`core.politicas_agenda`): horarios por defecto, feriados, cupos, plazos por nivel, anticipación, ventana, márgenes y regla de asignación **[PROPUESTA]**. El arranque rechaza una política incompleta en `produccion`. El perfil demo no habilita datos reales.
11. **Conciliación como red de seguridad.** Un proceso periódico compara casos y citas y corrige divergencias (cita activa de un caso cerrado, caso derivado sin solicitud), con auditoría.
12. **Desempate alfabético suspendido.** La vista del producto no trae nombres (§7, «la búsqueda por nombre queda pendiente»). Solo se reactiva si se aprueba una fuente de nombres con base legal.

## Plan de fases

| Fase | Contenido | Gate | Depende de |
|---|---|---|---|
| 10.A | Modelo de datos, asignación, avisos dirigidos, política y permisos | G10.A | Etapas 4, 7 y 8 |
| 10.B | Disponibilidad, solicitudes y reserva automática (núcleo sin LLM) | G10.B | 10.A |
| 10.C | Ciclo de vida: resultado, cancelación por caso, conciliación y reprogramación en bloque | G10.C | 10.B |
| 10.D | Interfaz: pantalla Agenda, derivaciones, resultado y estado para Seguimiento | G10.D | 10.C |
| 10.E | Asistente: herramientas de agenda, propuestas con confirmación y evals | G10.E | 10.D y servidor vLLM |
| 10.F | Operación y piloto: carga, restauración, conservación y vista de operación | G10 (M9) | 10.A–10.E |

La agenda sin LLM (10.A–10.D y 10.F) puede pilotarse con 10.E desactivada.

---

## FASE 10.A — Modelo de datos, asignación, avisos y política

**Objetivo:** que la base, los permisos y la configuración soporten la agenda antes de escribir lógica de reserva.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T1 | Esquema de agenda: profesionales, horarios, bloqueos, solicitudes, citas, operaciones, eventos de cita y políticas; rangos con márgenes; extensión `btree_gist` | Migración `0011_agenda` reversible |
| E10-T2 | Asignación: `core.casos.asignado_a`, equipos y alcance de coordinación dentro del rol `bienestar` | Migración + `api/app/services/asignacion.py` |
| E10-T3 | Avisos dirigidos a un usuario, manteniendo los avisos por rol existentes | Cambio en `core.notificaciones` y `services/notificaciones.py` |
| E10-T4 | Política de agenda versionada: esquema, validador y carga; perfil demo | `shared/contratos/politica_agenda.py`, `core.politicas_agenda` |
| E10-T5 | Permisos nuevos en la matriz: `ver_agenda`, `gestionar_agenda`, `coordinar_agenda`, `configurar_agenda`, `ver_cita_de_caso` | `api/app/auth/permisos.py` + fila en la prueba de matriz |
| E10-T6 | Contrato de evento `cita.solicitada` (sin datos personales) y su candado de versión | `shared/eventos/modelos.py`, `esquemas.lock.json` |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T1 | CA1 Subir, bajar y volver a subir deja el mismo esquema. CA2 La base rechaza dos citas activas del mismo caso. CA3 La base rechaza dos citas solapadas del mismo profesional y de la misma persona, incluidos márgenes; dos citas adyacentes con margen cero se aceptan. CA4 `eventos_cita` es de solo agregar. CA5 Solo `app_api` escribe; `app_chat_ro` lee sin identidad |
| E10-T2 | CA1 Un caso derivado tiene a lo sumo un profesional asignado y el cambio queda en el historial. CA2 Solo un usuario activo con rol `bienestar` puede ser asignado. CA3 Solo coordinación (o la regla aprobada) asigna |
| E10-T3 | CA1 Un aviso dirigido solo lo ve su destinatario. CA2 Los avisos por rol siguen funcionando igual. CA3 Reprocesar el evento no duplica el aviso |
| E10-T4 | CA1 Una política sin un campo obligatorio no se activa en `produccion`. CA2 Una política aprobada no se modifica: cambiarla crea otra versión. CA3 Tramos superpuestos, zona inválida, duración distinta de 15 min o cupo ≤ 0 se rechazan. CA4 El perfil demo nunca habilita `produccion` |
| E10-T5 | CA1 Cada combinación rol × acción nueva probada (2xx o 403). CA2 `admin` configura la agenda sin recibir identidad. CA3 Un profesional sin alcance de coordinación no ve agendas ajenas (404 sin revelar existencia) |
| E10-T6 | CA1 Un payload con cédula, nombres o contacto se rechaza. CA2 Cambiar el contrato sin subir la versión rompe la prueba del candado. CA3 `cita.solicitada` tiene un solo consumidor |

**Criterio de salida (Gate G10.A):** migración probada contra PostgreSQL real, matriz de permisos completa, contrato con candado y mutaciones de política y permisos al 100 %.

### Pruebas (orientadas a encontrar fallos)

- **Restricciones por propiedades** (Hypothesis): para cualquier par de rangos de un mismo profesional o persona, la base acepta la segunda cita si y solo si un oráculo independiente en Python dice que no se solapan (con márgenes).
- **Bordes temporales:** `[09:00, 09:15)` y `[09:15, 09:30)` adyacentes; un margen de 1 minuto las vuelve incompatibles; rangos que cruzan medianoche.
- **Política inválida:** cada campo obligatorio eliminado uno por uno; tramos superpuestos; feriado con formato erróneo.
- **Mutaciones:** cambiar `[)` por `[]`, quitar el margen del rango, permitir que coordinación sea cualquier `bienestar`, mostrar el aviso dirigido a todo el rol, aceptar una política sin cupo.

---

## FASE 10.B — Disponibilidad, solicitudes y reserva automática

**Objetivo:** que cada derivación produzca una cita confirmada sin intervención humana, en el orden correcto, sin dobles reservas y sin depender del LLM.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T7 | Horarios y bloqueos: alta, edición y baja con versión; conflicto si afectan citas activas | `routers/agenda.py`, `services/agenda.py` |
| E10-T8 | Cálculo de disponibilidad: horario − bloqueos − citas, grilla de 15 min, anticipación, ventana, feriados y zona; máximo 20 franjas por respuesta con cursor | `GET /agenda/profesionales/{id}/disponibilidad` |
| E10-T9 | Solicitud al derivar: `casos.derivar` crea la solicitud y publica `cita.solicitada` en la misma transacción | Cambio en `services/casos.py` |
| E10-T10 | Planificador: consumidor de `cita.solicitada` y rondas periódicas por profesional, con orden congelado por ronda | `api/app/agenda/planificador.py`, `api/app/agenda/rondas.py` |
| E10-T11 | Reserva transaccional: bloqueos en orden estable (persona, profesional, cupo por fecha), revalidación de caso, horario y cupo, cita + operación + aviso en un commit; idempotencia por `caso_id + derivado_en` | `services/agenda.py` |
| E10-T12 | Reprogramar y cancelar manualmente, con versión (`If-Match`) e `Idempotency-Key` | `POST /agenda/citas/{id}/reprogramar`, `POST /agenda/citas/{id}/cancelar` |
| E10-T13 | **IT-M9.B**: derivación → solicitud → reserva con base real, concurrencia incluida | `tests/integration/test_agenda_reserva.py` |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T7 | CA1 Un bloqueo que choca con una cita activa devuelve 409 y no cancela nada. CA2 Editar con una versión vieja devuelve 409. CA3 Todo cambio queda auditado |
| E10-T8 | CA1 Con horario 09:00–10:00, cita 09:15–09:30 y bloqueo 09:45–10:00, devuelve exactamente 09:00 y 09:30. CA2 Respeta feriados, anticipación y ventana. CA3 Coincide con un oráculo independiente |
| E10-T9 | CA1 Derivar crea exactamente una solicitud. CA2 Si la transacción de derivar falla, no queda solicitud ni evento. CA3 Un caso no derivado nunca tiene solicitud |
| E10-T10 | CA1 Con varias solicitudes, el orden de reserva coincide con `GET /bienestar/casos`. CA2 Una solicitud que no puede reservarse no detiene a las siguientes del mismo profesional. CA3 Profesionales distintos avanzan en paralelo. CA4 Sin asignación → `pendiente_asignacion` |
| E10-T11 | CA1 Dos reservas simultáneas a la misma franja: una sola se crea. CA2 Misma persona, dos profesionales, misma hora: una sola se crea. CA3 Timeout después del commit: repetir recupera la misma cita. CA4 No se supera el cupo diario. CA5 Si el caso se cerró antes del commit, no se reserva. CA6 Sin llamadas de red ni LLM dentro de la transacción |
| E10-T12 | CA1 Reprogramar es atómico: si falla, la cita anterior sigue. CA2 Misma clave con otro payload → 409. CA3 Una cita finalizada no se reprograma |
| E10-T13 | CA1 IT-M9.B en verde con PostgreSQL temporal. CA2 Ningún dato personal en el bus, los logs ni las respuestas de agenda |

**Criterio de salida (Gate G10.B):** IT-M9.B en verde, pruebas de concurrencia estables en 20 repeticiones y mutaciones de `services/agenda.py` y del planificador al 100 %.

### Pruebas (orientadas a encontrar fallos)

- **Carreras reales:** hilos que reservan la misma franja, la misma persona con dos profesionales y la misma solicitud dos veces, contra PostgreSQL real, repetidas en bucle.
- **Orden como oráculo:** generar casos con prioridades y fechas aleatorias y comparar el orden de reserva con el de la bandeja calculado por la API existente.
- **Inyección de fallos:** cortar la conexión después del commit y antes de la respuesta; matar el consumidor a mitad de la ronda; deadlock forzado.
- **Prueba negativa obligatoria:** un caso `nuevo` de nivel crítico nunca recibe cita.
- **Mutaciones:** invertir el orden de prioridad, quitar la revalidación del estado del caso, bloquear en otro orden, contar el cupo sin las finalizadas, permitir reservar dentro de la anticipación mínima, detener la ronda en la primera solicitud fallida.

---

## FASE 10.C — Ciclo de vida, resultado y conciliación

**Objetivo:** que la cita acompañe al caso hasta el final: se registra su resultado, se cancela si el caso termina y ninguna divergencia queda sin corregir.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T14 | Resultado de la cita como intervención (tipo y resultado del catálogo existente) | `POST /agenda/citas/{id}/resultado` → `casos.registrar_intervencion` |
| E10-T15 | Cancelación por caso: `cerrar`, `descartar` y paso a `sin_matricula` cancelan la cita activa y marcan obsoletos sus avisos | Cambio en `services/casos.py` |
| E10-T16 | Finalización de citas vencidas y aviso de cita sin resultado tras el plazo **[PROPUESTA: 2 días hábiles]** | Ronda periódica |
| E10-T17 | Plazo objetivo por nivel: aviso a coordinación si la espera desde `derivado_en` lo supera **[PROPUESTA: crítico 2, alto 5, medio 10 días hábiles]** | Ronda periódica |
| E10-T18 | Conciliación: casos cerrados con cita activa, casos derivados sin solicitud, solicitudes huérfanas | `api/app/agenda/conciliacion.py` |
| E10-T19 | Reprogramación en bloque por ausencia del profesional, con motivo; las que no caben pasan a `sin_disponibilidad` | `POST /agenda/profesionales/{id}/ausencias` |
| E10-T20 | **IT-M9.C**: dos ciclos completos con cierre, descarte, sin matrícula y reapertura en un corte posterior | `tests/integration/test_agenda_ciclo.py` |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T14 | CA1 Crea exactamente una intervención y el caso pasa de `derivado` a `en_intervencion`. CA2 "Otro" exige texto. CA3 Registrar dos veces con la misma clave no duplica. CA4 Solo el profesional asignado o coordinación lo registran |
| E10-T15 | CA1 Cerrar o descartar un caso con cita la cancela en la misma transacción. CA2 Si el cierre falla, la cita sigue. CA3 Los avisos de esa cita quedan obsoletos |
| E10-T16 | CA1 Finalizar no infiere asistencia ni resultado. CA2 No se registra `no_contactado` por silencio. CA3 Un aviso por cita, no uno por ronda |
| E10-T17 | CA1 Aviso una sola vez por solicitud y umbral. CA2 Escalar un caso no cambia una cita ya reservada; sí la prioridad de las pendientes |
| E10-T18 | CA1 Cada divergencia sembrada se corrige y queda auditada. CA2 Correr la conciliación dos veces no hace nada la segunda vez. CA3 No toca casos ni citas consistentes |
| E10-T19 | CA1 Ninguna cita queda solapada con la ausencia. CA2 Todo o nada por cita, con resultado por cita. CA3 Exige motivo y alcance de coordinación |
| E10-T20 | CA1 IT-M9.C en verde. CA2 Un caso nuevo de la misma persona en un corte posterior, al derivarse, genera otra solicitud |

**Criterio de salida (Gate G10.C):** IT-M9.C en verde y mutaciones del ciclo de vida y la conciliación al 100 %.

### Pruebas (orientadas a encontrar fallos)

- **Máquina de estados por propiedades:** para cualquier secuencia de derivar, cerrar, descartar, reprogramar, resultado y conciliación, nunca existe una cita activa de un caso cerrado ni dos citas activas del mismo caso.
- **Divergencias sembradas:** escribir estados inconsistentes directamente en la base y exigir que la conciliación los encuentre todos.
- **Tabla de verdad del resultado:** estado del caso × tipo × resultado → transición esperada.
- **Mutaciones:** no cancelar al descartar, cancelar en otra transacción, inferir `no_contactado`, conciliar sin auditar, reprogramar en bloque dejando solapes.

---

## FASE 10.D — Interfaz de agenda

**Objetivo:** que Bienestar opere su agenda, Coordinación asigne y Seguimiento vea el estado de la cita, con la misma interfaz, contrato y reglas de privacidad del producto.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T21 | Modelos de respuesta de agenda, contrato publicado y tipos regenerados | `frontend/openapi.json`, `frontend/src/api/esquema.ts` |
| E10-T22 | Pantalla Agenda (Bienestar): vista diaria y semanal, horarios, bloqueos, reprogramar, cancelar | `frontend/src/paginas/Agenda.tsx` |
| E10-T23 | Derivaciones de Bienestar: pendientes, sin asignar, sin disponibilidad, con motivo; asignación para coordinación | `frontend/src/paginas/` |
| E10-T24 | Registro del resultado desde la cita, con el formulario de intervención existente | `frontend/src/paginas/` |
| E10-T25 | Estado de la cita en el detalle del caso para Seguimiento (solo de los casos que derivó) | `DetalleCaso.tsx` |
| E10-T26 | Configuración de política y profesionales para Administración, sin identidad | `frontend/src/paginas/` |
| E10-T27 | **IT-M9.D**: recorrido en navegador contra la API real | Registro de verificación + pruebas de componentes |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T21 | CA1 Cambiar la API sin regenerar el contrato rompe la prueba. CA2 Ningún modelo de agenda incluye cédula; el detalle del caso sigue siendo el único lugar con identidad |
| E10-T22 | CA1 Un 409 de agenda se explica en pantalla sin perder lo escrito. CA2 La agenda muestra la zona horaria. CA3 Un profesional sin coordinación no ve agendas ajenas |
| E10-T23 | CA1 El orden coincide con el de la API. CA2 Asignar sin alcance de coordinación no está disponible y la API lo rechaza igual |
| E10-T24 | CA1 "Otro" exige texto antes de enviar. CA2 Tras registrar, el caso aparece en intervención |
| E10-T25 | CA1 Seguimiento ve fecha, profesional y resultado, sin acciones de agenda |
| E10-T26 | CA1 Administración configura sin ver identidad. CA2 Una política inválida muestra el campo que falla |
| E10-T27 | CA1 Derivar como Seguimiento → cita visible para Bienestar → resultado → caso en intervención. CA2 Ninguna cédula en URL, almacenamiento ni consola |

**Criterio de salida (Gate G10.D):** IT-M9.D verificada en navegador, `npm run build` y pruebas del frontend en verde, contrato sin deriva.

### Pruebas (orientadas a encontrar fallos)

- **Deriva de contrato** y **componentes contra una API falsa** con la forma del contrato, como en la Etapa 5.
- **Permisos por rol:** con cada rol, la navegación solo ofrece lo permitido; forzar una acción prohibida muestra el 403.
- **Almacenamiento del navegador:** después de usar la agenda, `localStorage` y `sessionStorage` no contienen cédulas.

---

## FASE 10.E — Asistente de agenda

**Objetivo:** que el asistente responda preguntas sobre la agenda y proponga cambios que la persona confirma, dentro de los presupuestos de tokens y sin escrituras del LLM.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T28 | Herramientas de solo lectura (§33.2): `consultar_derivaciones`, `consultar_agenda` y `preparar_nota`, filtradas por rol, con `app_chat_ro`, detector de datos personales, resultados ≤ 600 tokens y normalizador determinista de fechas relativas | `api/app/chat/herramientas.py` |
| E10-T29 | Propuestas de acción (§33.2): `proponer_reprogramacion` y `proponer_cancelacion` como componente A2UI, con token de propuesta firmado (usuario, cita, versión, acción; caduca en 10 min) y confirmación por la API | `api/app/chat/a2ui.py`, `RespuestaA2UI.tsx` |
| E10-T30 | Ejecutor de presupuestos (SPEC del calendario §33.3): reserva y liquidación por llamada, ventana, presupuesto por tarea, escalado O1 → O2, compactación con continuidad; `usage` y `finish_reason` en `RespuestaLLM`; conteo con `/tokenize`; semáforo global hacia vLLM | `shared/llm.py`, `api/app/chat/presupuesto.py`, `chat.presupuestos_tarea` |
| E10-T38 | Trazas de consumo (§33.4): tramos de tarea, contexto, cola, llamada, herramienta, compactación y propuesta; resumen por tarea; consumo visible en Trazabilidad y en el asistente | `shared/trazas.py`, `chat.consumo_tareas`, `Trazabilidad.tsx` |
| E10-T39 | Ejecutor de evals de runtime (§33.5): PostgreSQL temporal con fixture, reloj fijo, sesión por rol, ciclo real del agente, grader y reporte JSON con señales de la traza | `backend/tests/evals/` |
| E10-T31 | Evals de runtime: al menos 60 solicitudes sintéticas en español, con grader automático y 10 corridas por eval | Conjunto de evals + reporte |
| E10-T32 | **IT-M9.E**: conversación con LLM controlado y con el servidor real, de la pregunta a la acción confirmada | `tests/integration/` |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T28 | CA1 Las herramientas no devuelven cédula ni seudónimo. CA2 Un rol sin permiso no recibe la herramienta. CA3 Cada uso queda auditado |
| E10-T29 | CA1 El LLM no puede ejecutar la acción; solo el botón, con la sesión de la persona. CA2 La acción confirmada pasa por las mismas validaciones que la pantalla. CA3 Una propuesta con argumentos que no validan no se muestra. CA4 Un token caducado, ajeno o de una versión vieja se rechaza con 409 (A55) |
| E10-T30 | CA1 Ninguna llamada supera entrada + salida + margen ≤ 8192. CA2 Compactar no reinicia el consumo acumulado. CA3 Con el servidor saturado, el asistente responde `llm_busy` y la agenda sigue funcionando. CA4 Una caída entre reserva y liquidación no pierde consumo (A53). CA5 Un desajuste entre tokenizador y `usage` se registra y avisa (A54). CA6 Siempre queda una llamada para responder (A58) |
| E10-T38 | CA1 Ninguna traza contiene prompts, respuestas, argumentos ni identidad (A56). CA2 Los contadores de la traza coinciden con `usage` de cada respuesta. CA3 El consumo por respuesta se ve con su origen medido o estimado (A57) |
| E10-T39 | CA1 Cada eval falla con un agente nulo y pasa con una respuesta guionada. CA2 Dos corridas con el mismo LLM controlado producen el mismo reporte. CA3 El reporte usa el formato de calidad-evals y toma las señales de la traza |
| E10-T31 | CA1 ≥ 95 % de resolución correcta. CA2 100 % en autorización, identidad y escrituras indebidas, en las 10 corridas. CA3 Se publican todos los fallos |
| E10-T32 | CA1 IT-M9.E en verde. CA2 Texto adversarial en una nota no provoca acciones |

**Criterio de salida (Gate G10.E):** IT-M9.E en verde, evals de runtime sobre su umbral con línea base registrada, consumo visible en trazas y mutaciones de herramientas, ejecutor de presupuestos y trazas al 100 %. Sin este gate, la agenda opera sin asistente.

### Pruebas (orientadas a encontrar fallos)

- **LLM hostil**, como en la Etapa 6: pide herramientas que el rol no tiene, intenta devolver una cédula, responde fuera de formato, propone una acción con un `caso_id` ajeno.
- **Inyección en datos:** una observación de intervención con instrucciones no cambia el comportamiento.
- **Caída a mitad de llamada:** matar el proceso entre reserva y liquidación y comprobar los contadores al reanudar.
- **Tokenizador mentiroso:** un servidor falso cuyo `usage` no coincide con `/tokenize`.
- **Mutaciones:** exponer la herramienta a `admin`, quitar el detector antes del envío, ejecutar la acción sin confirmación, reiniciar el contador al compactar, liquidar con la estimación en lugar de `usage`, no reservar la última llamada, aceptar un token de propuesta caducado, escribir argumentos en la traza.

---

## FASE 10.F — Operación y piloto

**Objetivo:** que la agenda se pueda operar, restaurar y medir antes de usarla con estudiantes reales.

### Tareas

| ID | Tarea | Entregable |
|---|---|---|
| E10-T33 | Vista de operación: solicitudes sin asignar, sin disponibilidad, citas sin resultado, espera por nivel, divergencias de conciliación | `services/operacion.py`, pantalla Operación |
| E10-T34 | Carga: 1000 solicitudes, 50 profesionales, 10 000 citas históricas, 10 clientes; la bandeja existente no se degrada | `tests/integration/test_rendimiento.py` (marca `rendimiento`) |
| E10-T35 | Respaldo y restauración incluyen las tablas de agenda | `scripts/respaldar.py`, `scripts/restaurar.py` |
| E10-T36 | Conservación: las citas siguen la política D32 (1–2 periodos y anonimización de casos cerrados) | `services/conservacion.py` |
| E10-T37 | **IT-M9**: punta a punta de la Etapa 10 con dos cortes, más carga y restauración | `tests/integration/` |

### Criterios de aceptación

| Tarea | Criterios |
|---|---|
| E10-T33 | CA1 Las cifras coinciden con la base. CA2 Sin identidad. CA3 Solo Administración y coordinación |
| E10-T34 | CA1 p95 de disponibilidad ≤ 1 s y reserva confirmada ≤ 2 s **[PROPUESTA]**. CA2 Cero dobles reservas. CA3 La bandeja mantiene su p95 de la Etapa 8 |
| E10-T35 | CA1 Respaldo → restauración deja los mismos conteos de agenda. CA2 Reanudar después de restaurar no duplica citas ni avisos |
| E10-T36 | CA1 Al vencer el plazo, las citas de casos cerrados se anonimizan con su caso. CA2 Ninguna cita conserva un vínculo a una identidad borrada |
| E10-T37 | CA1 IT-M9 en verde. CA2 Mutaciones de la etapa al 100 % |

**Criterio de salida (Gate G10 = hito M9):** IT-M9 en verde, mutaciones de la etapa al 100 %, carga medida, restauración probada y verificación en navegador. Para usar la agenda con estudiantes reales hace falta además, fuera de este gate: política aprobada por Bienestar, Entra ID registrado y el modelo activo aprobado o con excepción firmada.

### Pruebas (orientadas a encontrar fallos)

- **Carga con contención:** muchos profesionales con pocas franjas y muchas solicitudes al mismo tiempo.
- **Restauración a mitad de ronda:** restaurar un respaldo tomado durante una ronda y reanudar.
- **Conservación:** buscar en la base, los respaldos y los logs cualquier vínculo entre una cita y una cédula borrada.

---

## Decisiones que la institución debe confirmar

| # | Decisión | Propuesta | Quién |
|---|---|---|---|
| 1 | Regla de asignación de casos derivados | Coordinación asigna; tabla por equipo como alternativa | Coordinación de Bienestar |
| 2 | Plazo objetivo por nivel | Crítico 2, alto 5, medio 10 días hábiles | Bienestar con Seguimiento |
| 3 | Plazo para registrar el resultado | 2 días hábiles | Bienestar |
| 4 | Anticipación mínima de una cita | 1 día hábil, para que el profesional contacte al estudiante | Bienestar |
| 5 | Horarios, feriados y cupo diario por profesional | Según cada profesional; cupo inicial 20 | Bienestar |
| 6 | Procedimiento de contacto al estudiante | Por canales institucionales, con la cédula del detalle del caso | Responsable institucional |
| 7 | Desempate alfabético | Suspendido mientras no exista una fuente de nombres aprobada | Usuario y responsable de datos |

## Trazabilidad con el SPEC del calendario

| Criterio del calendario (v0.8) | Tareas de la Etapa 10 |
|---|---|
| A01, A03, A12, A46, A47 | E10-T9, E10-T10, E10-T11 |
| A02, A48, A49 | E10-T10 |
| A04, A07, A15, A27, A36 | E10-T11, E10-T12 |
| A05, A06, A28, A29 | E10-T1, E10-T11 |
| A08, A32 | E10-T3, E10-T15 |
| A09, A16 | E10-T7, E10-T12, E10-T19 |
| A10, A13, A19, A35, A52 | E10-T5, E10-T28, E10-T29 |
| A11, A18, A33, A34 | E10-T30 |
| A53, A54, A58 | E10-T30 |
| A55 | E10-T29 |
| A56, A57 | E10-T38 |
| A43–A44 (evals de runtime) | E10-T31, E10-T39 |
| A14 | E10-T28, E10-T32, E10-T38 |
| A17 | E10-T10, E10-T11 (sin LLM) |
| A25, A31, A51 | E10-T11, E10-T15, E10-T18 |
| A26 | E10-T17 |
| A30, A50 | E10-T14, E10-T16 |
| A37, A38 | E10-T34, E10-T35 |
| A39, A40 | E10-T4, E10-T19 |
| A20–A22, A42–A45 | Método del producto (TDD, mutaciones, CI) y sistema de calidad del calendario |

## Cambios respecto del SPEC del calendario v0.8

Al bajar a tareas concretas aparecieron dos ajustes, que se registran también en el SPEC del calendario:

1. **P1 y P2 dejan de ser necesarios en la opción A.** La solicitud se crea dentro de `casos.derivar` y la cancelación dentro de `cerrar`, `descartar` y el paso a `sin_matricula`, en la misma transacción. Se usa un evento nuevo (`cita.solicitada`) con su propio consumidor.
2. **El asistente no escribe.** El chat del producto es de solo lectura por diseño (`app_chat_ro`). `gestionar_cita` pasa a ser una propuesta que la persona confirma en la interfaz.
3. **La lógica del harness de ejecución** (ciclo del agente, herramientas, ejecutor de presupuestos, trazas de consumo y evals de runtime) está en el SPEC del calendario §33 y se implementa en la fase 10.E (E10-T28 a E10-T32, E10-T38 y E10-T39).
