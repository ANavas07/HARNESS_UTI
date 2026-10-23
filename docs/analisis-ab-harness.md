# Análisis y protocolo A/B: sin harness frente a con harness

Versión 0.2 — 23 de octubre de 2026. Estado: diseño del experimento; no ejecutado. Modelo identificado por configuración del usuario.

## 1. Qué plantea la primera imagen

La imagen propone ejecutar la misma tarea de desarrollo dos veces. En A, el repositorio carece de orientación operativa; en B, el agente cuenta con instrucciones, estructura y fixtures. La tarea ilustrativa es agregar un endpoint de total de orden con su test y pasar el linter. Es un ejemplo de laboratorio, no un requisito de pedidos para nuestro calendario.

| Problema ilustrado en A | Ayuda ofrecida en B | Qué debemos medir |
|---|---|---|
| Probar varios comandos para encontrar los tests | AGENTS.md con comando exacto | Intentos fallidos y tiempo hasta la primera verificación válida |
| Crear el endpoint en el módulo equivocado | Estructura documentada | Ubicación y dependencias del cambio |
| Encontrar un script peligroso de reset | Script excluido del entorno de prueba | Intentos de operaciones fuera del alcance de la tarea |
| Tests que fallan por falta de datos | Fixtures deterministas | Fallos atribuibles al entorno y reproducibilidad |

La diapositiva ilustra una hipótesis, no demuestra que nuestros tests pasarán al primer intento ni que un modelo usará menos tokens. Eso se debe medir aquí.

## 2. Dos sentidos de harness en este proyecto

- **Harness de desarrollo:** instrucciones del repositorio, comandos, estructura, fixtures, pruebas y reportes que ayudan a un agente a construir el software. Este es el objeto directo de la imagen.
- **Harness de ejecución:** entorno del agente de calendario: contexto, herramientas, persistencia, políticas y observabilidad. Es el producto definido en SPEC.md.

Ambos se necesitan, pero sus evaluaciones se separan. Que un agente programe bien no prueba que el sistema reserve correctamente; las pruebas de aceptación del spec cubren ese comportamiento.

## 3. Por qué hacerlo

Identificar si documentar y preparar el repositorio reduce exploración improductiva, correcciones humanas, fallos de entorno y coste por tarea aceptada. También permite descubrir qué le falta al harness antes de atribuir un fallo a Qwen o cambiar de modelo.

La hipótesis principal es que B mejora la proporción de tareas aceptadas dentro del mismo presupuesto. Tiempo y coste solo cuentan como mejora si se conserva la corrección.

## 4. Tarea adaptada al calendario

Enunciado idéntico en A y B:

> Implementa `GET /advisors/:id/availability` en el módulo de calendario. Debe devolver franjas de 15 minutos dentro del rango solicitado, descontando bloqueos, reservas activas y buffers configurados, respetando la zona horaria y los permisos. Añade pruebas relevantes, ejecuta la suite rápida y el linter y reporta resultados y archivos modificados.

Se ejecutará cuando exista un esqueleto funcional del repositorio con stack y scripts fijados. No se presenta este endpoint como ya implementado.

Fixtures sintéticas propuestas: asesor con horario 09:00–10:00 America/Guayaquil, reserva 09:15–09:30 y bloqueo 09:45–10:00 en un día laborable fijo. Con buffer cero y rango completo, el resultado esperado contiene 09:00–09:15 y 09:30–09:45. Añadir casos separados de cancelación, buffer distinto de cero, rango inválido y acceso denegado.

## 5. Diseño controlado

1. Crear dos copias aisladas desde el mismo commit base y base de datos sintética limpia por corrida. No usar la base de estudiantes real.
2. Mantener el mismo código funcional, dependencias, tests de evaluación y datos iniciales en ambas condiciones.
3. A recibe el repositorio sin el paquete de orientación. B añade AGENTS.md corto, documentación de módulos, comandos verificados y guía para cargar las fixtures disponibles en ambos entornos.
4. Mantener idénticos modelo/tag/digest, cuantización, contexto, thinking, temperatura, herramientas disponibles del agente de código, hardware, presupuesto y enunciado. Usar sesiones nuevas, sin transferir hallazgos entre A y B.
5. Ejecutar inicialmente cinco pares A/B con orden alternado o aleatorio. Registrar seeds cuando el runtime lo permita y condiciones de caché; cinco pares solo ofrecen una señal preliminar.
6. Evaluar ambos resultados con la misma suite independiente, fuera del control del agente. Un test añadido por el propio agente no basta como prueba de corrección.
7. Conservar diff, comandos, salidas, costes y reporte por corrida. No integrar automáticamente los cambios experimentales en la rama de trabajo.

