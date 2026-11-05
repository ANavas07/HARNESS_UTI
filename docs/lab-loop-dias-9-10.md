# Laboratorio del loop, días 9–10: hacer visible lo que el ciclo hace

5 de noviembre de 2026. Fase A de las [directrices del ciclo del agente](loop-agente.md).

## 1. Qué se instrumentó

| Pieza | Dónde | Qué registra |
|---|---|---|
| Evento por iteración (producción) | Producto: `agente.iteracion` en `api/app/chat/agente.py` | Paso, decisión, herramienta, resultado, `error_code`, duración, tokens de entrada y salida, y `corte`. **Solo metadatos (A56):** el filtro de `shared/trazas.py` descarta todo lo demás. La vista «Ver proceso» no lo muestra como paso |
| Trayectoria por corrida (evals) | HARNESS_UTI: `scripts/ejecutar_runtime.py` → `trayectorias/<eval>-<n>.jsonl` | Además: los argumentos, el texto del modelo, el resultado de cada herramienta y la `razon` (cuando exista, en la fase B). Los datos son sintéticos |
| Línea de tiempo | HARNESS_UTI: `scripts/linea_de_tiempo.py [--html]` | Tabla y barras por paso, con los pasos «sin aporte» (repiten una llamada ya hecha) y el paso más caro |

## 2. Las tres tareas (Qwen3-8B-AWQ real, una corrida)

Evidencia: [reports/evals/runtime/loop-dias-9-10/](../reports/evals/runtime/loop-dias-9-10/), con las trayectorias JSONL y la [línea de tiempo de B04](../reports/evals/runtime/loop-dias-9-10/linea-B04.html).

| Tarea | Paso 0 | Paso 1 | Total |
|---|---|---|---|
| **F01** fácil: «¿Qué citas tengo mañana?» | `consultar_agenda{desde: mañana}` · 2353+40 tokens · 2,3 s | Respuesta · 2750+54 · 2,3 s | 2 pasos · 4,6 s · 5197 tokens |
| **B04** media: agenda y derivaciones | `consultar_agenda` + `consultar_derivaciones{}` · 2359+57 · 2,0 s | Respuesta · **3762+155 · 5,9 s** | 2 pasos · 7,8 s · 6333 tokens |
| **P02** difícil: reprogramar por hora | `proponer_reprogramacion{cita: «mañana 10:00», desde: «jueves por la tarde»}` · 2369+81 · 2,8 s | Respuesta con las 3 franjas · 2627+74 · 2,6 s | 2 pasos · 5,5 s · 5151 tokens |

Las tres pasaron su grader. Ninguna tuvo pasos sin aporte: cada una resolvió en el mínimo de 2 pasos (consultar y responder).

## 3. Respuestas del laboratorio

**¿Qué pasó en el paso que gastó más tokens?**
Fue la respuesta de B04: 3762 tokens de entrada y 155 de salida, en 5,9 s.
- El modelo pidió `consultar_derivaciones` **sin filtro**, aunque la persona preguntó por las *pendientes*. Recibió todas las solicitudes del profesional y después las enumeró todas en la respuesta.
- Más datos de entrada producen una respuesta más larga y más lenta: el tiempo de una llamada crece con los tokens de salida.

**¿Hubo iteraciones que no aportaron nada?**
No, en estas tres. La línea de tiempo marca automáticamente la repetición de una llamada ya hecha, que es lo que el circuit breaker de la fase C va a bloquear. En las líneas base de ayer sí las hubo: Q06 repitió 3 veces la misma llamada inválida.

**¿Dónde dudó el modelo?**
- **Pensó en voz alta sin que se le pidiera.** Al pedir herramientas, el campo `texto` llevó una frase como «Buscando tus citas para mañana…» o «Propongo mover la cita… Confirma con un botón». Eso cuesta entre 40 y 80 tokens de salida por paso. En P02 incluso anticipó una propuesta antes de tener el resultado.
- **En B04 dudó sobre el filtro.** Interpretó «derivaciones pendientes» como «todas las derivaciones».

## 4. Lo que esto cambia en las fases siguientes

1. **El costo fijo domina.** Cada llamada empieza con ~2.350 tokens de sistema, rol y firmas de herramientas: entre el 75 y el 90 % de la entrada de cada paso. Antes de agregar más texto al prompt conviene medir el *prefix caching* de vLLM, que reutiliza ese prefijo entre llamadas, y adelgazar el sistema.
2. **El «Pensar» ya ocurre, pero sin forma.** El modelo ya escribe una frase de intención en `texto` al llamar herramientas. La fase B no agrega costo, sino que lo **ordena**:
   - el campo `razon` (≤ 40 tokens) reemplaza ese texto suelto;
   - el texto queda vacío mientras se piden herramientas;
   - la comparación con y sin la `razon` decide si se queda.
3. **Filtros que el modelo omite.** El caso de B04 se ataca en la descripción de la herramienta («si la persona dice *pendientes*, filtra por estado») y con un eval de regresión. No es una guarda.
