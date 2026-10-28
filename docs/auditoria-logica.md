# Auditoría de lógica del harness

Fecha: 23 de octubre de 2026. Base revisada: SPEC v0.5, diagrama, presupuestos, scripts y evidencia de Qwen. Resultado: SPEC v0.6.

Esta es una revisión de diseño. El calendario operativo aún no existe: los hallazgos son vacíos o riesgos del spec, no incidentes observados en producción. «Cerrado en diseño» significa que se definió comportamiento y aceptación; no que la implementación o su prueba ya estén terminadas.

## Hallazgos y resolución

| ID | Prioridad | Vacío/riesgo identificado | Resolución incorporada | Verificación requerida |
|---|---|---|---|---|
| H01 | Crítica | Agendar mientras llegan páginas puede dar una cita antes a un riesgo menor. | Corte consistente, lote listo y prioridad congelada antes de planificar (§24). | A23: riesgo mayor en página posterior. |
| H02 | Crítica | Consultar LLM o proveedores dentro de una transacción haría esperar a otros usuarios. | Transacciones breves, sin red; workers separados y bloqueos por recurso (§27–29). | A37: otro asesor avanza con el LLM detenido. |
| H03 | Crítica | Un lock solo por asesor no evita dos citas incompatibles del mismo estudiante con asesores distintos. | Guardas por estudiante/asesor, orden global y exclusiones por ambos recursos (§27). | A28, concurrencia entre asesores. |
| H04 | Alta | Cupos, buffers, anticipación y calendario laboral aparecían sin contrato de validación. | Política versionada obligatoria y cómputo transaccional; perfil demo separado (§23, §26). | A29, límites de jornada y cupo concurrente. |
| H05 | Alta | Citas pasadas podían quedar activas para siempre o inferir asistencia. | Estado finalizada independiente de asistencia y caso pendiente_resultado (§26). | A30. |
| H06 | Alta | Cancelar una cita podría permitir que la próxima importación la recree. | Sin reapertura automática; nuevo ciclo y motivo explícitos (§25–26). | A31. |
| H07 | Crítica | Recordatorios en cola podían enviarse con la hora anterior tras reprogramar. | Clave cita/versión/tipo/destinatario, invalidación y comprobación previa (§28). | A32. |
| H08 | Crítica | Timeout externo podía producir reenvíos o reservas duplicados. | Separar resultado desconocido, consultar operación/conciliar proveedor antes de repetir (§25, §27–28). | A07, A32, A36. |
| H09 | Alta | Un worker interrumpido podía dejar un caso procesando para siempre. | Lease, heartbeat, generación y recuperación de operación antes de reencolar (§27). | A27. |
| H10 | Crítica | Qwen podía transformarse en dependencia obligatoria de toda la agenda. | O0 aislado, pool de inferencia acotado, backpressure y modo degradado (§28–29). | A17, A34, A37. |
| H11 | Alta | Compactar podía terminar el flujo o consumir todo el presupuesto antes de la siguiente acción. | Compactar/recontar/continuar, reservar una llamada útil y limitar pasos sin progreso (§10, §29). | A11, A33. |
| H12 | Alta | Las salidas de 256 tokens y las nueve muestras truncadas podían confundirse con calidad demostrada. | Gate de herramientas y dominio; no ejecutar fragmentos, medir calidad y carga antes de O1/O2 (§29). | G6, A18–A19, A34. |
| H13 | Crítica | Roles e institución estaban descritos, pero no se fijaba su origen autorizado ni su alcance. | Matriz de roles, identidad validada y ámbito también para idempotencia (§25). | A10, A35. |
| H14 | Alta | Revisiones viejas/divergentes o registros inválidos podían sobrescribir datos u omitirse al avanzar cursor. | Upsert con comparación declarada, cuarentena y checkpoint atómicos (§24). | A24–A25. |
| H15 | Alta | No había recuperación ensayada, responsables de alertas o criterios de retención. | Gate operativo, propuesta RPO/RTO y restauración de estado y outbox (§30). | G7, A38. |
| H16 | Alta | Preguntas institucionales abiertas podían convertirse en defaults implícitos para datos reales. | Campos obligatorios, perfil solo demo y matriz G1–G7 con responsables/evidencia (§23, §30). | Arranque rechaza política productiva incompleta. |
| H17 | Media | Esperar A/B o calidad de IA para todo el piloto bloquearía una agenda O0 válida. | Readiness por capacidad y A/B en paralelo, sin declarar terminado el alcance completo (§30). | Piloto O0 funciona con O1/O2 deshabilitados. |
| H18 | Alta | El diagrama Mermaid insinuaba escritura directa a la base del producto. | Retorno opcional únicamente mediante su API; adaptadores sin autoridad duplicada (§6). | Revisión de arquitectura y contratos. |
| H19 | Media | Existían inconsistencias entre 20 % de reserva, topes por ruta, tres dimensiones y estados realmente listados. | Ventana con salida explícita más margen, dimensiones independientes y estados ampliados (§10–11). | Coherencia documental y A11/A18. |
| H20 | Alta | La prioridad estricta puede dejar casos esperando; reintentar falta de cupo sin cambios genera carga inútil. | Reactivación por evento/ventana, medición de antigüedad y alerta sin modificar el orden alfabético (§23, §26). | A26. |
| H21 | Crítica | Pausar un lote incompleto por falta de espacio mientras el planificador espera el lote completo crea un bloqueo circular. | Staging separado, admisión previa, límite explícito y conservación del último corte publicado (§24). | A41: desbordamiento de staging y cursor expirado. |

