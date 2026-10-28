# Sistema de calidad y tiempos: tests, evals y métricas del equipo

Versión 0.2 — 28 de octubre de 2026. Estado: sistema de medición definido, runner de evals de desarrollo implementado y eval D02 ejecutable con controles registrados. La aplicación de calendario, los evals del agente en runtime y la primera línea base con un agente real siguen pendientes.

Este documento define **cómo se decide si algo funciona y cuánto tarda**. Complementa el [SPEC §31](SPEC.md#31-sistema-de-calidad-y-tiempos), el [protocolo A/B](analisis-ab-harness.md) y los [presupuestos por ruta](rutas-por-costo.md). Los umbrales numéricos son propuestas iniciales para calibrar con las primeras corridas, no resultados observados.

## 1. Tres capas, tres sistemas bajo prueba

| Capa | Sistema bajo prueba | Pregunta que responde | Quién la ejecuta |
|---|---|---|---|
| **Tests de código** | El código del calendario | ¿Las reglas, transacciones e invariantes se cumplen? | Desarrollador y CI, en cada cambio |
| **Evals del agente** | El agente más su harness | ¿El agente resuelve tareas reales de forma repetible y dentro del presupuesto? | Runner de evals, al cambiar prompt, modelo, herramientas o harness |
| **Métricas del equipo** | El proceso de desarrollo | ¿El harness ayuda o se volvió ruido? ¿Dónde se pierde tiempo? | Agregación semanal de las dos capas anteriores |

Un test de código no prueba que el agente use bien las herramientas, y un eval aprobado no prueba que una reserva sea transaccionalmente correcta. Ninguna capa sustituye a otra.

Hay dos agentes distintos (ver [análisis A/B §2](analisis-ab-harness.md#2-dos-sentidos-de-harness-en-este-proyecto)):

- **Agente de desarrollo:** el asistente de código que construye este repositorio. Sus evals miden el *harness de desarrollo*: AGENTS.md, comandos, fixtures y estructura.
- **Agente de calendario:** Qwen dentro del runtime. Sus evals miden el *harness de ejecución*: contexto, intenciones, presupuestos y validaciones.

## 2. Capa 1 — Tests de código

### Suites y presupuestos de tiempo

| Suite | Contenido | Cuándo | Tiempo objetivo |
|---|---|---|---|
| `rapida` | Unitarias de reglas, prioridad/desempate, política, presupuestos, idempotencia en memoria | Antes de cada commit; la usan los agentes | **< 60 s** (A21) |
| `integracion` | PostgreSQL real efímero: restricciones de exclusión, transacciones, outbox, leases, importación con simulador de origen | Cada push y PR | < 10 min |
| `concurrencia` | Carreras A05, A27, A28, deadlocks, reintentos | Cada PR que toque agenda, jobs o migraciones; nocturna | < 20 min |
| `carga` | Perfil de referencia §29: 1000 solicitudes, 50 profesionales, 10 clientes | Antes de ampliar el piloto y al cambiar índices | Reporte, no bloquea el commit |

La suite actual (`python -m unittest discover -s tests`) contiene 4 pruebas de presupuestos y pertenece a `rapida`.

### Reglas

- Cada criterio vigente del SPEC (A01–A58, sin los retirados) se asigna a una suite y a un archivo de prueba. Un criterio sin prueba asignada figura como **no cubierto**, no como aprobado.
- Un test que falla de forma intermitente (*flaky*) se marca, se aísla del bloqueo de merge y se corrige en el mismo ciclo. No se reintenta en silencio hasta que pase.
- Si la suite rápida supera 60 s en el entorno de referencia, se mueven pruebas a `integracion` antes de agregar más.
- Las pruebas usan datos sintéticos y relojes inyectados; nunca la API real ni estudiantes reales.

### Qué se registra por ejecución

Duración total y por suite, los 10 tests más lentos, fallos, flakes detectados y criterios vigentes cubiertos. Formato en §6.

## 3. Capa 2 — Evals del agente

> Un eval es un test de integración donde el sistema bajo prueba es el agente más su harness.

### Anatomía

| Parte | Definición | Requisito en este proyecto |
|---|---|---|
| **Tarea** | Instrucción realista, como la que se daría a un colega. Ni trivial ni imposible. | Redactada en español, con alcance cerrado y criterio de terminado verificable. |
| **Entorno aislado** | Copia fresca por corrida, estado conocido, sin efectos entre corridas. | Copia limpia del commit fijado, sin la carpeta `evals/`, sin red salvo que la tarea la requiera, base sintética nueva. |
| **Grader** | Verificación automática y objetiva. Sin opinión humana. | Pasos compuestos: tests + comandos + HTTP/estado + lint + archivos que no deben cambiar. |

**Regla de oro:** si el grader no puede decidir *pasa / no pasa* sin un humano, el eval todavía no está listo. La calidad de redacción, por ejemplo, solo entra como comprobaciones objetivas (contiene fecha y hora correctas, no menciona el riesgo, no supera N caracteres).

**Graders compuestos:** combinar tests, comandos, HTTP o estado de base y lint captura los cambios que «funcionan pero rompen otra cosa».

**Aislamiento del grader:** el runner copia el repositorio *sin* `evals/`; los tests ocultos y fixtures del grader se aplican desde fuera de la copia después de que el agente termina. Un test escrito por el propio agente no basta como evidencia.

**Controles del eval:** antes de usarlo, cada eval debe demostrar que **falla** sobre el commit base (control negativo) y que **pasa** con una solución de referencia (control positivo). Sin ambos, no se sabe si es trivial o imposible.

### Formato

Cada eval es un archivo YAML en `evals/`. Campos mínimos:

```yaml
id: D02-calculador-check
capa: desarrollo            # desarrollo | runtime
estado: ejecutable          # borrador | ejecutable | bloqueado_por_<dependencia>
tarea: |
  Instrucción para el agente.
repo: harness-calendario@<commit>
entorno: { tipo: copia_limpia, excluir: [evals/], red: deshabilitada }
presupuesto: { ruta: R1, tiempo_max_s: 390 }
corridas: 10                # N para pass@N
grader:
  - run: python -m unittest discover -s tests
    exit: 0
umbral: { tasa_minima: 0.8 }
```

Los evals de runtime añaden `estado_inicial` (fixture de base), `actor`, `entrada` y `esperado` (intención y argumentos). La carpeta [evals/](../evals/) contiene los ejemplos iniciales.

### Repetición: pass@N

Un agente no determinista no se evalúa con una sola corrida, igual que no se aprueba con un solo test. Cada eval se corre **N veces (5–10)** con el mismo commit, modelo y configuración.

- **Tasa de éxito** = corridas que pasan el grader / N. En este proyecto «pass@N» significa esta fracción.
- **Evals críticos** (autorización, identidad, duplicados, escrituras indebidas) exigen **N/N**: una sola falla bloquea.
- Reportar siempre las N corridas con su salida. No descartar corridas por «mala suerte»; los errores de entorno se reportan aparte y se corrigen.

### Evals de desarrollo

Miden el harness de desarrollo. El presupuesto usa las rutas R0/R1/R2 de [rutas-por-costo.md](rutas-por-costo.md); agotarlo cuenta como fallo (`budget_exceeded`), no como éxito parcial.

| ID | Tarea | Estado |
|---|---|---|
| [D02](../evals/desarrollo/D02-calculador-check.yaml) | Añadir modo `--check` al calculador de rutas, sin escribir reportes | **Ejecutable hoy** sobre el repositorio actual |
| [D01](../evals/desarrollo/D01-disponibilidad.yaml) | Disponibilidad de agenda en el producto, con su test (la tarea del A/B) | Bloqueado: requiere la etapa de agenda en el producto y que el runner acepte su repositorio |

El experimento A/B es un uso particular de estos evals: misma tarea y mismo grader, con y sin el paquete de orientación.

### Evals del agente de calendario (runtime)

Miden a Qwen con su harness. Desarrollan la evaluación de dominio de [SPEC §29](SPEC.md#habilitación-de-o1o2): al menos 60 casos sintéticos en español y ≥ 95 % de resolución correcta, con 100 % en los críticos. Son la evidencia para cerrar la puerta **G6**.

| Categoría | Ejemplos | Crítico |
|---|---|---|
| Interpretación de agenda | Fechas relativas («el jueves por la tarde»), zona horaria, rangos | No |
| Gestión de cita | Reprogramar, cancelar, consultar estado | Sí, si escribe |
| Datos faltantes y homónimos | Pide el dato en vez de inventarlo; no elige entre dos estudiantes | Sí |
| Permisos y ámbito | Un profesional de Bienestar pide la agenda de otro sin alcance de coordinación | Sí |
| Texto adversarial | Mensaje que ordena cambiar el riesgo o ignorar reglas | Sí |
| Redacción acotada | `preparar_comunicacion` sin riesgo, con fecha y hora correctas | No |

El grader compara la salida estructurada (herramientas, argumentos, propuesta), comprueba que la base no cambió (el agente solo propone), que se respetó el presupuesto de la ruta y que ninguna llamada terminó en `length` con un tool call truncado. El ejecutor, los pasos de grader y el conjunto de 60 evals están definidos en [SPEC §33.5](SPEC.md#335-evals-de-runtime). Ejemplos: [C01](../evals/runtime/C01-reprogramar.yaml) y [C02](../evals/runtime/C02-adversarial-riesgo.yaml).

## 4. Capa 3 — Señales del harness y métricas del equipo

Las señales del laboratorio A/B se convierten en instrumentación permanente: se registran en **cada** corrida de eval y se agregan por semana.

| Señal | Qué mide | Cuándo preocuparse (umbral inicial) |
|---|---|---|
| Tasa de éxito (pass@N) | Fracción de corridas que pasan el grader | Baja ≥ 2 corridas de 10 tras un cambio del harness con el mismo modelo: el cambio lo rompió |
| Intentos hasta verde | Ejecuciones de tests/grader del agente hasta el primer resultado válido | Sube respecto de la línea base: el contexto se volvió ruido |
| Comandos fallidos | Errores de setup, build o test por corrida | > 0 sostenido en 3 corridas: AGENTS.md o el setup mienten |
| Preguntas al humano | Bloqueos que requieren intervención | Pregunta por información que ya estaba escrita: falta un enlace o sobra ruido |
| Tokens por tarea | Entrada + salida acumuladas por corrida | Crece > 20 % sin que la tarea crezca: contexto inflado |
| Tiempo por tarea | Reloj total y hasta el primer test válido | Supera el plazo de su ruta o sube > 25 % respecto de la línea base |

En un eval no hay humano disponible: si el agente pregunta, el runner responde con un texto fijo («no hay información adicional») y cuenta la pregunta.

### Métricas del equipo

| Métrica | Fuente | Uso |
|---|---|---|
| Duración de cada suite y tests más lentos | Capa 1 | Mantener la suite rápida bajo 60 s |
| Tasa de fallos de CI y flakes abiertos | Capa 1 | Distinguir código roto de pruebas inestables |
| Tiempo de ciclo (primer commit → merge) | Git | Detectar bloqueos de revisión o integración |
| Tiempo de recuperación tras rojo en `main` | CI | Cuánto tarda el equipo en volver a verde |
| Cobertura de criterios vigentes A01–A58 | Matriz de pruebas | Qué está probado y qué sigue en papel |
| Tasa de éxito y tokens por eval, por semana | Capa 2 | Tendencia del harness y del modelo |
| Correcciones humanas sobre trabajo del agente | Revisión de PR | Qué debe pasar a AGENTS.md o a una herramienta |

Estas métricas evalúan el proceso, no a las personas. No se usan para comparar individuos.

## 5. Sistema de tiempos

Todos los tiempos se registran con el mismo reloj (UTC, monotónico para duraciones) y se correlacionan por `trace_id` o `run_id`.

| Nivel | Puntos medidos | Límite de referencia |
|---|---|---|
| Test de código | Suite total, por archivo, por test | §2 |
| Eval de desarrollo | Total, hasta el primer test válido, por llamada al modelo, por comando, grader | Plazo de la ruta R0/R1/R2 |
| Eval de runtime | Cola, tokenización, TTFT, generación, herramientas, validación, total (SPEC §29) | Plazo de la ruta O1/O2 (45 s / 150 s propuestos) |
| Operación del piloto | p95 de disponibilidad, comando O0 confirmado, edad del outbox | ≤ 1 s, ≤ 2 s (objetivos §29) |

Los plazos de ruta son proyecciones de 9 mediciones, no SLA; se recalibran con las primeras corridas de eval reales.

## 6. Registro de resultados

Cada ejecución escribe un JSON en `reports/evals/<AAAA-MM-DD>/<id>-<run_id>.json` (o `reports/tests/` para la capa 1). Campos mínimos:

```json
{
  "run_id": "D02-20261028-01",
  "eval_id": "D02-calculador-check",
  "capa": "desarrollo",
  "commit_base": "<sha>",
  "harness_version": "<sha o etiqueta de AGENTS.md/prompts>",
  "modelo": { "id": "<id>", "revision": "<digest>", "temperatura": 0.3, "thinking": false },
  "resultado": "accepted",
  "grader": [ { "paso": 1, "ok": true, "duracion_s": 0.4 } ],
  "senales": {
    "intentos_hasta_verde": 2,
    "comandos_fallidos": 0,
    "preguntas_humano": 0,
    "tokens_entrada": 0,
    "tokens_salida": 0,
    "llamadas_modelo": 0
  },
  "tiempos_s": { "total": 0, "hasta_primer_test_valido": 0, "grader": 0 },
  "notas": ""
}
```

`resultado` toma uno de estos valores: `accepted`, `failed`, `budget_exceeded` o `environment_error`, los mismos del protocolo A/B. Los reportes son evidencia histórica: no se sobrescriben para mostrar una validación nueva.

## 7. Runner de evals

[scripts/ejecutar_eval.py](../scripts/ejecutar_eval.py) ejecuta evals de desarrollo. Requiere PyYAML fijado en [requirements-evals.txt](../requirements-evals.txt); el resto del proyecto sigue sin dependencias externas.

```powershell
pip install -r requirements-evals.txt

# Controles del eval: deben salir con código 0
python scripts/ejecutar_eval.py evals/desarrollo/D02-calculador-check.yaml --control negativo
python scripts/ejecutar_eval.py evals/desarrollo/D02-calculador-check.yaml --control positivo

# N corridas de un agente (N del eval, o --corridas)
python scripts/ejecutar_eval.py evals/desarrollo/D02-calculador-check.yaml --agente "<comando del agente>"
```

Por corrida, el runner:

1. Copia el repositorio en una carpeta temporal nueva, sin `evals/`. Por defecto usa el commit `HEAD` (`git archive`); `--origen trabajo` usa los archivos locales y marca el registro como `arbol_sucio`.
2. Toma una huella SHA-256 de los archivos.
3. Ejecuta el agente dentro de la copia con el plazo `presupuesto.tiempo_max_s`. Al vencer, termina el árbol de procesos y la corrida es `budget_exceeded`.
4. Registra los archivos que cambió el agente, antes de que el grader genere los suyos.
5. Ejecuta **todos** los pasos del grader, aunque falle uno, para que el reporte muestre cada fallo.
6. Escribe un JSON por corrida y un resumen en `reports/evals/<AAAA-MM-DD>/`.

**Contrato con el agente.** El comando recibe estas variables de entorno: `EVAL_TAREA` (archivo con la tarea), `EVAL_REPO` (la copia), `EVAL_ID`, `EVAL_RUN_ID` y `EVAL_SENALES`. Si el agente o su envoltorio escriben en `EVAL_SENALES` un JSON con las señales de §4, el runner las incorpora. Las señales que no se informan quedan en `null`, **no en 0**: un dato desconocido no se presenta como medido.

**Pasos de grader soportados:** `run` (con `exit`, `stderr_no_contiene` y `archivo_existe`), `sin_cambios` y `solo_modifica`. Un paso con otra clave (`http`, `sql`, `json_igual`…) produce `environment_error`, no un aprobado. Los marcadores `{evals}`, `{tmp}` y `{repo}` se sustituyen y conviene entrecomillarlos, porque la ruta del proyecto tiene espacios.

**Salida:** código 0 si el resumen cumple (umbral alcanzado o control correcto), 1 si no cumple y 2 si el eval está bloqueado o es de runtime.

**Límites conocidos:**
- No restringe la red: el registro lo indica como `no_restringida_por_el_runner`.
- No mide por sí mismo tokens, intentos ni preguntas: dependen de lo que informe el agente.
- No ejecuta evals de runtime: esos necesitan el ejecutor del agente de calendario.

Las pruebas del runner están en [tests/test_ejecutar_eval.py](../tests/test_ejecutar_eval.py). Usan controles y agentes simulados: aceptado, cambio fuera de alcance, plazo vencido, paso no soportado y eval bloqueado. Dentro de la copia aislada se omiten, porque allí no existe `evals/`.

## 8. Cuándo se ejecuta cada cosa

| Evento | Capa 1 | Capa 2 | Capa 3 |
|---|---|---|---|
| Commit local | `rapida` | — | — |
| PR | `rapida` + `integracion` (+ `concurrencia` si aplica) | Evals afectados, si cambia AGENTS.md, prompt, herramientas o modelo | — |
| Cambio de modelo, plantilla o servidor | — | Todos los evals de runtime, N = 10 | Nueva línea base |
| Semanal | — | Conjunto completo | Reporte de señales y métricas |
| Antes de cada puerta G5/G6/G7 | Suites aplicables | Evals críticos N/N | Reporte firmado por el responsable |

## 9. Estado e implementación pendiente

| Elemento | Estado |
|---|---|
| Este documento y el formato YAML/JSON | Definidos |
| Eval D02, fixtures y solución de referencia | Ejecutables; controles registrados por el runner en `reports/evals/2026-10-28/` sobre el commit `9d020d2` |
| Eval D01 y evals de runtime C01–C02 | Definidos como plantilla; bloqueados por el esqueleto y el runtime |
| Runner de evals de desarrollo | Implementado en Python con 6 pruebas; sin restricción de red |
| Runner de evals de runtime | Pendiente; requiere el ejecutor del agente de calendario |
| Runner sobre el repositorio del producto | Pendiente: hoy copia solo este repositorio; D01 necesita una opción de repositorio de origen (SPEC v0.8, opción A) |
| Instrumentación de señales en el agente de desarrollo | Pendiente; depende de los registros que exponga la herramienta de agente utilizada |
| Separación de suites y CI | Pendiente; hoy solo existe la suite rápida de presupuestos |
| Primera línea base de señales | Pendiente; requiere elegir el agente de desarrollo y ejecutar D02 con N = 10 |

No se declara ninguna tasa de éxito, tiempo ni mejora hasta tener las corridas registradas.
