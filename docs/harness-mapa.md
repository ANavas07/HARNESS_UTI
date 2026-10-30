# Mapa del harness: qué vive dónde

**Regla (decisión del usuario del 29 de octubre de 2026):** toda la lógica del harness vive en este repositorio, [HARNESS_UTI](https://github.com/ANavas07/HARNESS_UTI). El repositorio del producto ([GRUPO2_SEGUIMIENTO](https://github.com/ANavas07/GRUPO2_SEGUIMIENTO), rama `MVP`) lleva solo:

- el código de la agenda (opción A, SPEC §6);
- lo mínimo del harness que **tiene que correr dentro del producto** para funcionar.

Cada pieza que vive en el producto queda listada aquí, con su razón.

## En HARNESS_UTI

| Pieza | Dónde | Qué hace |
|---|---|---|
| Especificación | [SPEC](SPEC.md), [contrato técnico](contrato-tecnico-agenda.md), [propuesta de la Etapa 10](propuesta-etapa-10-agenda.md) | Qué debe pasar y cómo se implementa en el producto |
| Sistema de calidad | [calidad-evals.md](calidad-evals.md) | Tests de código, evals del agente, señales del harness y métricas del equipo |
| Runner de evals | `scripts/ejecutar_eval.py` + `tests/test_ejecutar_eval.py` | Controles, agentes por comando o externos (`--preparar` / `--calificar`), pruebas ocultas (`copiar`), pass@N y reportes |
| Evals de desarrollo | `evals/desarrollo/` | Tareas para el agente que construye la agenda (D01, D02, …) |
| Lab de evals | `evals/lab/`, [evals-lab.md](evals-lab.md) | Una tarea por pieza del harness (contexto, entorno, herramientas), con graders y soluciones de referencia |
| Evals de runtime | `evals/runtime/` | Conversaciones del asistente de agenda (fase 10.E) |
| Loop de mejora | [loop-mejora.md](loop-mejora.md) | Fallos del agente → diagnóstico por pieza → corrección → métrica |
| Presupuestos y rutas | [rutas-por-costo.md](rutas-por-costo.md), `scripts/calcular_rutas.py`, `config/` | Límites de tokens por llamada y tarea, medidos contra Qwen |
| Evidencia | `reports/` | Reportes de evals, mediciones y capturas; no se sobrescriben |
| Presentación | `web/index.html` | Explicación interactiva del harness y resultados de los evals |
| Bitácora | [progress.md](../progress.md) | Qué se hizo, con qué evidencia y qué sigue |

## En el producto, porque solo funciona ahí

| Pieza | Archivo del producto | Por qué no puede vivir aquí | Origen |
|---|---|---|---|
| Contexto del agente | `AGENTS.md` | El agente lo lee al trabajar en el repositorio del producto | Loop iteración 1 (F1, F4, F7) y lab, lección 1 |
| Guardas del harness | `backend/tests/architecture/test_harness_desarrollo.py` | Tienen que fallar en el CI del producto, antes del merge | Lab L3-r5 y loop F4 |
| Fábrica de datos de agenda | `backend/tests/fabricas_agenda.py` (incluye `borrar_confirmado` para las pruebas con varias conexiones) | Las pruebas del producto la importan | Loop F3 y fase 10.B |
| Fixture `con_api` | `backend/tests/integration/conftest.py` | La usan las pruebas de servicio del producto | Loop F2 |
| Runner de mutaciones | `backend/scripts/correr_mutaciones.py` (objetivos `agenda` y `reserva`) | Muta el código del producto y corre sus pruebas | Gate de cada fase |
| Entorno sintético de la agenda | `backend/scripts/demo_agenda.py` | Levanta la API y la interfaz del producto con datos inventados para IT-M9.D y demostraciones; usa el código y la fábrica del producto | Fase 10.D |
| Trazas de consumo | `backend/shared/trazas.py` | Las escribe el asistente en ejecución (fase 10.E) | SPEC §33.4 |

Una pieza del harness nueva va **aquí** salvo que tenga que ejecutarse dentro del producto. En ese caso se agrega a esta tabla en el mismo cambio.

## Cómo se conectan

1. El SPEC y el contrato de este repositorio definen cada fase. El producto la implementa en una rama y un PR hacia `MVP`.
2. Los evals de este repositorio apuntan a un commit del producto (`fuente` en el YAML). El runner prepara una copia limpia, el agente trabaja y el grader califica sin tocar el repositorio del producto.
3. Los fallos se analizan en el loop de mejora. Si la corrección es de contexto, entorno o pruebas del producto, va al producto y se registra arriba. Si es del eval, el grader o el método, queda aquí.
