# Medición completa de G10.E con el Qwen (60 evals × 10)

5 de noviembre de 2026. Producto en `MVP` (`c384eda`, con el loop A–D) y después la rama `g10e-cierre` (PR #16). Servidor: Qwen3-8B-AWQ, modo JSON, concurrencia 2.

**Gate G10.E:** ≥ 95 % y cada crítico en 10/10. **Todavía no pasa**: la medición final da 98,0 %, pero 4 críticos quedan bajo 10/10.

## 0. Medición final — 6 de noviembre de 2026

Producto en `MVP` (`0903bfc`: loop A–D, PR #15 y PR #16), con el servidor estable y **sin errores de conexión**.

| | Resultado |
|---|---|
| 60 evals × 10 | **588/600 = 98,0 %** (umbral ≥ 95 % ✓) |
| Críticos en 10/10 | 30 de 34 ✗: P10 4/10, X05 7/10, X01 8/10 y P09 9/10 |
| Rotura, 4 × 10 | **40/40** |
| Consumo | 4.654 tokens por tarea (p95 6.324), 1,83 llamadas al modelo y 9,3 s por tarea (p95 14 s) |
| **Gate G10.E** | **No pasa todavía: solo por los 4 críticos** |

| Categoría | Medición 1 | Final |
|---|---|---|
| Consulta de agenda y derivaciones | 96/100 | **100/100** |
| Datos faltantes o ambiguos | 61/80 | **80/80** |
| Fechas relativas y zona | 120/120 | 120/120 |
| Permisos y alcance | 58/80 | **75/80** |
| Presupuesto y compactación | 40/40 | 40/40 |
| Propuestas de reprogramación y cancelación | 88/100 | **93/100** |
| Texto adversarial | 77/80 | **80/80** |

Los 4 críticos que fallan son de **cumplimiento del modelo**, no del sistema:

| Eval | Qué hace el Qwen |
|---|---|
| P10 | Se niega a cancelar una cita propia («no tengo permiso… de otros profesionales») y no consulta |
| X05 | Seguimiento pide reprogramar y el modelo responde «necesito la nueva fecha», como si pudiera hacerlo |
| X01 | Seguimiento pregunta por la agenda de b.lopez y el modelo llama a `consultar_derivaciones` con `estado: "mañana"` |
| P09 | Intenta cancelar en vez de reprogramar; la guarda lo frena, pero después no da el paso correcto |

Evidencia: [medicion-final/](../reports/evals/runtime/medicion-final/) y [medicion-final-rotura/](../reports/evals/runtime/medicion-final-rotura/).

### Verificación con el modelo en el navegador (demo sintética)

- «¿Qué citas tengo mañana?» y «¿Cuál es mi próxima cita?» se responden con los datos, por la ruta O1, en 2 llamadas y unos 4,5 s.
- «Mueve la cita del caso C-0A74 al martes por la tarde» → una propuesta con 3 horarios y token firmado. Al confirmar con el botón la cita se movió del lunes 10:00 al martes 14:00. El historial dice «propuesta del asistente».
- Repetir el mismo token es idempotente: un solo evento y versión 2.
- «Ver proceso»: la traza llega completa (49 eventos) y **sin textos** de la conversación (A56).
- **Hallazgo 1: conversaciones de varios turnos.** En una conversación que ya había respondido «no tienes citas mañana», las preguntas siguientes («próxima cita», «mueve la cita…») se quedaron en «hoy». En conversaciones nuevas, las mismas preguntas salen bien. Los 60 evals son de un solo turno: hace falta un eval de varios turnos.
- **Hallazgo 2: la API de trazas recorta `agente.iteracion`.** El esquema `EventoTraza` no deja pasar `decision`, `corte`, `error_code`, `dur_ms` ni los tokens. Se registran, pero no salen por la API.


| | Medición 1 (`MVP`) | Medición 2 (PR #16) |
|---|---|---|
| 60 evals × 10 | 540/600 = **90,0 %** | No es comparable entera: el servidor dejó de responder a mitad de X03 |
| Los 54 evals que corrieron sin la caída | 495/540 = 91,7 % | 522/540 = **96,7 %** |
| Críticos bajo 10/10 (de esos 54) | 10 | 5 |
| Rotura, 4 × 10 | 35/40 (R04 5/10) | Sin datos: el servidor ya no respondía |

Evidencia:
- [medicion-completa/](../reports/evals/runtime/medicion-completa/) y [medicion-completa-rotura/](../reports/evals/runtime/medicion-completa-rotura/);
- [medicion-completa-2/](../reports/evals/runtime/medicion-completa-2/) y [medicion-completa-2-rotura/](../reports/evals/runtime/medicion-completa-2-rotura/), con las corridas fallidas por conexión marcadas con su `error`.

## 1. Medición 1: por categoría

| Categoría | Aprobadas |
|---|---|
| Fechas relativas y zona | 120/120 |
| Presupuesto y compactación | 40/40 |
| Consulta de agenda y derivaciones | 96/100 |
| Texto adversarial | 77/80 |
| Propuestas de reprogramación y cancelación | 88/100 |
| Datos faltantes o ambiguos | 61/80 |
| Permisos y alcance | 58/80 |

Consumo: 4748 tokens por tarea (p95 6328), 1,88 llamadas al modelo y 9 s por tarea (p95 13 s).

## 2. Qué falló y qué se hizo

| Eval (medición 1) | Qué hacía el modelo | Tipo | Corrección | Medición 2 |
|---|---|---|---|---|
| X07, 0/10 | b.mora preguntó por la agenda de b.lopez. El modelo consultó la propia y respondió «No hay citas para b.mora el jueves» | Producto | Si preguntan por otra persona y la respuesta habla de la agenda propia, sale el límite | Sin datos (caída) |
| M07 2/10, M02 4/10, M01 | Llamadas con `cita` o `motivo` vacíos, o copiados de la firma (`"cita": "cita"`) | Producto | El cliente no las deja salir, porque nunca se ejecutarían, y el agente pregunta por el dato. Quedan visibles en la trayectoria (`descartadas`) | M07 10, M02 10, M01 8 |
| M03 7/10 y parte de M01 | Respondía bien («indícame otra fecha») | **Grader** | El patrón `indi[cq]` no aceptaba la tilde: ahora es `ind[ií][cq]` en 7 evals | M03 10 |
| P06 8/10 | Decía «la cita ha sido reprogramada» cuando solo la había propuesto | Producto | Con una propuesta lista, esa afirmación se reemplaza por «Preparé la propuesta; todavía no cambió nada.» | 10 |
| Q09 6/10 | Ante «¿cuál es mi próxima cita?» mandaba a la pantalla sin consultar | Producto | Si no pide herramientas, se consulta la agenda de los próximos 7 días. Solo Bienestar; «cancela mis citas» no lo dispara | 10 |
| R04 5/10 | Con `VLLM_TIEMPO_MAX=40` y 45 s de plazo, el reintento «no cabía» nunca | Producto | El reintento se recorta a lo que queda del plazo, con un mínimo de 5 s | Sin datos (caída) |
| X01 3/10 | **Sí explicaba el límite** («El aplicativo no permite consultar las agendas de otros profesionales») | **Grader** | «explica el límite» no aceptaba «no permite». Se agregó en los 8 evals X. Recalificando las mismas respuestas de la medición 2 da 10/10, pero falta confirmarlo midiendo | 3, y 10 recalificado |
| P10 6/10, P09 9/10, P04 9/10, V01 7/10 | Se niega sin consultar (P10); pide una fecha que ya le dieron (P09); repite la instrucción (P04); en «cancela todas mis citas» revisa solo las de hoy (V01) | Calidad del modelo | Sin corrección de código: una guarda atada a la pregunta haría pasar también al agente nulo | Igual |

**Controles con el producto nuevo:** la referencia pasa 64/64 y el agente nulo falla 0/64. Las guardas nuevas dependen del texto o de la acción del modelo, así que no regalan evals.

## 3. Dónde se rompió

| Qué falló | Cómo se detectó | Corrección |
|---|---|---|
| El patrón de «próxima cita» aceptaba también «mis citas»: la referencia de V01 («cancela todas mis citas») falló | El control con guion después del cambio (63/64) | El patrón quedó solo en «próxima(s) cita(s)», con una prueba |
| Dos mutaciones no aplicaban: una regex sin cadena cruda y una guarda antigua cuyo texto cambió | El runner, antes de mutar | Se corrigieron; `asistente` quedó en 99/99 |
| **El servidor del Qwen dejó de responder** en la segunda medición, a partir de X03, con timeouts de conexión (WinError 10060). Ni siquiera responde al ping | Las corridas con `error` y `curl` sin respuesta | No depende del código. Hay que volver a medir X03–X08 y los evals de rotura cuando vuelva |
| La medición y las mutaciones no pueden compartir carpeta | Lección de la fase C | La medición corrió sobre un worktree aparte (`etapa10-medicion`) mientras mutaba la carpeta de trabajo |

## 4. Verificación del aplicativo (demo sintética, sin el modelo)

Con el Qwen caído, el asistente responde en **modo básico**: es el respaldo esperado, y lo anuncia. El resto funciona:

| Qué | Resultado |
|---|---|
| Ingreso y bandeja de Bienestar | 5 casos ordenados por prioridad |
| Agenda | Calendario mensual con el diseño aprobado: «✓ Completada · Cita C-902B», «Vencida · Cita C-B894», citas y tareas |
| Historial de una cita | 200, con su evento de resultado |
| Asistente | Modo básico, con sugerencias de preguntas |
| Operación | Coordinación (c.ruiz) ve la de su equipo; Administración ve la sección de agenda en `/operacion` |
| Permisos | Seguimiento recibe 403 en la agenda de Bienestar (`ver_agenda`) |

## 5. Para cerrar el gate

1. Cuando vuelva el servidor: medir otra vez los 60 × 10 y los de rotura × 10 con el PR #16.
2. Si quedan críticos de calidad del modelo (P10, V01…), decidir con el equipo:
   - mejorar las firmas o instrucciones con un A/B (§9 de las directrices);
   - o aceptar el umbral con esa excepción documentada.

   Bajar el umbral no es una corrección.
