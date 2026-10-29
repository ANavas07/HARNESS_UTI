# Progreso del proyecto — Harness de calendario

Última actualización: **29 de octubre de 2026**, zona America/Guayaquil.

Esta bitácora reúne el proceso realizado, decisiones, entregables, evidencia y trabajo pendiente. La secuencia inicial se reconstruye desde la conversación y los archivos existentes; no se asignan fechas individuales que no estén acreditadas. No es un registro de producción. El [SPEC](docs/SPEC.md) define el comportamiento y [rutas por costo](docs/rutas-por-costo.md) los presupuestos numéricos.

## 1. Estado actual

**Etapa: especificación, prototipo visual y validación inicial de inferencia.** El calendario operativo todavía debe implementarse.

| Frente | Estado | Evidencia o límite |
|---|---|---|
| Definición funcional y arquitectura | Cerrada para el MVP, SPEC v0.9 con contrato técnico | [SPEC](docs/SPEC.md); nuevas reglas técnicas propuestas, no aprobaciones institucionales implícitas. |
| Auditoría integral de lógica | Realizada en diseño | [21 hallazgos de v0.6 y 12 de alineación v0.8](docs/auditoria-logica.md), con resolución propuesta y pruebas asignadas. |
| Alineación con el Agente de Deserción v2 | Analizada el 28 de octubre | Código y documentación revisados (commit `fd64df2`). Arquitectura decidida: módulo del producto (opción A). Etapa 10 aceptada por el equipo del producto el 28 de octubre de 2026 (comunicado por el usuario). Cambios P3, P5 y P7 por implementar en la fase 10.A. |
| Calendario en el producto | Fase 10.A cerrada (G10.A) | PR [GRUPO2_SEGUIMIENTO#1](https://github.com/ANavas07/GRUPO2_SEGUIMIENTO/pull/1): esquema, política, asignación, avisos dirigidos y evento; 1.733 pruebas y mutaciones 46/46. Aún sin reservas ni endpoints (fase 10.B). |
| Conexión y medición de Qwen | Verificadas históricamente | Nueve solicitudes sintéticas; no se volvió a comprobar disponibilidad el 27 de octubre. |
| Presupuestos de tokens | Calculados y cubiertos por cuatro pruebas | No existe aún ejecutor persistente de presupuesto por tarea. |
| HTML interactivo | Actualizado a v0.8 y §33 | Simulación local; no ejecuta herramientas ni llamadas al modelo. Verificado en navegador el 28 de octubre. |
| Política de ejemplo | Creada solo para demo | [JSON](config/politica.demo.json) con `production_enabled=false`; validador y motor pendientes. |
| Experimento A/B | Protocolo definido, no ejecutado | Requiere esqueleto funcional y entornos comparables. |
| Sistema de calidad y tiempos | Runner implementado; un eval ejecutable | [calidad-evals.md](docs/calidad-evals.md), [evals/](evals/) y [runner](scripts/ejecutar_eval.py). Controles de D02 registrados; línea base con agente real, CI por suites y evals de runtime pendientes. |
| Publicación en GitHub | Realizada el 28 de octubre de 2026 | [HARNESS_UTI](https://github.com/ANavas07/HARNESS_UTI), rama `main`: commit inicial `9d020d2`; `4eac95b` con SPEC v0.8, §33, propuesta de la Etapa 10, sistema de calidad, runner de evals y HTML; `9b3f83a` con SPEC v0.9 y contrato técnico. Push verificado contra `origin/main`. |

## 2. Decisiones y aclaraciones del proceso

- Se analizaron las imágenes del harness general, requisitos de documentación, propuesta de calendario y prototipo n8n. Sus ejemplos de certificados/pedidos no se incorporaron como funciones del calendario.
- El usuario confirmó calendario propio para el MVP, consumo del producto de deserción mediante API y reservas automáticas con reglas, sin aprobación por cada cita válida.
- Se adoptaron citas de 15 minutos a partir de la propuesta funcional. Horarios, umbral de riesgo, vigencia, cupos y canal requieren validación institucional.
- Se precisó el desempate solicitado: riesgo descendente; a igual riesgo, apellidos y nombres en orden alfabético español; finalmente ID de caso estable. La comparación ignora mayúsculas/acentos y conserva la ñ. **Suspendido en v0.8:** el producto de deserción no guarda nombres; se usa el orden de su bandeja (§3.10).
- La configuración enviada corrigió el nombre provisional «Qwen 3.8»: el modelo es `Qwen/Qwen3-8B-AWQ`, servido con vLLM mediante API compatible con OpenAI. Ollama no es requisito.
- El hardware informado es cuatro RTX 4000 y 128 GB de RAM. Variante, VRAM y reparto efectivo entre GPU no se verificaron; no se infiere concurrencia a partir del número de tarjetas.
- El usuario aclaró que «costo» significa tokens de entrada/salida, ventana, llamadas y tiempos; no electricidad ni USD.
- La compactación debe reconstruir, recontar y **continuar** cuando el contexto quepa. El consumo acumulado no se reinicia y el presupuesto total sigue teniendo límites.

## 3. Secuencia del trabajo realizado

### 3.1 Análisis inicial y especificación

Se distinguió el harness de ejecución del agente del harness de desarrollo que facilita construir el repositorio. Se definieron actores, alcance, arquitectura, reglas, herramientas, persistencia, estados, contratos API propuestos, fases y aceptación.

Entregable: [docs/SPEC.md](docs/SPEC.md). Las versiones previas fueron refinadas durante la conversación; no todas tienen un commit independiente recuperable. La versión vigente es 0.6, fechada el 23 de octubre de 2026.

### 3.2 Laboratorio A/B y antipatrones

Se analizó la imagen «sin harness vs con harness» y se adaptó el laboratorio a una tarea de disponibilidad del calendario. Se definieron condiciones comparables, medición de éxito/costo y reporte de fallos. También se incorporaron instrucciones breves, pocas herramientas por intención, pruebas rápidas y configuración versionada.

Entregable: [docs/analisis-ab-harness.md](docs/analisis-ab-harness.md). **No se ha ejecutado el experimento** ni se ha demostrado una mejora A/B.

### 3.3 Conexión institucional y mediciones de Qwen

Con autorización del usuario se implementó un cliente de medición y se consultó el servidor institucional. El primer intento encontró una restricción de socket; después se completó el acceso mediante el mecanismo de permisos de red. El descubrimiento reportó una ventana efectiva de **8192 tokens**.

Se hicieron nueve generaciones sintéticas: tres cortas, tres medias y tres largas. Se contó el prompt con el tokenizador del servidor y se contrastó con `usage.prompt_tokens`; coincidieron en las nueve muestras. Perfil: temperatura 0.3, thinking desactivado y solicitudes secuenciales.

| Perfil | Entrada por llamada | Salida por llamada | Tiempo observado |
|---|---:|---:|---|
| Corto | 966 | 128 | 4.443–4.491 s |
| Medio | 2958 | 256 | 9.207–9.209 s |
| Largo | 4964 | 512 | 18.027–18.066 s |

Total: **26664 tokens de entrada + 2688 de salida = 29352** entre nueve llamadas. Ninguna excedió la ventana. Todas terminaron por el límite deliberado de salida (`length`): esto mide consumo/latencia, **no calidad, tool calling ni citas realizadas**.

Evidencia: [medición original](reports/llm/qwen-medicion.json). Utilidad: [scripts/medir_qwen.py](scripts/medir_qwen.py). Configuración de ejemplo: [.env.example](.env.example); el script no carga `.env` automáticamente.

### 3.4 Rutas, cálculos y límites

Se separó ocupación por llamada de consumo acumulado por tarea. Se fijó la condición `entrada + salida máxima + margen <= 8192`, margen inicial de 820 y techo global de entrada de 5734, sujeto a límites menores por ruta.

- O0: agenda estructurada determinista, sin inferencia.
- O1: interpretación/redacción acotada.
- O2: excepción justificada con presupuesto mayor.
- R0/R1/R2: desarrollo/evaluación; no son delegación automática del calendario.

Se calcularon topes por llamada/tarea, número de llamadas y plazos propuestos con las mediciones disponibles. Los tiempos son proyecciones, no SLA. Reintentos y resúmenes contabilizan consumo; el ejecutor operativo aún no existe.

Entregables: [rutas por costo](docs/rutas-por-costo.md), [calculador](scripts/calcular_rutas.py), [presupuestos derivados](reports/llm/qwen-rutas.json) y [pruebas](tests/test_presupuestos.py).

### 3.5 HTML y diagrama interactivo

Se construyó una vista HTML y, por petición del usuario, el diagrama pasó a ser la vista principal. Incluye 21 nodos, ocho recorridos, detalle al seleccionar nodos y controles de navegación del diagrama.

Se corrigió la ruta de contexto excesivo: `compactar → reconstruir contexto → recontar → modelo → continuar`. Se añadió medición visual por paso, distinguiendo contexto preparado, reserva de salida y consumo acumulado simulado.

La simulación usa referencias históricas, sin nuevas inferencias. O0 consume cero tokens de modelo; el ejemplo O1 contabiliza 2958 de entrada y 256 de salida; el ejemplo de compactación y continuación suma 7922 de entrada y 768 de salida entre dos llamadas. No representan todas las tareas posibles.

Entregables: [HTML](web/index.html), [QA histórica](reports/qa/flujo-harness-qa.json) y [capturas](reports/capturas/). La QA del HTML corresponde a la vista base v0.5 y 22 criterios; **no acredita los 41 criterios del SPEC v0.6**. La vista móvil no se comprobó en esa revisión.

### 3.6 Organización y repositorio

Se organizaron documentos en `docs/`, HTML en `web/`, utilidades en `scripts/`, pruebas en `tests/` y evidencia en `reports/`. Después se añadió `config/` para perfiles. Se ajustaron enlaces, rutas de scripts y guía de uso; se añadieron exclusiones locales y normalización de finales de línea.

Se publicó la entrega inicial en [HARNESS_UTI](https://github.com/ANavas07/HARNESS_UTI), rama `main`, commit `9d020d25da47d76078ba09a300e56e1459e07faa`, del 23 de octubre de 2026. Esta referencia acredita la entrega inicial; no significa que las modificaciones posteriores locales estén publicadas. Consultar `git status` antes de informar una nueva subida.

### 3.7 Auditoría integral y SPEC v0.6

Se revisaron spec, diagrama, scripts y presupuestos. Se registraron **21 riesgos/vacíos de diseño**, cada uno con comportamiento propuesto y verificación requerida. Se ampliaron los criterios de A01–A22 a **A01–A41**.

Los principales controles añadidos son:

- Importación con corte consistente, staging y publicación atómica; un lote incompleto no compite por citas ni bloquea circularmente su propia capacidad.
- Prioridad reproducible por asesor, revisiones de origen y vigencia revalidadas antes de reservar.
- Bloqueos por estudiante/asesor, cupos transaccionales, exclusión de solapamientos y orden estable de recursos.
- Identidad y permisos institucionales, idempotencia y control de versión en comandos.
- Ciclo de cancelación, reprogramación, finalización, resultado y reapertura explícita.
- Jobs con lease/recuperación, outbox versionado y conciliación de envíos inciertos.
- Pools separados, colas acotadas y operación O0 sin depender de Qwen.
- Compactación con progreso, consumo conservado y presupuesto para continuar.
- Siete condiciones de activación con responsables y evidencia; objetivos de carga/restauración sujetos a prueba.

Se creó [politica.demo.json](config/politica.demo.json) para ejemplos sintéticos. Sus horarios, umbral y cupos **no son política institucional aprobada**. La auditoría cierra decisiones de diseño, no implementa ni demuestra sus garantías en runtime.

Detalle: [docs/auditoria-logica.md](docs/auditoria-logica.md).

### 3.8 Bitácora central — 27 de octubre de 2026

Se comprobó que no existía `progress.md`. Se creó este archivo y se enlazó desde el README, reconstruyendo el avance con evidencia, límites y pendientes. No se repitieron inferencias ni pruebas de navegador para redactarlo.

### 3.9 Sistema de calidad y tiempos — 28 de octubre de 2026

A partir de dos diapositivas del curso («Anatomía de un eval» y «Señales del harness») se añadió un sistema de medición en tres capas: tests de código, evals del agente y métricas del equipo.

- [docs/calidad-evals.md](docs/calidad-evals.md): suites con presupuesto de tiempo (rápida < 60 s), anatomía tarea/entorno/grader, regla de oro del grader automático, pass@N con 5–10 corridas y 100 % en evals críticos, señales del harness con umbrales iniciales, sistema de tiempos por etapa y formato JSON de resultados.
- [evals/](evals/): D02 (opción `--check` del calculador, ejecutable hoy), D01 (tarea del A/B, bloqueada por el esqueleto), C01 y C02 (agente de calendario, bloqueados por el runtime).
- SPEC v0.7: nueva §31 y criterios A42–A45. El protocolo A/B enlaza el eval D01.

Verificación de D02 en una copia aislada sin `evals/`: el control negativo falla en el commit base (`--check` no existe, salida 2) y el control positivo pasa los seis pasos ejecutables del grader con una solución de referencia. Esa solución no se incorporó al repositorio: es el objetivo del eval. **No se ejecutó ninguna corrida de agente** ni existe línea base de señales.

Después se implementó [scripts/ejecutar_eval.py](scripts/ejecutar_eval.py): copia aislada desde `HEAD` sin `evals/`, N corridas con plazo y terminación del árbol de procesos, grader con los pasos `run`, `sin_cambios` y `solo_modifica`, señales informadas por el agente (`null` si no se informan) y reportes JSON. Se añadió la solución de referencia de D02 en `evals/desarrollo/soluciones/`, fuera del alcance del agente. Los controles se registraron en [reports/evals/2026-10-28/](reports/evals/2026-10-28/) sobre el commit `9d020d2`: el negativo falla en los pasos 2 y 3 y el positivo pasa los 7. La suite completa tiene 10 pruebas y tarda unos 8 s. **Todavía no se corrió ningún agente real**: en este equipo no hay una CLI de agente en el PATH.

### 3.10 Alineación con el Agente de Deserción v2 y SPEC v0.8 — 28 de octubre de 2026

Se analizó el producto real (carpeta `Agente Desercion v2`, commit `fd64df2` con cambios locales): README, arquitectura, resumen, bitácora, SPEC_REFINADO v1.9, migraciones `0001`–`0010`, contratos de eventos, cliente LLM y API de casos. Hallazgos que cambiaron el SPEC:

- El producto establece que «el agente nunca deriva ni decide por sí solo»: Seguimiento deriva y Bienestar atiende. Reservar sobre el puntaje lo contradecía.
- `pii.identidades` solo guarda matrícula, cédula cifrada y seudónimo: no hay nombres ni contacto, y los contratos de eventos los rechazan.
- El puntaje se calcula por corte, dos veces por semestre, y la bandeja ordena por `prioridad`, fecha de derivación e id.
- El bus admite un consumidor por tipo y `caso.derivado` ya lo consumen los avisos; cerrar, descartar y `sin_matricula` no publican eventos.
- Los casos se derivan al rol `bienestar`, sin persona asignada.
- El stack es Python/FastAPI con PostgreSQL y el mismo servidor Qwen, que rechaza `tool_choice=auto`.

SPEC v0.8: disparo por derivación, prioridad del producto, desempate alfabético suspendido, agenda de Bienestar, resultado como intervención del producto, conciliación, decisión de arquitectura A/B abierta (G8) con recomendación A, cambios P1–P7 en el producto y criterios A46–A52; A23, A24 y A41 retirados. Se reescribió la política demo (versión 2) y se ajustaron los evals C01–C02 al rol `bienestar` y sin nombres. **No se modificó el producto de deserción.**

**Decisión de arquitectura (G8), mismo día:** el usuario eligió la opción A, módulo dentro del producto. El código del calendario irá en el repositorio del producto y seguirá su método (etapa nueva en su SPEC_REFINADO, TDD, mutaciones, CI). Este repositorio conserva especificación, calidad, evals y mediciones. P6 deja de ser necesario. El eval D01 se reescribió sobre el repositorio y los comandos reales del producto; sigue bloqueado hasta que exista la etapa de agenda y el runner acepte ese repositorio.

### 3.11 Propuesta de la Etapa 10 para el producto — 28 de octubre de 2026

Se redactó [docs/propuesta-etapa-10-agenda.md](docs/propuesta-etapa-10-agenda.md) en el formato del SPEC_REFINADO del producto: decisiones comunes, seis fases (10.A modelo y política, 10.B reserva, 10.C ciclo de vida y conciliación, 10.D interfaz, 10.E asistente, 10.F operación), 37 tareas con entregable, criterios de aceptación por tarea, pruebas orientadas a encontrar fallos con mutaciones, gates G10.A–G10.E y G10 (hito M9), decisiones institucionales marcadas y trazabilidad con A01–A52.

Al bajar a tareas aparecieron dos ajustes registrados en el SPEC del calendario: P1 y P2 dejan de ser necesarios con la opción A, porque la solicitud y la cancelación ocurren dentro de las transacciones de `casos`, y el asistente solo **propone** cambios que la persona confirma, porque el chat del producto es de solo lectura. La propuesta no se aplicó al repositorio del producto.

### 3.12 Lógica del harness de ejecución — 28 de octubre de 2026

Se agregó el SPEC §33 para que el calendario sea un harness y no solo un flujo con LLM:

- **Ciclo del agente** con ronda reservada para responder.
- **Herramientas de agenda:** cinco contratos, propuestas con token firmado y normalizador de fechas.
- **Ejecutor de presupuestos:** reserva y liquidación por llamada, ventana, presupuesto por tarea y compactación con continuidad.
- **Trazas de consumo:** tramos sin contenido, resumen por tarea y origen medido o estimado.
- **Evals de runtime:** ejecutor, pasos de grader y conjunto de 60.

Criterios nuevos A53–A58. En la revisión del producto se confirmó que su cliente LLM descarta `usage` y `finish_reason` y que sus trazas no cuentan tokens; ambos cambios quedaron en la propuesta (E10-T30, E10-T38). La fase 10.E pasa a 7 tareas con E10-T38 (trazas) y E10-T39 (ejecutor de evals). El eval C01 ahora espera una propuesta y una base sin cambios. Nada de esto está implementado.

### 3.13 Vista interactiva actualizada a v0.8 y §33 — 28 de octubre de 2026

Se rehízo el contenido de [web/index.html](web/index.html), conservando su diseño y su mecánica:

- **Diagrama:** 28 nodos en tres carriles (agenda O0, cierre y conciliación, asistente §33) y 11 recorridos.
- **Panel de consumo:** muestra reserva y liquidación por llamada, cola, `finish_reason` y plazo.
- **Simulación de derivaciones:** usa casos sin nombres, el orden de la bandeja y el cierre que cancela la cita.
- **Vista nueva «Harness de ejecución»:** ciclo del agente, piezas reutilizadas y nuevas, ejecutor de presupuestos interactivo, tramos de traza y evals de runtime.
- **Fases y criterios:** las fases de la Etapa 10 y los criterios A01–A58.

Verificación en navegador local:

- Los 11 recorridos completan con todas sus aristas.
- Los cuatro escenarios de la simulación y las reglas del ejecutor responden según la §33: compactar, desajuste (A54), última llamada reservada (A58), caída (A53) y `budget_exceeded`.
- La consola no registra errores y no hay desbordamiento horizontal a 375 px.

La QA histórica de `reports/qa/` sigue correspondiendo a la v0.5.

### 3.14 SPEC cerrado para empezar el MVP — 28 de octubre de 2026

Tras evaluar la madurez del SPEC, se cerraron las brechas que impedían empezar:

- **[Contrato técnico de la agenda](docs/contrato-tecnico-agenda.md):**
  - esquema SQL de la migración `0011_agenda` con restricciones de exclusión, inmutabilidad e historial de solo agregar;
  - prioridad exacta del producto (10/20/30 + 5 escalado + 3 sin atender);
  - cambios en `derivar`, `cerrar` y `registrar_matriculas`;
  - evento `cita.solicitada`;
  - 18 endpoints con permisos y catálogo de errores;
  - esquema de la política, algoritmos de disponibilidad, ronda, reserva y conciliación;
  - esquemas de herramientas y datos sintéticos.
- **Correcciones del SPEC:** la fase 1 ya no menciona P1/P2; A19 aclarado; descartar no afecta citas, porque el producto solo descarta casos `nuevo`.
- **SPEC §34:** alcance del MVP en localhost, valores del MVP para las 7 decisiones institucionales y definición de listo.

**Verificación:** la migración se ejecutó en un PostgreSQL 18 temporal con las tablas del producto que toca. Las 9 pruebas de restricciones se comportaron según el contrato.

**Pendientes antes de escribir código:** solo la aceptación del equipo del producto, cumplida el mismo día (§3.15). La maqueta revisada por Bienestar bloquea únicamente la fase 10.D.

### 3.15 Etapa 10 aceptada por el equipo del producto — 28 de octubre de 2026

El usuario comunicó que el equipo del producto aceptó la propuesta de la Etapa 10 sin cambios. No se adjuntó un acta. Con esto se cumple la parte de G1 que pedía aceptar la etapa en el plan del producto.

Siguen pendientes dentro de G1 la implementación de P3, P5 y P7 (fase 10.A) y la aprobación o excepción firmada del modelo activo, que solo hace falta para un piloto con estudiantes. La definición de listo (SPEC §34) queda completa para las fases 10.A–10.C.

### 3.16 Desarrollo iniciado: fase 10.A en el producto — 28 de octubre de 2026

El trabajo se hizo en el repositorio del producto (GRUPO2_SEGUIMIENTO), rama local `etapa-10-agenda`, en un worktree aparte (`Agente Desercion v2 - etapa10`) para no tocar los cambios sin commit del Monitor UTI en la carpeta original.

- **SPEC_REFINADO v1.10** con la Etapa 10. E10-T5 (permisos) pasa a la fase 10.B: la prueba de la matriz exige que cada acción tenga su endpoint.
- **E10-T1:** migración `0011_agenda` con 29 pruebas de integración y un objetivo de mutaciones `agenda` en el runner del producto.
- **E10-T6:** evento `cita.solicitada` con 9 pruebas de contrato; declarado sin consumidor hasta la fase 10.B.
- **Hallazgo:** el contrato técnico omitía el tipo de aviso `deriva` de la migración `0007`. La suite del producto lo detectó; se corrigió la migración y el [contrato técnico](docs/contrato-tecnico-agenda.md) pasó a la versión 1.1.
- **Verificación en el producto:**
  - 1.649 pruebas aprobadas;
  - mutaciones del objetivo `agenda`: 17/17;
  - ruff, mypy e import-linter en verde.
- **Decisiones del usuario:** Coordinación asigna; la política demo se carga automáticamente en el MVP; habrá maqueta previa con Bienestar antes de 10.D; la rama se publica con un PR hacia `MVP` del producto. HARNESS_UTI no se publica por ahora.
- **Sigue:** E10-T2, E10-T3 y E10-T4 para cerrar el gate G10.A.

### 3.17 Fase 10.A cerrada (G10.A) — 28 de octubre de 2026

- **Implementado en la rama del producto:**
  - **E10-T4:** validador de la política, servicio de versiones con aprobación auditada y carga automática de la demo en `mvp_local.py`.
  - **E10-T2:** asignación por Coordinación.
  - **E10-T3:** avisos dirigidos.
- **Hallazgo:** `app_api` no podía marcar avisos obsoletos. La migración ahora le da solo `UPDATE (obsoleta)` y el [contrato técnico](docs/contrato-tecnico-agenda.md) pasó a la versión 1.2.
- **Verificación en el producto:**
  - 1.733 pruebas aprobadas;
  - mutaciones del objetivo `agenda`: 46/46;
  - ruff, mypy e import-linter en verde.
- **Incidente controlado:** una corrida de mutaciones se cortó por el límite de tiempo del comando. El runner del producto restauró los 7 archivos desde su respaldo y la corrida completa se repitió sin límite.
- **Publicación:** la rama `etapa-10-agenda` se actualizó en el PR [ANavas07/GRUPO2_SEGUIMIENTO#1](https://github.com/ANavas07/GRUPO2_SEGUIMIENTO/pull/1) hacia `MVP`. HARNESS_UTI sigue sin publicar, por decisión del usuario.
- **Sigue:** la fase 10.B y la maqueta para Bienestar antes de 10.D.

### 3.18 Loop de mejora, iteración 1 — 29 de octubre de 2026

El CI del PR quedó en verde, con 4/4 checks y 1.733 pruebas en Linux, después de corregir el permiso de gitleaks, el lint sobre `build/`, el socket de PostgreSQL y una prueba de PDF dependiente de la plataforma.

Se aplicó el loop observar → diagnosticar → corregir → medir a los 8 fallos del agente durante la fase 10.A ([loop-mejora.md](docs/loop-mejora.md)):

- **Hechas y medidas:** 2 correcciones (la prueba de regresión de F1 y la reparación del CI de F7).
- **Propuestas con su métrica:** 3 líneas de AGENTS.md, el fixture `con_api`, una fábrica de datos de prueba, una prueba contra mutaciones a medias y 3 prácticas del agente.
- **Brecha detectada:** no se miden los tokens del agente de desarrollo.

### 3.19 Lab de evals: tres tareas y pass@5 — 29 de octubre de 2026

Tres evals sobre el producto, uno por pieza del harness: L1 contexto, L2 entorno y L3 herramientas ([evals-lab.md](docs/evals-lab.md)). El runner ganó `--preparar` y `--calificar` para calificar el trabajo de un agente externo sobre una copia limpia del commit base, el paso `copiar` para inyectar pruebas ocultas y `entorno.ignorar` para los artefactos generados. Controles negativo y positivo en verde para los tres.

- **Resultado:** 14/15 (L1 5/5, L2 5/5, L3 4/5) con los graders v2. Con los v1 habría sido 9/15: dos graders rechazaban trabajo correcto.
- **Único fallo real:** L3-r5 no registró la herramienta en las trazas, y ninguna prueba del producto lo exige.
- **Bug del producto encontrado por los agentes:** el `Literal` de `Aviso` no admitía los avisos de agenda. Corregido en el PR #1 (commit `e43df1c`).
- **HTML:** vista 07 «Evals del lab», con el resultado de cada intento y las lecciones.

### 3.20 SPEC cerrado con las preguntas del lab — 29 de octubre de 2026

Se cerraron con el usuario las tres decisiones que los agentes preguntaron en el lab. Quedaron en el SPEC (§23 y §34), en el contrato técnico v1.3 (§1) y en el SPEC_REFINADO del producto (v1.11, Etapa 10, decisiones 13–15):

- **Modo de la política por entorno:** `desarrollo` → `demo`, `pruebas` → `piloto_interno`, `produccion` → `produccion`.
- **Conteo de citas de un día:** se cuentan `reservada` y `finalizada`, por la hora de inicio en la zona de la agenda.
- **Modo básico del chat:** sin herramientas de agenda; remite a la pantalla Agenda.

## 4. Verificaciones realizadas y alcance

| Verificación | Resultado registrado | Qué demuestra |
|---|---|---|
| Descubrimiento y nueve inferencias | Completados en la etapa inicial | Modelo/contexto reportados y consumo de esos ejemplos. |
| Tokenizador frente a usage | Coincidencia en nueve muestras | Conteo del payload/plantilla medidos, no cualquier configuración futura. |
| Suite `python -m unittest discover -s tests -v` | Cuatro pruebas aprobadas en la revisión v0.6 | Muestras/rutas caben, contexto menor invalida rutas previas, mismatch invalida calibración y exceso se rechaza antes de generar. |
| HTML y ocho recorridos | QA histórica sin errores de consola registrados | Simulación y contadores; no backend ni entrega de mensajes. |
| Auditoría documental v0.6 | Enlaces locales, JSON demo y A01–A41 comprobados | Coherencia documental y perfil sin habilitación productiva. |
| Controles del eval D02 con el runner | Negativo falla, positivo pasa; reportes en `reports/evals/` (28 de octubre) | El eval no es trivial ni imposible; no mide todavía ningún agente. |
| Suite `unittest` con el runner | 10 pruebas aprobadas en unos 8 s | Runner con agentes simulados: aceptado, fuera de alcance, plazo, paso no soportado, eval bloqueado. |
| Migración `0011_agenda` en PostgreSQL 18 temporal | 9 pruebas de restricciones según el contrato (28 de octubre) | Exclusión de solapes, una cita activa por caso, duración, inmutabilidad y permisos del chat; no prueba la lógica de servicio |
| Concurrencia, carga, restauración y dominio LLM | Pendientes | No existe evidencia operativa de esas garantías. |

## 5. Trabajo pendiente, en orden de dependencia

### 5.1 Siguiente bloque de trabajo (29 de octubre de 2026)

Pendientes acordados al cerrar el SPEC con las preguntas del lab. Se retoman en este orden:

1. ✅ **Publicación:** HARNESS_UTI publicado en `main` (commit `481634e`).
2. **PR #1 (fase 10.A):** CI 4/4 verde y sin conflictos con `MVP` (commit `2615dda`). ⏳ El merge lo hace el usuario: el agente no tiene permiso para mergear sin revisión.
3. **Aplicar las decisiones del 29 de octubre en el código:** el modo por entorno (hoy solo existe `cargar_demo` para desarrollo) en la fase 10.B. El conteo por día y el modo básico entran en la fase 10.E.
4. ✅ **Correcciones del loop de mejora en el producto** (rama local `loop-mejora-1`, commit `4857104`; se publica cuando el PR #1 esté en `MVP`):
   - una prueba de arquitectura: toda herramienta del chat está en `ENUMS["herramienta"]` de `shared/trazas.py`;
   - en AGENTS.md: cómo regenerar los tipos del frontend y la política de migraciones ya aplicadas;
   - el fixture `con_api`, una fábrica de datos y una prueba contra mutaciones a medias.
5. **Fase 10.B** (disponibilidad, solicitudes y reserva automática) con TDD y su puerta G10.B.
6. **Maqueta de la pantalla Agenda** revisada con Bienestar, antes de la fase 10.D.
7. **Medición 2 del lab:** tareas más difíciles y pass@5 otra vez después de aplicar el punto 4, para comparar la tendencia. Medir tokens y tiempo cuando haya una CLI de agente.

### 5.2 Pendientes generales

1. Incorporar la [Etapa 10](docs/propuesta-etapa-10-agenda.md) al SPEC_REFINADO del producto (v1.10) y empezar la fase 10.A con TDD. Antes de un piloto, obtener la aprobación o excepción firmada del modelo activo (G1).
2. Añadir al runner una opción de repositorio de origen para ejecutar evals sobre el producto (D01).
3. Aprobar con Bienestar la política de agenda: profesionales, horarios, feriados, cupos, plazos por nivel y regla de asignación (G2/G4).
4. Registrar la aplicación en Entra ID y definir el alcance de coordinación (G3).
5. Implementar agenda, solicitudes, reserva, conciliación y resultado como intervención, con las pruebas del método del producto (G5).
6. Implementar la pantalla de agenda; mantener el HTML explicativo identificado como simulación.
7. Implementar ejecutor de presupuestos, adaptador de intención/herramientas y evaluación de dominio antes de activar O1/O2 (G6). O0 puede validarse independientemente.
8. Ejecutar aceptación aplicable, concurrencia, carga y recuperación; definir alertas, retención y responsables (G7).
9. Ejecutar el A/B de desarrollo cuando exista el esqueleto funcional. No usar ese experimento como sustituto de pruebas del calendario.
10. Elegir el agente de desarrollo y su envoltorio de señales, ejecutar D02 con N = 10 como primera línea base y separar las suites en CI; activar D01 y los evals de runtime cuando existan el esqueleto y el runtime.
11. Publicar las próximas modificaciones locales cuando corresponda y registrar commit y alcance de la publicación.

Los valores iniciales y objetivos técnicos del spec son propuestas verificables. No se declara que se hayan eliminado todos los cuellos de botella sin implementar y medir el sistema.

## 6. Cómo mantener esta bitácora

Actualizar con cada entrega significativa: fecha local, solicitud/cambio, archivos, decisiones, verificaciones realmente ejecutadas, resultado y siguiente dependencia. Registrar commit solo después de crearlo y publicación solo después de verificarla. Distinguir siempre evidencia histórica, ejecución nueva y simulación. No guardar secretos ni datos reales de estudiantes.

No sobrescribir reportes históricos para aparentar una nueva validación. Una prueba pendiente sigue pendiente hasta contar con evidencia del entorno y versión correspondientes.
