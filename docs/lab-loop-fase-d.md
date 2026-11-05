# Loop ReAct, fase D: recuperar — evals de rotura

5 de noviembre de 2026. Fase D de las [directrices del ciclo del agente](loop-agente.md). Producto: PR #14 (rama `loop-fase-d`, sobre el #13).

**Resultado: 20/20 con el Qwen real (4 evals × 5 corridas). Las referencias pasan (4/4) y el agente nulo falla (0/4).**

## 1. Qué se agregó en el producto

- **Una herramienta que se cae no tumba la conversación.** Si lanza una excepción (por ejemplo, con la base caída):
  - el modelo recibe `herramienta_no_responde`, sin el detalle técnico;
  - cuenta como fallo para el circuit breaker;
  - la traza registra `chat.tool` con resultado `fallo`.
- **Escalado del nivel 4.** La persona siempre sabe qué se intentó y qué falló. El texto se arma solo con frases fijas: nunca con argumentos, datos ni el error técnico.

| Situación | Lo que ve la persona |
|---|---|
| Salta el circuit breaker (parada 6) o una herramienta no respondió, sin ningún dato obtenido | Solo el escalado: «No pude completar tu consulta: consulté tu agenda y no respondió. Puedes verlo en la pantalla Agenda o preguntarme de otra forma.» Lo que diga el modelo se descarta, porque sin datos sería inventado |
| Lo mismo, pero algo sí funcionó | La respuesta del modelo y, después, lo que falló, sin repetir lo que funcionó |
| Se agota el presupuesto (parada 5) | El mensaje de hoy y «Antes de detenerme, …» con lo intentado |
| El servidor falla después del reintento (parada 7), con herramientas ya usadas | «El asistente no está disponible en este momento.» y lo intentado. Sin nada intentado, la ruta del chat responde como hoy |
| Un fallo que la persona puede corregir (fecha ambigua, motivo no dicho…) | Sin cambios: el modelo pregunta |

- **Repeticiones bloqueadas:** no cuentan como intentos en el escalado, porque no se ejecutaron.
- **«Ver proceso»:** muestra «La herramienta no respondió», marcada como fallo, y «El servidor del modelo falló; se reintentó una vez».
- **Mutaciones `asistente`:** 83/83.

## 2. Los evals de rotura (HARNESS_UTI)

Están en `evals/runtime-rotura/`, aparte de los 60 del gate G10.E, que fija el SPEC. El runner simula averías con el campo `averia`:
- `herramienta_rota`: la herramienta lanza una excepción en cada llamada, solo en esa corrida;
- `servidor_transitorio: N`: las primeras N llamadas de generación fallan con un timeout. Solo aplica con `--modelo real`, porque el reintento vive en el cliente del producto.

Hay dos graders nuevos:
- `herramientas_intentadas_max`: no cuenta las repeticiones que bloqueó el breaker;
- `reintento_transparente`.

| Eval | Avería | Qué se exige |
|---|---|---|
| R01 agenda caída | `consultar_agenda` siempre falla | ≤ 3 intentos; dice que no pudo; no inventa horas ni citas |
| R02 agenda caída con derivaciones | La agenda falla y las derivaciones responden | Da las derivaciones y dice que la agenda falló; no inventa la agenda |
| R03 tarea imposible | Ninguna: no hay franjas el domingo y la persona no acepta otro día | ≤ 3 intentos; sin propuesta; dice que no se puede; no afirma haberlo hecho |
| R04 timeout transitorio | La primera llamada al servidor falla | Un reintento; responde con las horas correctas, sin escribir y dentro del plazo |

## 3. Resultado con el Qwen (5 corridas por eval)

| Eval | Aprobadas | Intentos (máx.) | Llamadas al modelo | Tokens por tarea | Segundos |
|---|---|---|---|---|---|
| R01 | 5/5 | 1 | 2 | 4906 | 5,9 |
| R02 | 5/5 | 2 | 2 | 5941 | 12,4 |
| R03 | 5/5 | 2 | 2–3 | 5276 | 7,2 |
| R04 | 5/5 | 1 | 2 | 5193 | 6,9 |

Lectura:
- Con la herramienta caída, el Qwen **no insiste**: se detiene al primer `herramienta_no_responde`. El breaker queda como red y no fue necesario.
- En R03, 3 de 5 corridas pidieron primero `proponer_cancelacion`. La guarda `no_pidio_cancelar` lo frenó, y el modelo reprogramó, recibió `sin_disponibilidad` y lo dijo. Con 2 intentos, nunca se acercó al breaker.
- En R04 hubo un timeout simulado por corrida, y el reintento lo absorbió sin que la persona lo note.

Evidencia: [reports/evals/runtime/loop-fase-d/](../reports/evals/runtime/loop-fase-d/), con las trayectorias JSONL.

## 4. Dónde se rompió

| Qué falló | Cómo se detectó | Corrección |
|---|---|---|
| Una herramienta que lanzaba una excepción tumbaba toda la conversación | Al preparar los evals de rotura: leyendo `_herramientas` | La excepción se convierte en `herramienta_no_responde` y cuenta como fallo |
| R02, 0/5 en la primera corrida con el Qwen: con la agenda caída, el modelo respondió solo con las derivaciones y **no dijo que faltaba la agenda** | La trayectoria de R02 | Una herramienta caída siempre se escala, aunque el breaker no salte. Prueba nueva y dos mutaciones |
| El grader «no inventa citas» de R02 marcaba como inventados los códigos `C-0A0…`, que aparecen con razón en la lista de derivaciones | La misma trayectoria | El grader busca afirmaciones sobre la agenda que no se pudo ver («mañana tienes…») |
| Una mutación antigua apuntaba a la línea del presupuesto agotado, que cambió | El runner: «el texto original aparece 0 veces» | Se actualizó su texto original. Otras 13 mutaciones de objetivos anteriores (`agente`, `chat`, `web`, `avisos`, `casos`, `contratos`) ya estaban desfasadas en `MVP`: se registra como pendiente aparte |
| La prueba anterior «la herramienta caída no tumba la conversación» esperaba el texto del modelo | La suite, al agregar el escalado por herramienta caída | Ahora espera el escalado |

## 5. Pendientes

- Medir los 4 de rotura con N = 10 junto con la medición completa 60 × 10, fuera de horario.
- Revisar las 13 mutaciones desfasadas de objetivos anteriores a la Etapa 10.
- En R02, el modelo pidió las derivaciones sin el filtro «pendiente» (la misma falla de B04). El texto lista también las agendadas.