Los veintiún hallazgos tienen resolución propuesta y verificación asignada. Su implementación sigue pendiente. Los aspectos que dependen de terceros se cierran mediante las puertas explícitas; no se fingen confirmados para afirmar que «no falta nada».

## Cuellos de botella: controles propuestos

| Punto | Riesgo | Control y medida de comprobación |
|---|---|---|
| API de origen | Lotes largos o corte cambiante bloquean prioridad. | Cursor/corte estable, 100 registros por página inicialmente, checkpoint recuperable; latencia y última importación completa visibles. |
| Agenda | Lock global o consultas sobre todo el historial. | Guardas por recurso y transacciones cortas; rangos/índices y consultas acotadas por institución, asesor y fecha. |
| Estudiante/cupo | Comprobaciones solo en memoria del worker. | Validación en la transacción; concurrencia cruzada y cuota diaria probadas. |
| Qwen | Saturación, cola ilimitada o exceso de contexto. | O0 no depende de Qwen; una inferencia inicial, cola acotada y plazos; medir antes de subir concurrencia. |
| Herramientas | Payloads enormes o demasiadas rondas de modelo. | Cuatro intenciones, paginación, 20 franjas por respuesta inicialmente y presupuestos acumulados. |
| Notificaciones | Fallos externos detienen reservas o envían versiones antiguas. | Outbox aislado, versión y vigencia, reintentos finitos y conciliación de resultados inciertos. |
| Operación | Trabajos huérfanos y crecimiento sin observación. | Leases, progreso, responsables, alertas, retención aprobada y restauración ensayada. |

Los límites iniciales son propuestas para el piloto. No se ha medido throughput de 1000 casos ni p95 del calendario; sería incorrecto afirmar que se eliminaron físicamente todos los cuellos de botella mediante un cambio documental.

## Dependencias que no se pueden resolver inventando datos

1. **Equipo de deserción:** contrato real, acceso, escala/revisión del score y extracción consistente (G1).
2. **Coordinación institucional:** política, jornadas, capacidad, asignaciones y contacto con estudiantes (G2/G4).
3. **Identidad y operación:** mecanismo de acceso, retención, backups y responsables (G3/G7).
4. **Dueño del servidor y equipo IA:** configuración/plantilla, herramientas y calidad bajo carga (G6; no bloquea O0).

Cada dependencia tiene un comportamiento mientras falta: no habilitar la capacidad correspondiente y usar datos sintéticos. Esto evita una ambigüedad de ejecución; no equivale a tener una aprobación externa que aún no existe.

## Entregables de esta revisión

