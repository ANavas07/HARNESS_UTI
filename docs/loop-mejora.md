# Loop de mejora del harness

Cada fallo del agente alimenta el harness: **observar → diagnosticar → corregir → medir**. Cada corrección es un cambio pequeño, versionado y reversible, y se queda solo si la medición mejora. Este documento registra las iteraciones; el sistema de medición está en [calidad-evals.md](calidad-evals.md).

## Iteración 1 — fase 10.A de la agenda (28–29 de octubre de 2026)

**Agente observado:** el agente de desarrollo (Claude Code) construyendo la fase 10.A en el producto, rama `etapa-10-agenda`, PR [ANavas07/GRUPO2_SEGUIMIENTO#1](https://github.com/ANavas07/GRUPO2_SEGUIMIENTO/pull/1).

**Fuente de las trazas:** la conversación de trabajo, los 14 commits de la rama, los registros del CI y las corridas de pruebas y mutaciones.

**Límite:** no hubo corridas repetidas de la misma tarea. No hay pass@N; las señales son de una sola ejecución.

### 1. Observar

| # | Qué intentó el agente | Dónde falló | Quién lo detectó | Costo |
|---|---|---|---|---|
| F1 | Ampliar los tipos de `core.notificaciones` en la `0011` | Partió de la lista de la `0006` y borró `deriva`, que había agregado la `0007` | La suite completa (`test_itm8_una_deriva...`), después del commit | 1 commit de corrección y una versión nueva del contrato |
| F2 | Marcar avisos obsoletos desde la API | `app_api` no tenía `UPDATE` sobre `core.notificaciones` | Prueba de integración corrida como `app_api` | 1 cambio en la migración y una versión nueva del contrato |
| F3 | Escribir los helpers de datos de `test_agenda_esquema.py` | 4 errores seguidos: orden de claves foráneas, corte repetido, solicitud duplicada, un caso abierto por persona | Las propias pruebas | 4 rondas rojas antes de verde, ninguna por la migración |
| F4 | Correr las 46 mutaciones con un límite de 590 s | El límite cortó la corrida y quedaron **7 archivos mutados** en el árbol de trabajo | El agente, al ver `.mutaciones_respaldo` | Restauración manual con el runner y otra corrida completa (~25 min) |
| F5 | Editar dos archivos y volver a correr las pruebas | La herramienta rechazó las ediciones (archivo sin leer) y **las pruebas corrieron sobre el código sin cambios**: «46 passed» no probaba nada | El agente, al leer el error de la herramienta | Una corrida desperdiciada; riesgo de un falso verde |
| F6 | Agregar mutaciones con un script en heredoc | `\n` se convirtió en un salto real dentro de un literal: `SyntaxError` | El intérprete, de inmediato | Una corrección |
| F7 | Abrir el primer PR del repositorio | El CI estaba en rojo en `MVP` desde el 15 de octubre (lint sobre `build/`), así que **la suite nunca había corrido en Linux**. Detrás aparecieron gitleaks sin permiso, PostgreSQL sin socket y un PDF dependiente de la plataforma | El CI del PR, con Auto-fix | 3 commits de corrección; dos semanas sin señal |
| F8 | Registrar las pruebas en la bitácora | Escribió «31 pruebas» a mano cuando eran 29 | El agente, al contar con `--collect-only` | 1 commit de corrección |

**Señales de la iteración** (formato de calidad-evals §4):

| Señal | Valor | Lectura |
|---|---|---|
| Intentos hasta verde | E10-T1: 5 · E10-T6: 2 · E10-T2/T3/T4: 2 | E10-T1 se encareció por los datos de prueba (F3), no por la migración |
| Comandos fallidos | 3: heredoc, edición no aplicada, límite de tiempo | Ninguno por el producto: todos del entorno y las herramientas del agente |
| Preguntas al humano | 4: publicación, asignación, política, maqueta | Las 4 eran decisiones del usuario; ninguna pedía información ya escrita |
| Tokens por tarea | **No medido** | No hay instrumentación del agente de desarrollo: es una brecha del harness |
| Resultado final | 1.733 pruebas en Windows y Linux; mutaciones 46/46; CI 4/4 | El código quedó bien; el costo estuvo en llegar a verde |

### 2. Diagnosticar

| # | Pieza del harness que faltó | Diagnóstico |
|---|---|---|
| F1 | **Contexto** | Nada le indica al agente que una restricción `CHECK` puede haber cambiado en migraciones posteriores. El contrato técnico se escribió leyendo hasta la `0006`. |
| F2 | **Verificación** (funcionó) | Probar los servicios con el rol real (`app_api`) atrapó el permiso faltante. Es una práctica que debe quedar fija para toda prueba nueva de servicios. |
| F3 | **Fixture** | No existe una fábrica común de casos, solicitudes y citas. Cada archivo arma su propio `caso()` y cada uno redescubre las restricciones del producto: corte único por periodo, un caso abierto por persona. |
| F4 | **Entorno** | AGENTS.md no dice que las mutaciones tardan unos 25 min ni que cortarlas deja código mutado. Nada impide hacer commit en ese estado. |
| F5 | **Verificación** | No hay una comprobación de que el cambio esté en el árbol antes de dar por buena una corrida. Una suite en verde sobre el código viejo parece un éxito. |
| F6 | **Herramienta** | Escribir código Python con escapes desde un heredoc de shell es frágil. Debe usarse el editor de archivos. |
| F7 | **Entorno / verificación** | El CI en rojo se normalizó: la señal «comandos fallidos > 0 sostenido» estuvo dos semanas sin dueño. Además, el CI solo corría en `push` a ciertas ramas: la suite en Linux no tenía uso real. |
| F8 | **Contexto** | Los números de la bitácora se escriben a mano en vez de copiarse de la salida de un comando. |

### 3. Corregir (propuesta mínima, una pieza por fallo)

| # | Corrección | Tipo | Dónde | Estado |
|---|---|---|---|---|
| F1 | Prueba de regresión de los tipos de aviso anteriores y mutación «se pierde el aviso de deriva» | Prueba | Producto | ✅ Hecho en el PR |
| F1 | Una línea en AGENTS.md: «Antes de reescribir una restricción existente, buscar la última migración que la tocó: `grep -n <nombre> backend/db/migrations/versions/*.py`» | AGENTS.md | Producto | Propuesto |
| F2 | Fixture `con_api` en `tests/integration/conftest.py`: conexión con `app_api` dentro de una transacción que se deshace, para toda prueba de servicio nuevo | Fixture | Producto | Propuesto (hoy vive solo en `test_agenda_servicios.py`) |
| F3 | Módulo `tests/fabricas_agenda.py` con `corte()`, `caso(estado, nivel)`, `profesional()`, `solicitud()` y `cita()`, que respeten las restricciones del producto | Fixture | Producto | Propuesto, antes de la fase 10.B (la usarán reserva, planificador y conciliación) |
| F4 | Prueba en la suite rápida: `test_no_hay_una_corrida_de_mutaciones_a_medias` (falla si existe `backend/.mutaciones_respaldo`), y una línea en AGENTS.md: «Las mutaciones de un objetivo grande tardan ~25 min: no cortarlas; si se cortaron, volver a correr el runner antes de hacer commit» | Prueba + AGENTS.md | Producto | Propuesto |
| F5 | Práctica del agente: antes de dar por buena una corrida, comprobar el cambio en el árbol (`git diff --stat`) | Práctica del agente | Memoria del agente | Propuesto |
| F6 | Práctica del agente: código con escapes, siempre con el editor de archivos | Práctica del agente | Memoria del agente | Propuesto |
| F7 | `pull-requests: read` para gitleaks, `build/` excluido de ruff, socket de PostgreSQL en la carpeta del clúster y PDF comparado por palabras | CI y pruebas | Producto | ✅ Hecho en el PR |
| F7 | Una línea en AGENTS.md: «El CI en rojo en `MVP` se arregla antes de seguir: no se normaliza» | AGENTS.md | Producto | Propuesto |
| F8 | Práctica: los conteos de la bitácora se copian de `pytest --collect-only -q` | Práctica del agente | Memoria del agente | Propuesto |

Las tres líneas de AGENTS.md suman tres renglones. El AGENTS.md del producto tiene hoy 14 líneas, lejos del límite de 100 del antipatrón «AGENTS.md que intenta explicarlo todo».

### 4. Medir

| Corrección | Métrica | Línea base de esta iteración | Criterio para quedarse |
|---|---|---|---|
| F7 (hecha) | Checks del CI en verde por commit | 0/4 → **4/4** en `eac725b`; 1.733 pruebas en Linux | Se queda: medido |
| F1, F4 y F7 en AGENTS.md | Fallos del mismo tipo en la fase 10.B | 1 restricción perdida, 1 corrida cortada y 2 semanas de CI en rojo | Cero repeticiones en 10.B. Si se repite, la línea no sirve: reescribirla o revertirla |
| F3 (fábrica) | Intentos hasta verde por tarea con datos de prueba | E10-T1: 5 | ≤ 2 en las tareas de 10.B que creen casos y citas |
| F2 (`con_api`) | Permisos faltantes detectados en CI en lugar de en pruebas | 0 en CI (F2 se detectó en pruebas) | Se mantiene en 0 |
| F5, F6 y F8 | Comandos fallidos del agente por fase | 3 | ≤ 1 en 10.B |
| Brecha de tokens | Tokens por tarea del agente de desarrollo | Sin dato | Instrumentar con el contrato `EVAL_SENALES` del runner antes de comparar |

**pass@N:** para medir con rigor, el patrón de F1 sirve como eval de desarrollo. Una tarea D03, «agrega un tipo de aviso nuevo a `core.notificaciones`», con un grader que exija conservar todos los tipos anteriores, corrida N = 10 sin y con la línea nueva de AGENTS.md. Requiere que el runner acepte el repositorio del producto, una tarea ya pendiente en calidad-evals §9.

**Decisión de esta iteración:** las correcciones hechas (F1 prueba, F7) se quedan porque ya están medidas. Las propuestas se aplican como cambios separados al harness, en un PR propio o al inicio de la fase 10.B, y se miden al cerrarla.