No exponer un script destructivo a una base real para reproducir la diapositiva. Si se evalúa el efecto de excluir scripts peligrosos o añadir fixtures que no estaban en A, hacerlo como experimento de paquete completo y declararlo: esas diferencias impiden atribuir toda la mejora únicamente a AGENTS.md. La comparación principal conserva las mismas capacidades funcionales y datos.

## 6. Criterios y métricas

Una corrida es aceptada si el endpoint cumple el contrato, está en el módulo correcto, respeta permisos, pasa la evaluación independiente y el linter, y no introduce cambios ajenos a la tarea. Un corte de presupuesto o resultado parcial no es éxito.

Registrar por corrida:

- Modelo real y digest; condición A/B; commit base y configuración del harness.
- Resultado: `accepted`, `failed`, `budget_exceeded` o `environment_error`.
- Tiempo total y hasta primer test válido; intentos de comandos inexistentes; intervención humana.
- Tokens acumulados de entrada/salida, llamadas al modelo, herramientas, reparaciones y reinicios de contexto.
- Coste API real o estimado; coste local marginal y asignado por separado.
- Pruebas de evaluación y lint, ubicación del módulo y diff final.

| Par | Modelo/digest | A: resultado / s / USD | B: resultado / s / USD | Observaciones |
|---|---|---|---|---|
| 1–5 | Pendiente de fijar | No ejecutado | No ejecutado | Completar con evidencia |

Comparar tasa de aceptación, mediana de tiempo y coste total dividido por tareas aceptadas; incluir el gasto de intentos fallidos. Si no hay tareas aceptadas, reportar coste por éxito como no definido, no como cero. Separar errores de entorno sin ocultarlos ni descartarlos selectivamente.

## 7. Comparar modelos sin confundir efectos

Primero A/B con el mismo modelo. Después repetir el par para otro modelo bajo el mismo protocolo. La matriz es **modelo × condición**, no A con Qwen y B con un modelo diferente.

Modelo identificado mediante la configuración del usuario: **`Qwen/Qwen3-8B-AWQ`**, servido con vLLM en la red institucional. La denominación previa «Qwen 3.8 de 8B» queda corregida: se trata de Qwen3 de 8B cuantizado AWQ. La conexión y el contexto efectivo de 8192 fueron verificados mediante solicitudes reales. Antes del experimento registrar además revisión de pesos, versión de vLLM, plantilla, parámetros y hardware. No usar una variante de Ollama como reemplazo silencioso. Los candidatos y fórmulas se definen en [rutas-por-costo.md](rutas-por-costo.md).

Perfil inicial del ejemplo: temperatura 0.3 y `enable_thinking=false`. Congelarlo para A y B; evaluar thinking activado como un bloque experimental separado y contabilizar su consumo. Confirmar soporte de herramientas del servidor con una prueba simulada antes de ejecutar tareas del agente de código.

## 8. Entregables y condición de cierre

Entregar configuración A/B versionada, manifiesto de datos sintéticos, tareas y evaluación independiente, reportes de todas las corridas y análisis de resultados con limitaciones. No declarar una mejora porcentual sin datos. Decidir después qué instrucciones, comandos y fixtures se incorporan al harness de desarrollo.

## 9. Evaluación del agente de calendario

Por separado, ejecutar los casos de SPEC.md con y sin ayudas de contexto opcionales para medir uso válido de herramientas, respuestas y coste. Las validaciones transaccionales, permisos y prevención de duplicados permanecen habilitados en ambas condiciones: no se eliminan controles del calendario para crear una variante «sin harness».

## 10. Próximos requisitos para poder ejecutar

El workspace incorpora documentación, un cliente de medición y un calculador de presupuestos, pero todavía no existe la aplicación de calendario ni el esqueleto de la tarea A/B. La conexión al modelo y nueve inferencias sintéticas de tokens/tiempo fueron verificadas; no constituyen el experimento A/B de desarrollo. Se necesita implementar el esqueleto, fixtures y evaluación independiente para ejecutarlo.

La identidad servida es `Qwen/Qwen3-8B-AWQ` y el contexto efectivo verificado es 8192. La limitación inicial de conexión quedó resuelta mediante permisos de red. Registrar revisión de pesos, versión de vLLM y configuración del servidor antes de comparar A/B; los límites y mediciones están en rutas-por-costo.md.
