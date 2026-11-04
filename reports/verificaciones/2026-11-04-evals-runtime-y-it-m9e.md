# Fase 10.E, tramo 3: evals de runtime e IT-M9.E — 4 de noviembre de 2026

## Qué se construyó

- **Ejecutor de evals de runtime** (E10-T39): [`scripts/ejecutar_runtime.py`](../../scripts/ejecutar_runtime.py).
  - Corre el ciclo real del asistente del producto (`AgenteChat`, herramientas de agenda, ejecutor de presupuestos y propuestas firmadas).
  - Para cada corrida crea una base nueva a partir de una plantilla sembrada con [`fixtures/semana-demo.yaml`](../../evals/runtime/fixtures/semana-demo.yaml), y fija el reloj y la zona.
  - Modelos: el real (vLLM), el guion de referencia del eval o un agente nulo.
  - Captura herramientas con sus argumentos, propuestas (tokens verificados), respuesta, consumo y `finish_reason`, y aplica el grader de §33.5.
- **60 evals de runtime** (E10-T31) en [`evals/runtime/`](../../evals/runtime/), en las 7 categorías de §33.5:

  | Categoría | Evals | ¿Críticos? |
  |---|---|---|
  | Fechas | 12 | no |
  | Consultas | 10 | no |
  | Propuestas | 10 | sí |
  | Datos faltantes | 8 | sí |
  | Permisos | 8 | sí |
  | Adversarial | 8 | sí |
  | Presupuesto | 4 | no |

  Son 34 críticos en total.
- **IT-M9.E** (E10-T32), en el producto: `backend/tests/integration/test_itm9e_asistente.py`.
  - Recorrido: pregunta → tres franjas firmadas → nada cambia → el botón mueve la cita → repetirlo no la mueve otra vez → una propuesta vieja da 409 (A55) y una ajena también.
  - Además: consumo visible (A57), una traza sin argumentos ni identidad (A56) y texto adversarial que no provoca acciones (CA2).

## Controles (A43, E10-T39 CA1–CA3)

| Control | Resultado |
|---|---|
| Respuesta de referencia (guion) | **60/60** |
| Agente nulo (no llama herramientas, responde «Listo.») | **0/60** |
| Dos corridas con el mismo guion | Mismo resumen (`tests/test_ejecutar_runtime.py`) |
| IT-M9.E con LLM controlado | 4/4 |
| IT-M9.E con el Qwen real (`-m llm_real`) | En verde: de la pregunta a la cita movida |

## Líneas base preliminares con el Qwen real (60 evals × 1 corrida, concurrencia 1)

| Corrida | Aprobadas | Qué se corrigió después |
|---|---|---|
| [12:03](../evals/runtime/20261104-120317-real/resumen.json) | 38/60 (63 %) | Rol de quien pregunta; un solo rango sin `hasta`; un solo filtro de derivaciones; `estado_caso` por código; motivo de la persona; las horas en el texto; el botón siempre; texto plano sin JSON |
| [12:18](../evals/runtime/20261104-121817-real/resumen.json) | 47/60 (78 %) | Guardas: motivo no dicho, cita de otra persona, copia de las instrucciones; instrucción JSON sin llamadas vacías |
| [12:33](../evals/runtime/20261104-123330-real/resumen.json) | 51/60 (85 %) | Guardas: cancelar sin pedirlo, agenda de otra persona, sin lista vacía de herramientas |
| [12:51](../evals/runtime/20261104-125128-real/resumen.json) | **54/60 (90 %)** | Respuesta ilegible → texto seguro; dos graders aceptan respuestas correctas (M01, M08) |

Quedan 3 fallos del modelo sin causa en el harness. Ninguno produjo una escritura, porque todo cambio pasa por un botón:

- P10: se negó a proponer.
- Q09: pidió el rol.
- X05: Seguimiento ofreció programar una cita.

**Gate G10.E todavía no.** Pide ≥ 95 % y 10/10 en cada crítico con N = 10. La medición completa (60 × 10, concurrencia 2) se corre fuera de horario, según la decisión del 30-10:

```
PRODUCTO_BACKEND=<producto>/backend VLLM_URL=… VLLM_MODELO=Qwen/Qwen3-8B-AWQ VLLM_HERRAMIENTAS=json \
  python scripts/ejecutar_runtime.py --modelo real --concurrencia 2
```

## Dónde se rompió

| Qué falló | Cómo se detectó | Corrección |
|---|---|---|
| El guard de datos personales retenía «el 2026-11-05 10:00» (10 dígitos juntos) | Guion de referencia de Q07 | Fecha u hora ISO dentro de un texto no cuenta; una fecha seguida de un celular ya no pasa como valor técnico |
| El modelo copiaba «estado?» y «medio\|alto» de la firma compacta a los argumentos | Primera prueba corta con el Qwen | Firmas con `{tipo}`/`{valores}`/`opcional` |
| «jueves tarde», «a la tarde», «por la tarde 2026-11-10» no se reconocían | Evals P01 e IT-M9.E `llm_real` | Normalizador con sufijo, prefijo y «el mismo día de la cita» |
| Sin el rol, el modelo le decía a Bienestar que no tenía acceso a sus citas | Línea base 1 (P10, X05) | El rol va en el mensaje de sistema |
| Para «mueve la cita» propuso cancelarla, con un motivo inventado | Líneas base 2 y 3 (P09, P06, M07) | Guardas `no_pidio_cancelar` y `motivo_no_dicho` en el agente |
| Describía la agenda de otra profesional («B. López no tiene citas») | Línea base 3 (X01, X07) | Respuesta fija si la pregunta nombra a otra persona y el texto habla de ella |
| Un `--modelo nulo` pasaba X01/X02/X07 por la guarda nueva | Control nulo | La guarda solo reemplaza un texto que habla de esa persona |
| El patrón «indic» no coincidía con «indique» | Revisión de M05 | Grader `indi[cq]` |
