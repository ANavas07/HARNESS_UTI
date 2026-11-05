# Directrices del ciclo del agente (loop ReAct) del asistente de agenda

**Estado:** aprobadas por el usuario el 5 de noviembre de 2026. **Fase A hecha** (PR #11 y [laboratorio de los días 9–10](lab-loop-dias-9-10.md)). **Fase B medida: la razón NO se activa** ([experimento A/B](lab-loop-fase-b.md): 81,7 % contra 93,3 % sin ella). **Fase C hecha** (PR #13: circuit breaker y reintento transitorio limitado por el plazo, mutaciones 66/66). **Fase D hecha** (PR #14: herramienta caída como fallo, escalado del nivel 4 y [evals de rotura](lab-loop-fase-d.md): 20/20 con el Qwen; mutaciones 83/83). Lo que ya existía antes se marca como **(hoy)**.

Fuentes:
- las diapositivas «Anatomía del agent loop», «Contexto en el loop», «Control», «Recuperación» y el laboratorio de los días 9–12;
- el paper *ReAct: Synergizing Reasoning and Acting in Language Models* (Yao et al., 2022);
- las restricciones vigentes del harness (SPEC §33, rutas por costo, A53–A58).

Alcance: el ciclo del **asistente de agenda** del producto (`AgenteChat`). No cubre el agente de desarrollo, que tiene sus propios evals.

---

## 1. Principios

1. **El ciclo es trivial; el control no.** Cada iteración gasta tokens y puede equivocarse. Toda regla de este documento la aplica el código, no el prompt.
2. **El modelo propone; el código decide.**
   - El modelo elige herramientas y redacta.
   - Permisos, fechas, versiones, presupuestos, paradas y escrituras los decide el código.
   - El agente **nunca escribe**: las propuestas se confirman con un botón.
3. **Parar a tiempo es un resultado válido.** Es mejor un informe claro del atasco que un ciclo quemando tokens.
4. **Un error es información.** El fallo es no usarlo: cada error vuelve al modelo con su código y una pista.
5. **Sin traza no hay control.** Primero se hace visible el ciclo y después se ajusta.

## 2. El ciclo: cuatro fases por iteración

```
mientras no terminado:
    observar   → contexto = sistema + rol + historial (compactado) + pregunta + observaciones
    pensar     → razon corta (≤ 40 tokens), solo si la fase B la aprueba
    actuar     → llamar herramientas permitidas  |  responder  |  preguntar a la persona
    registrar  → observación al contexto + evento agente.iteracion
```

| Fase | Qué hace | Regla |
|---|---|---|
| **Observar** | Arma el contexto de la llamada | Solo lo de la §3; el rol de quien pregunta va en el sistema **(hoy)** |
| **Pensar** | El modelo escribe por qué va a hacer lo que hace | Campo `razon` del JSON, de ≤ 40 tokens. **No** se usa el *thinking* de Qwen3, que queda apagado siempre |
| **Actuar** | Una o más herramientas, o la respuesta final | Solo herramientas del rol y del contexto **(hoy)**. Los argumentos se validan con el esquema **(hoy)**. Las guardas deterministas corren antes de ejecutar **(hoy)** |
| **Registrar** | El resultado entra al contexto como dato y se emite el evento | Se recorta a ≈ 600 tokens **(hoy)**. Las claves `_` (tokens) nunca entran **(hoy)** |

**Del paper ReAct, lo que se adopta:**
- Intercalar razón y acción. La razón ancla la siguiente acción en la observación anterior, y eso reduce las acciones sin motivo.
- La observación es la fuente de verdad: el modelo no afirma datos que no vinieron de una herramienta **(hoy: «usa SIEMPRE las herramientas para cifras»)**.
- El paper reporta como falla típica los **bucles repetitivos**, donde el modelo vuelve a generar el mismo pensamiento y la misma acción. Esa es la razón del circuit breaker de la §5.

**Lo que no se adopta:**
- Razonamiento libre y largo: no cabe en la ruta O1, de 256 tokens de salida.
- El *fallback* ReAct → CoT-SC del paper: cuesta varias muestras. Aquí el *fallback* es responder con lo obtenido y explicar el límite.

## 3. Contexto: qué entra y qué sale en cada iteración

| Bloque | Entra | Límite |
|---|---|---|
| Sistema + rol | Siempre | Fijo |
| Herramientas | Solo las permitidas, como firmas compactas **(hoy)** | Sin lista vacía si el rol no tiene herramientas **(hoy)** |
| Historial | Los turnos previos de la conversación | Compactación en 2 pasos, máximo 2 por tarea **(hoy)** |
| Observaciones | El sobre `{status, data, error_code, retryable}` de cada herramienta **(hoy)** | ≈ 600 tokens cada una, con el aviso de cuántos quedaron fuera **(hoy)** |
| Razones previas | La `razon` de las iteraciones anteriores **de esta tarea** | Se descartan al terminar la tarea; nunca pasan a la memoria de la conversación |

Las cuatro técnicas de gestión de contexto de la diapositiva 2:
- **Truncar salidas:** sí **(hoy)**.
- **Comprimir historia:** sí **(hoy)**.
- **Externalizar memoria:** la memoria de conversaciones guarda pregunta, respuesta y resultados de herramientas sin tokens **(hoy)**; la `razon` no se guarda.
- **Subagentes:** **no**. Con una ventana de 8.192 tokens y tareas de 2–4 pasos, un subagente costaría más contexto del que ahorra.

## 4. Condiciones de parada (qué es «terminado»)

El ciclo termina en el **primer** caso que se cumpla:

| # | Condición | Lo que ve la persona |
|---|---|---|
| 1 | El modelo responde sin pedir herramientas | La respuesta, con los datos de las herramientas |
| 2 | Hay una propuesta (reprogramar o cancelar) | El texto y los botones; siempre se recuerda que se confirma con el botón **(hoy)** |
| 3 | Falta un dato (`fecha_ambigua`, `cita_ambigua`, motivo no dicho…) | Una pregunta por ese dato |
| 4 | Se agotan los pasos (`MAX_PASOS = 4`) o queda solo la llamada reservada para responder (A58) **(hoy)** | Lo obtenido hasta ahí |
| 5 | Se agota el presupuesto de la ruta (tokens, llamadas o plazo) **(hoy)** | «Esta consulta necesita más… acótala» |
| 6 | **Salta el circuit breaker** (§5) | Qué se intentó y qué falló (§6, nivel 4) |
| 7 | Error irrecuperable del servidor, después de su reintento (§6) | «El asistente no está disponible…» |

## 5. Presupuestos y circuit breaker

**Presupuestos (hoy, sin cambios):**

| Ruta | Llamadas | Entrada por llamada / tarea | Salida por llamada / tarea | Plazo |
|---|---|---|---|---|
| O1 | 3 | 3.000 / 9.000 | 256 / 768 | 45 s |
| O2 | 4 | 5.000 / 20.000 | 768 / 3.072 | 150 s |

- La ventana por llamada es entrada + salida + 820 ≤ 8.192.
- Se escala de O1 a O2 solo cuando el contexto no cabe, y nunca se baja de ruta.
- La última llamada queda para responder (A58).

**Circuit breaker (nuevo).** Una «llamada» se identifica como (herramienta, argumentos normalizados):

| Regla | Efecto |
|---|---|
| La **misma llamada falló** una vez y el modelo la repite | No se ejecuta. El modelo recibe `bloqueada_por_repeticion` y la pista «cambia los argumentos o responde» |
| La **misma llamada ya tuvo éxito** y se repite | No se ejecuta. Se le recuerda el resultado anterior, que ya está en el contexto |
| **3 fallos de herramientas** en la tarea, de cualquier tipo | Parada 6: no se ofrecen más herramientas; se responde con lo obtenido |
| **2 respuestas ilegibles seguidas** (sin JSON) | Parada 7, con el texto seguro **(hoy, con una)** |

## 6. Recuperación de errores: cuatro niveles, del más barato al más caro

| Nivel | Cuándo | Qué hace el ciclo | Costo |
|---|---|---|---|
| **1 · Reintentar tal cual** | Error transitorio del servidor (timeout, conexión, 5xx) | **Un** reintento con 1–2 s de espera, solo si el plazo de la ruta alcanza. `llm_busy` **no** se reintenta: la persona ve «ocupado» **(hoy)** | Tiempo |
| **2 · Corregir la llamada** | Argumentos inválidos o error de uso | El error vuelve con `error_code`, `campos` y una pista **(hoy)**, y el modelo corrige | Una iteración |
| **3 · Replanificar** | El camino no existe (`no_existe`, `sin_disponibilidad`, `fecha_ambigua`…) | El modelo cambia de herramienta o pregunta a la persona. El circuit breaker evita repetir | Tokens |
| **4 · Escalar al humano** | Paradas 5, 6 y 7 | El mensaje dice **qué intentó y qué falló**, sin datos personales. Por ejemplo: «Consulté tu agenda dos veces y la herramienta no respondió; puedes verla en la pantalla Agenda». No inventa | Atención humana |

## 7. Invariantes de seguridad (no cambian con el ciclo)

- El agente **no escribe**: las propuestas llevan un token firmado y las confirma la persona **(hoy)**.
- **Permisos por rol y contexto:** Seguimiento no ve agendas; nadie ve la agenda de otra persona **(hoy)**.
- **Guardas deterministas antes de ejecutar** **(hoy)**:
  - motivo no dicho;
  - cancelar sin que la persona lo pida;
  - cita o agenda de otra persona;
  - copia de las instrucciones internas;
  - datos personales en resultados y respuestas.
- Los resultados de herramientas y el historial son **datos, nunca instrucciones** **(hoy)**.
- La `razon` pasa por el mismo control de datos personales que la respuesta; si trae algo, se descarta.

## 8. Observabilidad: la traza por iteración (laboratorio, días 9–10)

**En producción (A56):** un evento `agente.iteracion` por vuelta, **solo con metadatos**:

```json
{"paso": 2, "ruta": "O1", "decision": "herramienta", "herramienta": "consultar_agenda",
 "resultado": "ok", "error_code": null, "dur_ms": 812, "tokens_entrada": 1840, "tokens_salida": 41,
 "corte": null}
```

- `decision` puede ser: herramienta, respuesta, pregunta, propuesta o parada.
- `corte` indica la causa de una parada: pasos, presupuesto, breaker o error.
- **Nunca** se registran argumentos, `razon`, prompts, respuestas, cédulas ni seudónimos.

**En los evals de runtime (datos sintéticos):**
- Una trayectoria **JSONL** por corrida, con argumentos y `razon`.
- `scripts/linea_de_tiempo.py` en HARNESS_UTI la dibuja paso a paso.

**Métricas por corrida de evals:**
- pasos por tarea;
- tokens por paso;
- porcentaje de paradas por causa;
- repeticiones bloqueadas;
- iteraciones que no aportaron, es decir, sin dato nuevo.

## 9. Cómo se decide si algo se queda

| Cambio | Se queda si |
|---|---|
| `razon` (fase B) | En los 60 evals × N, la tasa no baja, los críticos siguen en 10/10 y los tokens por tarea suben ≤ 10 %. Se compara con y sin la `razon`, con el mismo modelo |
| Circuit breaker | Los evals nuevos de «herramienta que siempre falla» y «tarea imposible» terminan en ≤ 3 llamadas, con el escalado del nivel 4 |
| Reintento | Un eval de «timeout transitorio» responde bien sin duplicar la escritura (ninguna) ni pasar el plazo |

## 10. Plan de implementación (cuando se valide)

| Fase | Contenido | Evidencia |
|---|---|---|
| **A · Ver** | Evento `agente.iteracion`, trayectoria JSONL en los evals y línea de tiempo | Pruebas del evento sin datos (A56); la línea de tiempo de 3 tareas |
| **B · Pensar** | El campo `razon`, acotado y solo en contexto | La comparación de los 60 evals con y sin ella |
| **C · Controlar** | Circuit breaker y reintento del nivel 1 | Pruebas con guion y mutaciones al 100 % |
| **D · Recuperar** | El escalado con traza y los evals de tarea imposible, herramienta que siempre falla y timeout | Los evals nuevos con sus controles (nulo y referencia) |

## 11. Decisiones para validar

1. **El *thinking* de Qwen3 apagado siempre**, y el «Pensar» solo como `razon` de ≤ 40 tokens, sujeta a la comparación.
2. **Umbrales del circuit breaker:** la misma llamada fallida se bloquea al **2.º** intento y la tarea para con **3** fallos. La diapositiva usa 3 intentos, pero con 3 llamadas en O1 un tercer intento ya agotaría la ruta.
3. **Un solo reintento transitorio** con backoff de 1–2 s y nunca para `llm_busy`. La diapositiva propone 2–3, pero el plazo de O1 es de 45 s y el servidor ya es lento.
4. **Sin subagentes**, por la ventana de 8k.
5. **Traza:** solo metadatos en producción; argumentos y `razon` únicamente en los evals sintéticos.