- [SPEC v0.6](SPEC.md): corrige contradicciones y añade §23–30 con reglas y aceptación A23–A41.
- [Política demo](../config/politica.demo.json): ejemplo explícito, marcado sin habilitación productiva.
- [Rutas](rutas-por-costo.md): referencia de ventana/tokens, complementada por las reglas de continuidad y carga del spec.
- [HTML](../web/index.html): vista educativa base v0.5; la auditoría no convierte la simulación en una aplicación operativa.

La siguiente verificación útil es implementar núcleo y adaptadores con las pruebas asignadas. No hace falta repetir inferencias de demostración para cerrar riesgos de transacciones, identidad o notificaciones: cada riesgo necesita su propia evidencia.

## Revisión v0.8: alineación con el producto real

Fecha: 28 de octubre de 2026. Base revisada: SPEC v0.7 frente al código y la documentación del Agente de Deserción v2 (commit `fd64df2` con cambios locales). Resultado: SPEC v0.8.

A diferencia de la revisión anterior, estos hallazgos no son vacíos internos del diseño sino **supuestos que el producto real contradice**.

| ID | Prioridad | Supuesto de v0.7 | Realidad del producto | Resolución en v0.8 |
|---|---|---|---|---|
| H22 | Crítica | Reservar a todo caso con riesgo ≥ umbral | «El agente nunca deriva ni decide por sí solo»; Seguimiento deriva | Disparo por `caso.derivado` (§5, §7); A47 |
| H23 | Crítica | Desempate por apellidos y nombres | `pii.identidades` no tiene nombres | Desempate suspendido; orden de la bandeja (§23); A48; P4 posterior |
| H24 | Crítica | Avisar al estudiante | No hay contacto; la notificación al estudiante está fuera de alcance del producto | Aviso solo al profesional en el MVP (§28); P4 con base legal |
| H25 | Alta | `assigned_advisor_id` desde el origen | Se deriva al rol, sin persona | Asignación por política y `pendiente_asignacion` (§23); P3; A46 |
| H26 | Alta | Vigencia del puntaje de 24 h y consulta cada 15 min | El puntaje es por corte (semestral) | Eliminados del calendario (§23) |
| H27 | Alta | Ingesta paginada con corte consistente propio | Paginación por desplazamiento solo para usuarios | Disparo por evento y conciliación (§24); P6 solo en opción B |
| H28 | Alta | Escuchar cambios del caso | Un consumidor por tipo; cierre, descarte y sin matrícula no publican eventos | P1 y P2; conciliación obligatoria mientras falten (§24); A51 |
| H29 | Alta | Stack TypeScript/Node con n8n | Python/FastAPI, bus en PostgreSQL, React | Stack del producto (§5); decisión A/B (§6, G8) |
| H30 | Alta | Resultado de la cita guardado en el calendario | El producto ya tiene `core.intervenciones` con tipo y resultado | Resultado como intervención (§26); A50 |
| H31 | Media | Tool calling por confirmar | El servidor rechaza `tool_choice=auto`; el producto usa modo JSON | Modo JSON (§9, §22) |
| H32 | Media | Concurrencia de inferencia propia | El mismo vLLM atiende al producto con 4 solicitudes por proceso | Límite global coordinado (§29); P7 |
| H33 | Media | El cuello de botella es la carga del sistema | Cientos de derivaciones por semestre; el límite es la capacidad de Bienestar | Plazos por nivel y aviso de espera (§23) |

Hallazgos de v0.6 que v0.8 deja **superados**, porque su mecanismo ya no existe: H01 (agendar mientras llegan páginas), H14 (revisiones del origen) y H21 (bloqueo circular del staging). Sus criterios A23, A24 y A41 quedan retirados. El resto de los hallazgos de v0.6 sigue vigente con el disparo por derivación.

Ningún hallazgo se cierra en el producto desde aquí: P1–P7 son cambios que su equipo debe especificar, probar y aceptar.

**Decisión G8 (28 de octubre de 2026):** el usuario eligió la opción A, módulo dentro del producto. Refuerza H28 y H30, porque cierre de caso, cancelación de cita y registro de intervención pueden quedar en una misma transacción, y vuelve innecesario P6.
