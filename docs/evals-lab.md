# Lab de evals: tres tareas, tres graders y pass@5

Registro de seguimiento del laboratorio «escribir evals». Cada medición nueva se agrega como una fila fechada: **el número importa menos que la tendencia**, así que se compara cada vez que cambia el harness. Los criterios generales están en [calidad-evals.md](calidad-evals.md) y las lecciones, en [loop-mejora.md](loop-mejora.md).

## Paso 1 — tres tareas, tres graders

Tareas que una persona resolvería en 15–30 minutos, cada una sobre una pieza distinta del harness del producto (repositorio GRUPO2_SEGUIMIENTO, rama `etapa-10-agenda`).

| Eval | Pieza | Tarea | Pregunta que responde | Grader | Commit base |
|---|---|---|---|---|---|
| [L1](../evals/lab/L1-contexto-endpoint-politica.yaml) | **Contexto** | Endpoint `GET /agenda/politica` siguiendo las convenciones del producto | ¿El agente encuentra dónde va el código y cómo se prueba (permisos, modelo de respuesta, contrato OpenAPI) solo con AGENTS.md y el repositorio? | Prueba oculta del endpoint (200, 404, 403, modo por entorno) + matriz de permisos + contrato OpenAPI + ruta en un router + ruff + mypy + alcance | `eac725b` |
| [L2](../evals/lab/L2-entorno-bug-deriva.yaml) | **Entorno** | Bug que se vio con datos reales: el aviso de deriva falla con `CheckViolation` | ¿Los fixtures del proyecto bastan para reproducirlo, o el agente tiene que inventar datos? | Prueba de regresión oculta de los tipos de aviso + flujo de deriva + migraciones + ruff + alcance | `64c289b` (el bug real F1 de la iteración 1) |
| [L3](../evals/lab/L3-herramientas-tool-citas.yaml) | **Herramientas** | Herramienta `citas_por_profesional` del asistente | ¿Usa la herramienta tipada y la vista de solo lectura, o intenta SQL crudo? ¿Se recupera del error de permisos de `app_chat_ro`? | Prueba oculta: respuesta correcta en el día local, roles, esquema, trazas, ejecución con `app_chat_ro` + pruebas del chat + ruff + mypy + cero SQL fuera de `herramientas.py` | `eac725b` |

### Criterios de un buen eval, comprobados

| Criterio | Cómo se cumple |
|---|---|
| Tarea realista, no de juguete | Las tres son trabajo pendiente o real del producto; L2 es un fallo que ocurrió |
| Grader objetivo, sin juicio humano | Solo comandos con código de salida y pruebas ocultas; ningún paso requiere leer el código |
| Entorno aislado | Cada corrida parte de una copia nueva del commit base hecha con `git archive`; las pruebas ocultas se copian **después** de que el agente termina |
| Suficientemente difícil para que el harness importe | Ninguna se resuelve sin descubrir convenciones no escritas en la tarea: la matriz de permisos, el contrato OpenAPI, las trazas, `app_chat_ro` |

### Controles (28–29 de octubre de 2026)

| Eval | Control negativo (código base) | Control positivo (solución de referencia) |
|---|---|---|
| L1 | ✅ Falla en los pasos 2 (endpoint) y 5 (ruta) | ✅ Aceptado |
| L2 | ✅ Falla en los pasos 2 (regresión) y 3 (deriva) | ✅ Aceptado (el arreglo real del commit `49c4c3a`) |
| L3 | ✅ Falla en el paso 2 (herramienta) | ✅ Aceptado |

Los demás pasos pasan sobre el código base: los graders no fallan por razones ajenas a la tarea. Al construir las referencias, el grader rechazó dos veces el estilo de **mi propia** solución (largo de línea), y detectó que las pruebas generan artefactos (trazas, caché de import-linter). Por eso el YAML tiene `entorno.ignorar`.

## Paso 2 — medir pass@5 y registrar las señales

**Cómo se midió:** no hay una CLI de agente instalada en este equipo. Cada corrida la hizo un subagente de Claude que recibió solo la tarea y su carpeta. El runner la calificó después con `--calificar`.

**Señales:** intentos, comandos fallidos y preguntas los informa el propio agente en un JSON. No son medidas independientes.

### Medición 1 (29 de octubre de 2026, commits base de la tabla del Paso 1)

| Eval | Pieza | Corridas (r1…r5) | pass@5 | Mediana de intentos hasta verde | Mediana de comandos fallidos | Mediana de preguntas |
|---|---|---|---|---|---|---|
| L1 | Contexto | ✅ ✅ ✅ ✅ ✅ | **5/5** | 2 | 1 | 3 |
| L2 | Entorno | ✅ ✅ ✅ ✅ ✅ | **5/5** | 3 | 0 | 2 |
| L3 | Herramientas | ✅ ✅ ✅ ✅ ❌ | **4/5** | 2 | 0 | 2 |
| **Total** | | | **14/15** | | | |

**Lectura:** 14/15 está en el rango de un harness sólido para estas tareas, así que toca subir la dificultad de los evals. El número no dice que el harness esté completo: las señales y la única corrida fallida muestran qué le falta (ver lecciones).

Reportes de la corrida en `reports/evals/2026-10-29/` (un JSON por corrida y un `-resumen.json` por eval).

### Correcciones del grader durante la medición

