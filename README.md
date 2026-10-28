# Harness de calendario

Proyecto de definición y validación de un harness de calendario para seguimiento estudiantil. Desde el SPEC v0.8, el calendario reserva una cita con un profesional de Bienestar cuando Seguimiento deriva un caso en el producto de deserción (Agente de Deserción v2), y sigue su stack Python.

**Punto de entrada visual:** [abrir el diagrama interactivo](web/index.html). Puede abrirse directamente en un navegador. Incluye recorridos, compactación con continuidad y consumo simulado de tokens basado en las mediciones guardadas.

## Estructura

```text
Harnes Calendario/
├── README.md                         Guía del proyecto
├── progress.md                       Bitácora de avances, evidencia y pendientes
├── .env.example                      Variables de conexión de ejemplo
├── .gitignore                        Exclusiones locales
├── .gitattributes                    Normalización de finales de línea
├── docs/                             Documentación funcional y técnica
│   ├── SPEC.md                       Especificación del MVP
│   ├── rutas-por-costo.md             Tokens, contexto, rutas y tiempos
│   ├── analisis-ab-harness.md         Protocolo de evaluación A/B
│   ├── auditoria-logica.md            Riesgos de diseño y su resolución
│   ├── propuesta-etapa-10-agenda.md   Etapa 10 para el SPEC_REFINADO del producto, por fases
│   └── calidad-evals.md               Tests, evals del agente, métricas y tiempos
├── evals/                            Definiciones de evals (tarea, entorno, grader)
│   ├── desarrollo/                   Agente que construye el repositorio
│   └── runtime/                      Agente de calendario con Qwen
├── config/
│   └── politica.demo.json            Perfil sintético; no habilita producción
├── web/
│   └── index.html                    Diagrama y simulación interactivos
├── scripts/                          Utilidades Python sin dependencias externas
│   ├── medir_qwen.py                 Conexión, tokenización y medición de Qwen
│   ├── calcular_rutas.py              Presupuestos derivados de las mediciones
│   └── ejecutar_eval.py               Runner de evals: copia aislada, N corridas, grader
├── tests/
│   ├── test_presupuestos.py           Pruebas de límites, sin acceso a red
│   └── test_ejecutar_eval.py          Pruebas del runner con agentes simulados
└── reports/                          Evidencia de ejecución y revisión
    ├── llm/
    │   ├── qwen-medicion.json         Nueve solicitudes reales de prueba
    │   └── qwen-rutas.json            Presupuestos y proyecciones calculados
    ├── evals/                        Corridas y controles de evals, por fecha
    ├── qa/
    │   └── flujo-harness-qa.json      Revisión del HTML y sus recorridos
    └── capturas/                     Vistas del diagrama y su evolución
```

## Documentos principales

- [Progreso del proyecto](progress.md): proceso realizado, decisiones, verificaciones, estado real y próximos pasos.
- [Spec](docs/SPEC.md): alcance, calendario interno, reglas, herramientas, fases y aceptación.
- [Auditoría de lógica](docs/auditoria-logica.md): revisión de riesgos, cuellos de botella y dependencias de activación.
- [Política de demostración](config/politica.demo.json): valores explícitos para desarrollar con datos sintéticos; pendientes de aprobación para un piloto real.
- [Calidad, tiempos y evals](docs/calidad-evals.md): tests de código, evals del agente con grader automático, señales del harness y métricas del equipo.
- [Rutas y presupuestos](docs/rutas-por-costo.md): contexto efectivo de 8.192 tokens y límites por llamada/tarea.
- [Evaluación A/B](docs/analisis-ab-harness.md): comparación controlada de desarrollo con y sin harness.
- [Mediciones de Qwen](reports/llm/qwen-medicion.json): evidencia original.
- [Validación del diagrama](reports/qa/flujo-harness-qa.json): recorridos y contadores comprobados.

## Comandos

Ejecutar desde la raíz del proyecto con Python 3.10 o superior. Solo el runner de evals necesita una dependencia externa, PyYAML, fijada en `requirements-evals.txt`; sin ella, sus pruebas se omiten.

```powershell
# Verificar presupuestos sin acceder al servidor
python -m unittest discover -s tests -v

# Recalcular rutas desde la evidencia existente, sin realizar inferencias
python scripts/calcular_rutas.py

# Consultar modelo y contexto: requiere acceso a la red institucional
python scripts/medir_qwen.py --discover-only --output reports/llm/qwen-discovery.json

# Controles de un eval y corridas de un agente (requiere: pip install -r requirements-evals.txt)
python scripts/ejecutar_eval.py evals/desarrollo/D02-calculador-check.yaml --control positivo
python scripts/ejecutar_eval.py evals/desarrollo/D02-calculador-check.yaml --agente "<comando del agente>"

# Repetir la medición: genera hasta 9 solicitudes y reemplaza el reporte indicado
python scripts/medir_qwen.py --repeats 3 --output reports/llm/qwen-medicion.json
```

Las rutas predeterminadas de los scripts se resuelven desde la ubicación del proyecto. Los argumentos `--input` y `--output` permiten seleccionar archivos explícitos.

La conexión se configura mediante variables del entorno del proceso, descritas en [.env.example](.env.example). El script no carga `.env` automáticamente. No guardar credenciales en los documentos, capturas o reportes.

Para previsualizar por HTTP, servir la raíz del proyecto —así también funcionan los enlaces a documentación y evidencia—:

```powershell
python -m http.server 8765 --bind 127.0.0.1
```

Abrir [la vista local del diagrama](http://127.0.0.1:8765/web/index.html). Detener el servidor con `Ctrl+C` al terminar.

## Estado y criterio de organización

El calendario operativo todavía debe implementarse. Se decidió implementarlo como **módulo dentro del producto de deserción** (SPEC §6, opción A): su código irá en el repositorio del producto, y este repositorio conserva la especificación, el sistema de calidad, los evals y las mediciones. Falta que el equipo del producto acepte la etapa, propuesta en [docs/propuesta-etapa-10-agenda.md](docs/propuesta-etapa-10-agenda.md) con seis fases, tareas, criterios, pruebas y gates (cambios P3, P5 y P7, SPEC §32). Ya existen la documentación, el HTML explicativo, la conexión/medición de Qwen, el calculador y las pruebas de presupuestos. El panel del HTML muestra una simulación, no nuevas solicitudes al modelo ni citas persistidas. El experimento A/B de desarrollo sigue pendiente.

Mantener especificaciones en `docs/`, perfiles de configuración en `config/`, definiciones de evals en `evals/`, la presentación en `web/`, utilidades en `scripts/`, pruebas en `tests/` y resultados en la subcarpeta correspondiente de `reports/`. Las capturas anteriores se conservan como evidencia de la evolución del diseño.
