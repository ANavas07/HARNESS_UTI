# Rutas por costo — presupuesto de tokens y tiempos de Qwen

Versión 0.4 — 23 de octubre de 2026. Sustituye el enfoque económico de v0.3 por el cálculo solicitado: tokens de entrada/salida, límite de contexto, ruta y tiempo. No calcula electricidad ni precios en USD.

## 1. Modelo y capacidad efectiva comprobada

- Modelo servido: `Qwen/Qwen3-8B-AWQ`.
- Runtime declarado por `GET /v1/models`: vLLM.
- URL base: `http://172.16.8.69:8000/v1`.
- **Contexto efectivo reportado por el servidor: 8 192 tokens.**
- Hardware informado por el usuario: 4 tarjetas RTX 4000 y 128 GB de RAM. No se verificó variante, VRAM, reparto entre GPU ni paralelismo efectivo.
- Perfil medido: temperatura 0.3, thinking desactivado, una solicitud a la vez.

La [ficha del modelo](https://huggingface.co/Qwen/Qwen3-8B-AWQ) declara 32 768 tokens nativos y extensión mediante YaRN. Esa capacidad teórica no es la habilitada aquí. La definición de [max_model_len en vLLM](https://docs.vllm.ai/en/latest/api/vllm/config/model/) comprende entrada y salida. Para el MVP manda el valor descubierto de **8 192**; no se habilitó ni modificó ninguna extensión del servidor.

Cuatro GPU no multiplican el contexto por cuatro ni prueban cuatro veces la velocidad. No se infiere capacidad operativa de los 128 GB de RAM. La conexión fue autorizada mediante el mecanismo de permisos de red y respondió correctamente; las notas previas de conexión bloqueada quedan superadas por esta medición.

## 2. Qué significa costo en este documento

Distinguir:

1. **Ocupación por llamada:** entrada completa más salida reservada. Debe caber en la ventana del servidor.
2. **Consumo acumulado por tarea:** suma de entrada/salida de todas las llamadas, reintentos y compactaciones hechas con un LLM. Puede superar 8 192 porque no se envía todo en una sola llamada.
3. **Tiempo por ruta:** latencia de inferencia y tiempo de herramientas/verificación.
4. **Calidad:** completar dentro del presupuesto no implica que una respuesta sea correcta.

Los resultados de herramientas y el historial reenviado cuentan de nuevo en la entrada. La caché no aumenta la ventana ni permite omitir esos tokens del cálculo de contexto.

## 3. Medición realizada contra el modelo

Se ejecutaron **9 solicitudes de generación**, tres por perfil, con datos sintéticos de seguimiento estudiantil y sin herramientas ejecutables. Antes de cada generación se contó el prompt mediante `POST /tokenize`, usando mensajes, plantilla y `enable_thinking=false`; se contrastó con `usage.prompt_tokens` de la respuesta. Coincidieron en las nueve muestras.

| Perfil | Entrada real por solicitud | Salida real por solicitud | Total por solicitud | Tiempo observado (s) | TTFT observado (s) | Generación aproximada (tokens/s) |
|---|---:|---:|---:|---:|---:|---:|
| Corto, 3 muestras | 966 | 128 | 1 094 | 4.443–4.491 | 1.054–1.080 | 37.239–37.503 |
| Medio, 3 muestras | 2 958 | 256 | 3 214 | 9.207–9.209 | 1.061–1.089 | 31.299–31.414 |
| Largo, 3 muestras | 4 964 | 512 | 5 476 | 18.027–18.066 | 1.417–1.466 | 30.722–30.856 |

Consumo total reportado: **26 664 tokens de entrada + 2 688 de salida = 29 352 tokens**, repartidos entre nueve solicitudes. Ninguna llamada superó la ventana de 8 192.

Las nueve muestras terminaron con `finish_reason=length`: se solicitó contenido extenso y se limitó deliberadamente la generación. Sirven para medir tokens y tiempos, **no son respuestas finales aceptadas ni un benchmark de calidad**. En producción, una respuesta truncada no se marca como éxito.

TTFT es el tiempo hasta el primer contenido generado observado por el cliente; incluye red, cola y prefill, sin aislar sus componentes. La tasa de generación es aproximada porque los chunks pueden agrupar tokens. No se midió una tasa pura de procesamiento de entrada ni se controlaron caché, tráfico ajeno o concurrencia. Las llamadas preparatorias a tokenización no se incluyen en los tiempos de inferencia de la tabla.

Evidencia reproducible: [mediciones completas](../reports/llm/qwen-medicion.json) y [cálculo de rutas](../reports/llm/qwen-rutas.json). Los textos guardados son sintéticos.

## 4. Cálculo para que una llamada no exceda el modelo

Definiciones:

```text
C = min(contexto reportado por servidor, techo de política del proyecto)
  = min(8 192, 32 768) = 8 192

M = ceil(10 % × C) = 820 tokens de margen operativo
I = tokens de entrada completa, contados con el tokenizador y plantilla reales
O = máximo de tokens de salida solicitado en esa llamada

Condición obligatoria: I + O + M ≤ 8 192
Salida disponible: O_disponible = max(0, 8 192 - I - 820)
max_tokens = min(tope de salida de ruta, presupuesto de salida restante, O_disponible)
```

El margen de 820 es una política conservadora del harness, no una reserva impuesta por Qwen. Además, el techo global de entrada será `floor(0.70 × 8192) = 5734`; si una ruta define uno menor, se usa el menor. La ventana sobrante se mantiene libre y no es una obligación de consumirla.

Ejemplo que cabe: entrada 5 500 + salida máxima 1 024 + margen 820 = **7 344**, quedan **848 tokens**. Ejemplo que se rechaza antes de generar: entrada 7 000 + salida 1 024 + margen 820 = **8 844 > 8 192**.

No se debe confiar únicamente en que el servidor recorte la petición: reducir datos, paginar, compactar o dividir la tarea antes de enviarla. Si no cabe el contenido esencial, devolver un estado explícito sin ejecutar una escritura.

## 5. De dónde salen los tokens de entrada

```text
I = tokenizar(plantilla de chat aplicada a:
    instrucciones + políticas + esquemas de tools + historial/resumen
    + solicitud/caso activo + resultados relevantes de herramientas)
```

Ejemplo de distribución máxima orientativa para O1, no conteo medido de un prompt de producción:

| Bloque | Asignación de tokens |
|---|---:|
| Sistema y reglas necesarias | 600 |
| Esquemas de herramientas habilitadas | 500 |
| Historial reciente y resumen | 600 |
| Caso activo y solicitud | 500 |
| Resultados acotados de herramientas | 600 |
| Plantilla/separadores y holgura de distribución | 200 |
| Entrada objetivo total | 3 000 |

El valor autoritativo es la tokenización de la solicitud completa; sumar estimaciones de bloques no reemplaza esa comprobación. No usar equivalencias fijas de caracteres o palabras. En producción, incluir los esquemas de tools en el conteo; el script admite contarlos y esta medición de rendimiento se hizo con mensajes sin tools.

Si al añadir un resultado se supera el tope de entrada de la ruta, recortar resultados no esenciales o reconstruir contexto y contar de nuevo. Preservar identificadores, reglas, versiones y estado de la operación. No mandar toda la base de estudiantes ni todo el lote al LLM.

## 6. Rutas del producto y límites por llamada

Todas las rutas con LLM usan el mismo Qwen3-8B-AWQ institucional. La reserva automática no obliga a llamar al modelo para cada estudiante.

| Ruta | Cuándo | Entrada máxima por llamada | Salida máxima por llamada | Llamadas máximas por tarea | Entrada + salida + margen |
|---|---|---:|---:|---:|---:|
| O0 | Importación, prioridad, disponibilidad y reserva desde datos estructurados | 0 | 0 | 0 | 0 |
| O1 | Interpretar una solicitud o producir texto acotado | 3 000 | 256 | 3 | 4 076 |
| O2 | Excepción justificada o una reparación que requiere más contexto | 5 000 | 768 | 4 | 6 588 |

O0 es código determinista con validaciones y transacciones. O1 → O2 requiere causa registrada; si no resuelve, revisión humana. No escalar por falta de disponibilidad ni para saltar permisos.

Thinking permanece desactivado en este perfil. Activarlo requiere evaluación separada y contar también su salida en el presupuesto; no se asigna tiempo gratuito a razonamiento.

## 7. Rutas de desarrollo y límites por llamada

La imagen de referencia trata tareas de programación. Se mantienen separadas de las rutas operativas.

| Ruta | Trabajo | Entrada máxima por llamada | Salida máxima por llamada | Llamadas máximas por tarea | Entrada + salida + margen |
|---|---|---:|---:|---:|---:|
| R0 | Cambio pequeño y localizado | 3 000 | 512 | 4 | 4 332 |
| R1 | Endpoint/regla con pruebas | 5 000 | 1 024 | 8 | 6 844 |
| R2 | Cambio transversal o diagnóstico complejo | 5 500 | 1 024 | 16 | 7 344 |

R2 no implica multiagente. Cualquier delegación requiere autorización expresa y consumo agregado. El protocolo A/B debe congelar la misma ruta, modelo, configuración y presupuesto para ambas condiciones.

Estas salidas pueden ser insuficientes para un archivo grande; dividir la tarea en cambios acotados dentro del mismo presupuesto, sin aceptar código truncado. Revisión e integración también consumen llamadas si usan el modelo.

## 8. Presupuesto acumulado por ruta

```text
Entrada_tarea = suma de usage.prompt_tokens de todas las llamadas
Salida_tarea  = suma de usage.completion_tokens de todas las llamadas
Consumo_tarea = Entrada_tarea + Salida_tarea

Techo de entrada = máximo de llamadas × tope de entrada por llamada
Techo de salida  = máximo de llamadas × tope de salida por llamada
```

| Ruta | Entrada acumulada máxima | Salida acumulada máxima | Total acumulado máximo |
|---|---:|---:|---:|
| O0 | 0 | 0 | 0 |
| O1 | 9 000 | 768 | 9 768 |
| O2 | 20 000 | 3 072 | 23 072 |
| R0 | 12 000 | 2 048 | 14 048 |
| R1 | 40 000 | 8 192 | 48 192 |
| R2 | 88 000 | 16 384 | 104 384 |

R2 puede consumir hasta 104 384 tokens sumados, pero ninguna de sus llamadas ocupa más de 7 344 incluyendo margen. No significa que el modelo tenga una ventana de 104 384.

Al escalar O1 → O2, los contadores no se reinician: el máximo de cuatro llamadas, 20 000 de entrada y 3 072 de salida incluye lo ya gastado en O1. Igual para R0 → R1 → R2. Los topes de tabla son acumulados de planificación; según las llamadas ya usadas puede quedar menos presupuesto útil del indicado.

## 9. Tiempos calculados desde las solicitudes reales

Se usa como calibración inicial la tasa de generación más baja observada y el TTFT más alto:

```text
v = 30.722 tokens/s aproximadamente
L = 1.466418 s de TTFT observado máximo

T_proyectado = N × (L + O/v) + T_otros
Plazo_propuesto = redondear_hacia_arriba_a_15_s(T_proyectado × 1.25)
```

N es el número máximo de llamadas y O su salida máxima. T_otros es una provisión explícita para herramientas, conteo y verificación: 5/10/10/30/60 s para O1/O2/R0/R1/R2. No se midieron esos componentes. La adición O/v tras TTFT aproxima conservadoramente la generación completa.

| Ruta | Cálculo de tiempo (s) | Proyección (s) | Plazo inicial con 25 % de margen |
|---|---|---:|---:|
| O1 | 3 × (1.466418 + 256/30.722) + 5 | 34.398 | 45 s |
| O2 | 4 × (1.466418 + 768/30.722) + 10 | 115.859 | 150 s |
| R0 | 4 × (1.466418 + 512/30.722) + 10 | 82.528 | 105 s |
| R1 | 8 × (1.466418 + 1024/30.722) + 30 | 308.381 | 390 s |
| R2 | 16 × (1.466418 + 1024/30.722) + 60 | 616.761 | 780 s |

**Estos plazos son proyecciones para configurar un piloto, no SLA medidos ni garantías.** Las muestras solo generaron hasta 512 tokens por llamada y usaron hasta 4 964 de entrada. Las salidas 768/1 024 y la entrada 5 500 extrapolan ese comportamiento; falta medir esos extremos, contexto con tools y concurrencia. Más carga, thinking, caché distinta o tests lentos pueden cambiar los tiempos. No extrapolar esta prueba a cuatro solicitudes simultáneas.

Para O0 no hay tiempo de inferencia: medir aparte API, base y calendario. Un plazo de agente agotado no revierte una reserva ya confirmada. Los plazos aquí sustituyen los anteriores presupuestos de tiempo hipotéticos del documento.

## 10. Ejemplo de varias llamadas y lote

O1 con entradas reales hipotéticas 1 000, 1 800 y 2 600 y salidas de 256 cada una:

```text
Llamada 1: 1000 + 256 + 820 = 2076 ≤ 8192
Llamada 2: 1800 + 256 + 820 = 2876 ≤ 8192
Llamada 3: 2600 + 256 + 820 = 3676 ≤ 8192
Consumo acumulado: entrada 5400 + salida 768 = 6168 tokens
```

La entrada de llamadas posteriores ya incluye el historial que se reenvía; no se descuenta por haber sido enviado antes.

Lote hipotético de 1 000 casos, clasificados por ruta final:

| Ruta final | Casos | Máximo de entrada acumulada | Máximo de salida acumulada |
|---|---:|---:|---:|
| O0 | 700 | 0 | 0 |
| O1 | 250 | 2 250 000 | 192 000 |
| O2 | 50 | 1 000 000 | 153 600 |
| Total | 1 000 | 3 250 000 | 345 600 |

Máximo acumulado del lote: **3 595 600 tokens**. No se envía como un prompt: se distribuye por caso y llamada. La proporción 70/25/5 es ilustrativa. Las tareas O2 incluyen su O1 previa y no se cuentan dos veces. En ejecución estrictamente secuencial, la suma de las proyecciones para las 300 tareas con LLM es aproximadamente 4 h; esto no mide el throughput real de un lote ni incluye las 700 operaciones O0.

## 11. Aplicación de límites en el harness

Antes de cada llamada:

1. Descubrir/cachear el modelo servido y contexto efectivo; no aceptar un nombre de modelo distinto silenciosamente.
2. Construir solo el contexto relevante y contar mediante tokenizador/plantilla equivalentes, incluyendo tools.
3. Comprobar tope de entrada de ruta, presupuesto acumulado de entrada y llamadas restantes.
4. Reservar salida con `max_tokens` y verificar `I + O + M ≤ C`.
5. Comprobar plazo restante de la tarea; no lanzar una nueva llamada que no tenga presupuesto razonable.
6. Acumular el `usage` real, incluidos reintentos con uso conocido. Un fallo de red con consumo desconocido no se contabiliza como cero: conservar la reserva estimada.
7. Si falta espacio en la ventana por llamada, paginar/compactar, reconstruir la entrada, contar de nuevo y continuar cuando quepa. La compactación no termina la ejecución ni reinicia contadores. Solo si se agota el presupuesto acumulado real de la tarea (tokens, llamadas o plazo), detener nuevas acciones y reportar `budget_exceeded`. Si el contenido esencial sigue sin caber, dividir la tarea o pedir el dato necesario, evitando ciclos de compactación sin reducción.

Al recibir `finish_reason=length`, contenido vacío o tool call inválida, no declarar éxito. La reparación consume el mismo presupuesto. Las confirmaciones al usuario se basan en la operación persistida; el texto generado no prueba que se reservó una cita.

## 12. Conexión y reproducción en este proyecto

La conexión usa Python 3.10+ y biblioteca estándar, sin instalar SDK ni dependencias. Variables y URL en [.env.example](../.env.example); el script lee el entorno del proceso, no carga automáticamente un archivo .env.

```powershell
python scripts/medir_qwen.py --discover-only --output reports/llm/qwen-discovery.json
python scripts/medir_qwen.py --repeats 3 --output reports/llm/qwen-medicion.json
python scripts/calcular_rutas.py --input reports/llm/qwen-medicion.json --output reports/llm/qwen-rutas.json
python -m unittest discover -s tests
```

La medición hace hasta nueve generaciones secuenciales y 2 688 tokens de salida máxima, además de llamadas de tokenización sin generación. No ejecuta herramientas ni crea citas. Requiere acceso de red autorizado al servidor. No reejecutar continuamente: recalibrar por cambios de contexto, modelo, runtime, carga o perfil.

El cliente implementa la comprobación por llamada; el calculador verifica matemáticamente las rutas y deriva los plazos. El ejecutor completo de tareas, sus contadores persistentes y las herramientas de calendario todavía son requisitos de implementación, no capacidades ya construidas.

## 13. Evidencia, límites y relación con el spec

- [Cliente y medidor](../scripts/medir_qwen.py).
- [Calculador reproducible](../scripts/calcular_rutas.py).
- [Reporte de las nueve solicitudes](../reports/llm/qwen-medicion.json).
- [Presupuestos y tiempos calculados](../reports/llm/qwen-rutas.json).
- [Protocolo A/B](analisis-ab-harness.md): todavía no ejecutado como experimento de desarrollo.
- [Spec](SPEC.md): adopta el contexto efectivo y estos presupuestos.

La medición verifica conexión, identidad reportada, tokenización, streaming y consumo de texto. No demuestra tool calling habilitado, calidad de decisión, concurrencia, VRAM efectiva ni rendimiento del flujo completo del calendario.