Dos graders rechazaron corridas correctas en su primera versión. Se corrigió la regla y se recalificaron las cinco corridas del eval con la nueva. Antes de recalificar se repitieron los controles: con el código base sigue fallando y con la referencia sigue pasando.

| Eval | v1 | Por qué la v1 estaba mal | v2 |
|---|---|---|---|
| L1 | 2/5 | `solo_modifica` no permitía `frontend/src/__tests__/apiFalsa.ts`, la API falsa que refleja las acciones por rol: actualizarla es lo correcto | 5/5 |
| L3 | 2/5 | `solo_modifica` no permitía los registros que ya listan cada herramienta (`graficos.py`, `ProcesoAgente.tsx`, `analizar_trazas.py`). Ninguno accede a la base: el objetivo «cero SQL fuera de las herramientas» se cumplía | 4/5 |

Con los graders v1, el total habría sido 9/15. Esa diferencia mide errores del examen, no del agente. Antes de confiar en un eval nuevo hay que revisar a mano sus primeros rechazos.

### La corrida que falló de verdad

**L3-r5** implementó bien la herramienta: sus pruebas, el rol `app_chat_ro` y la vista de solo lectura estaban correctos. Pero no registró el nombre en `shared/trazas.py` (`ENUMS["herramienta"]`), y la prueba oculta `test_las_trazas_reconocen_la_herramienta` lo detectó. Ninguna prueba del repositorio exige ese registro, así que las pruebas del propio agente pasaban. **Pieza que falta: contexto.** Hace falta una prueba de arquitectura que obligue a registrar cada herramienta del chat en las trazas, o una línea en AGENTS.md.

### Lecciones (entrada para el loop de mejora)

| # | Señal | Pieza | Corrección propuesta |
|---|---|---|---|
| 1 | 4/5 corridas de L1 no pudieron regenerar `frontend/src/api/esquema.ts`: no hay `node_modules` y AGENTS.md no dice qué hacer | Entorno | Documentar en AGENTS.md cómo regenerar los tipos, o hacer que la prueba de contrato los compare sin npm |
| 2 | 5/5 corridas de L1 preguntaron qué modo de política usan los entornos `pruebas` y `piloto_interno` | Especificación | ✅ Cerrada el 29-10-2026: `pruebas` → `piloto_interno` (SPEC §23 y §34) |
| 3 | 3/5 corridas de L2 detectaron por su cuenta que el `Literal` de `Aviso` en `esquemas.py` no admite los tipos de aviso de agenda: `GET /notificaciones` fallará cuando exista uno | Producto | ✅ Corregido en el PR #1 (commit `e43df1c`, con prueba de regresión de punta a punta) |
| 4 | 5/5 corridas de L2 preguntaron si la base local ya tiene la 0011 aplicada (varias agregaron una 0012 de reparación) | Contexto | Documentar la política de migraciones ya aplicadas: no se editan, se repara con una nueva |
| 5 | 5/5 corridas de L3 preguntaron si cuentan las citas `finalizada` y en qué zona se define «el día»; 2/5, si la herramienta también va en el modo básico sin LLM | Especificación | ✅ Cerrada el 29-10-2026: se cuentan `reservada` y `finalizada` por hora de inicio local; el modo básico no tiene herramientas de agenda (SPEC §34, contrato v1.3) |
| 6 | L3-r5 no registró la herramienta en las trazas | Contexto | Prueba de arquitectura: toda herramienta del chat está en `ENUMS["herramienta"]` |
| 7 | Los graders v1 de L1 y L3 rechazaron trabajo correcto | Evals | Revisar a mano los primeros rechazos de cada eval nuevo antes de usar su número |

### Con qué honestidad leer estos números

- El agente fue un subagente de Claude con las herramientas de un desarrollador. No hay una CLI de agente instalada en este equipo, así que no se midieron tokens ni tiempo del agente: el tiempo del reporte es solo el del grader.
- Las señales (intentos, comandos fallidos, preguntas) las informa el propio agente. El pasa/no pasa lo decide el grader.
- Las «preguntas» se registraron sin humano disponible: el agente decidió y anotó la duda. En un uso real cada una habría sido una interrupción.
- Cinco corridas son una señal, no una estadística. Lo que importa es repetir la medición después de aplicar las correcciones y comparar.

## Cómo repetir la medición

```powershell
# 1. preparar una copia limpia por corrida (código del commit base + archivo con la tarea)
python scripts/ejecutar_eval.py evals/lab/L1-contexto-endpoint-politica.yaml --preparar <carpeta>/L1-r1
# 2. el agente trabaja en <carpeta>/L1-r1 y escribe <carpeta>/L1-r1.senales.json
# 3. calificar las cinco corridas y obtener el resumen pass@5
python scripts/ejecutar_eval.py evals/lab/L1-contexto-endpoint-politica.yaml --calificar <carpeta>/L1-r1 <carpeta>/L1-r2 <carpeta>/L1-r3 <carpeta>/L1-r4 <carpeta>/L1-r5 --senales <carpeta>/L1-r1.senales.json <carpeta>/L1-r2.senales.json <carpeta>/L1-r3.senales.json <carpeta>/L1-r4.senales.json <carpeta>/L1-r5.senales.json
```

**Cómo leer el total:**

| Total | Lectura |
|---|---|
| 13–15 / 15 | Harness sólido para estas tareas: subir la dificultad de los evals |
| 8–12 / 15 | Normal: los fallos dicen qué falta |
| < 8 / 15 | Revisar primero contexto y entorno antes de tocar las herramientas |
