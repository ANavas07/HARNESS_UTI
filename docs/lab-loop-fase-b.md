# Loop ReAct, fase B: la razón antes de actuar — experimento A/B

5 de noviembre de 2026. Fase B de las [directrices del ciclo del agente](loop-agente.md).

**Decisión: la razón NO se activa.** El código queda en el producto detrás de `VLLM_RAZON=1`, apagado por defecto, para volver a medirlo si cambia el modelo.

## 1. Qué se probó

- En modo JSON, el modelo agrega `"razon"`: en hasta 25 palabras, qué pide la persona y por qué elige esa acción.
- Mientras pide herramientas, el `texto` queda vacío.
- La razón vuelve al contexto en la vuelta siguiente, como en ReAct, y nunca se guarda: no va a la memoria ni a las trazas (A56).
- Se recorta a ~40 tokens y pasa por el control de datos personales.

## 2. Resultado (Qwen3-8B-AWQ, 60 evals × 1 corrida, mismo código y misma base)

| | Sin razón | Con razón |
|---|---|---|
| Tasa | **93,3 %** (56/60) | 81,7 % (49/60) |
| Críticos 10/10 | **30** de 34 | 26 de 34 |
| Tokens por tarea | 4742 | 4802 (+1,3 %) |
| Pasos por tarea | 1,87 | 1,85 |
| Segundos por tarea | 9 | 8 |

- **Con razón gana:** M02 y X07.
- **Con razón pierde:** F08, M04, M06, M08, Q05, Q09, V01, V02 y X08.

La razón llegó en 109 de 110 pasos, con unos 100 caracteres de media.

**Criterios (§9 de las directrices):**

| Criterio | Resultado |
|---|---|
| Tasa no baja | ✗ |
| Críticos no empeoran | ✗ |
| Tokens ≤ +10 % | ✓ (+1,3 %) |

**No se queda.**

Evidencia en [reports/evals/runtime/loop-fase-b/](../reports/evals/runtime/loop-fase-b/): las dos corridas con sus trayectorias y la [comparación](../reports/evals/runtime/loop-fase-b/comparacion.txt).

## 3. Por qué empeora

Las trayectorias muestran que, con la razón, el modelo **decide antes de observar**. Razona sin anclarse en ningún dato y cierra la tarea sin consultar:

| Eval | Razón del modelo | Qué hizo |
|---|---|---|
| F08 | «la fecha está en el futuro y no se puede consultar directamente» | Inventó una regla y no llamó a la herramienta |
| V02 | «no tiene acceso a datos personales como cédulas» (correcta) | Respondió con el texto genérico de «fuera de alcance», sin explicar |
| M08 | «el asistente no puede crear citas» (correcta) | Ofreció «¿cancelar o reprogramar?» en vez de explicarlo |

Es la falla que el paper de ReAct describe cuando el razonamiento no se ancla en observaciones: el razonamiento alucina y la acción lo sigue. Con un modelo de 8B y una salida de 256 tokens, pedirle que razone primero lo empuja a cerrar antes de consultar. En el modelo actual, las guardas deterministas del código rinden más que el razonamiento explícito.

## 4. Dónde se rompió

| Qué falló | Cómo se detectó | Corrección |
|---|---|---|
| En la primera corrida, la razón llegó **vacía** en las 60 tareas | La trayectoria mostró `razon: null` en todos los pasos | Una llamada real mostró que el Qwen copia la plantilla JSON del principio de la instrucción y omite lo agregado al final. La razón pasó a la plantilla misma. Esa corrida se invalidó y se guarda aparte (`con-razon-omitida`) |
| La hipótesis inicial (la clave escrita «razón» con tilde) era falsa | El JSON crudo de una llamada real | Se acepta igual la grafía con tilde. La causa real se registra arriba |

## 5. Lo que sí se queda de la fase B

- La infraestructura para medir: la bandera `VLLM_RAZON`, la trayectoria con la razón, el comparador `scripts/comparar_corridas.py` y sus criterios.
- Un dato nuevo: **sin la razón y con todas las guardas, la línea base preliminar subió a 56/60 (93,3 %)**, frente a 54/60 ayer.

**Para retomar:** si cambia el modelo (por ejemplo, uno más grande) o la ruta de salida, repetir esta comparación con N = 10 fuera de horario.
