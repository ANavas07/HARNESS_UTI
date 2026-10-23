# Harness de calendario

Proyecto de definición y validación de un harness de calendario para seguimiento estudiantil, conectado por API al producto de deserción.

**Punto de entrada visual:** [abrir el diagrama interactivo](web/index.html). Puede abrirse directamente en un navegador. Incluye recorridos, compactación con continuidad y consumo simulado de tokens basado en las mediciones guardadas.

## Estructura

```text
Harnes Calendario/
├── README.md                         Guía del proyecto
├── .env.example                      Variables de conexión de ejemplo
├── .gitignore                        Exclusiones locales
├── .gitattributes                    Normalización de finales de línea
├── docs/                             Documentación funcional y técnica
│   ├── SPEC.md                       Especificación del MVP
│   ├── rutas-por-costo.md             Tokens, contexto, rutas y tiempos
│   └── analisis-ab-harness.md         Protocolo de evaluación A/B
├── web/
│   └── index.html                    Diagrama y simulación interactivos
├── scripts/                          Utilidades Python sin dependencias externas
│   ├── medir_qwen.py                 Conexión, tokenización y medición de Qwen
│   └── calcular_rutas.py              Presupuestos derivados de las mediciones
├── tests/
│   └── test_presupuestos.py           Pruebas de límites, sin acceso a red
└── reports/                          Evidencia de ejecución y revisión
    ├── llm/
    │   ├── qwen-medicion.json         Nueve solicitudes reales de prueba
    │   └── qwen-rutas.json            Presupuestos y proyecciones calculados
    ├── qa/
    │   └── flujo-harness-qa.json      Revisión del HTML y sus recorridos
    └── capturas/                     Vistas del diagrama y su evolución
```

## Documentos principales

- [Spec](docs/SPEC.md): alcance, calendario interno, reglas, herramientas, fases y aceptación.
- [Rutas y presupuestos](docs/rutas-por-costo.md): contexto efectivo de 8.192 tokens y límites por llamada/tarea.
- [Evaluación A/B](docs/analisis-ab-harness.md): comparación controlada de desarrollo con y sin harness.
- [Mediciones de Qwen](reports/llm/qwen-medicion.json): evidencia original.
- [Validación del diagrama](reports/qa/flujo-harness-qa.json): recorridos y contadores comprobados.

## Comandos

Ejecutar desde la raíz del proyecto con Python 3.10 o superior.

```powershell
# Verificar presupuestos sin acceder al servidor
python -m unittest discover -s tests -v

# Recalcular rutas desde la evidencia existente, sin realizar inferencias
python scripts/calcular_rutas.py

# Consultar modelo y contexto: requiere acceso a la red institucional
python scripts/medir_qwen.py --discover-only --output reports/llm/qwen-discovery.json

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

El calendario operativo todavía debe implementarse. Ya existen la documentación, el HTML explicativo, la conexión/medición de Qwen, el calculador y las pruebas de presupuestos. El panel del HTML muestra una simulación, no nuevas solicitudes al modelo ni citas persistidas. El experimento A/B de desarrollo sigue pendiente.

Mantener especificaciones en `docs/`, la presentación en `web/`, utilidades en `scripts/`, pruebas en `tests/` y resultados en la subcarpeta correspondiente de `reports/`. Las capturas anteriores se conservan como evidencia de la evolución del diseño.
