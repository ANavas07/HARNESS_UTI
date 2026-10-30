# IT-M9.D: pantalla Agenda verificada en el navegador contra la API real

**Fecha:** 30 de octubre de 2026.
**Producto:** rama `etapa-10d-pantalla` (fase 10.D), interfaz compilada con `npm run build`.
**Entorno:** `backend/scripts/demo_agenda.py`, con PostgreSQL temporal, migraciones hasta la 0012, datos sintéticos de la fábrica y rondas cada 20 s. No se usaron el MVP local ni el dataset real.
**Navegador:** el panel integrado de Claude Code, con el ingreso de desarrollo (X-Usuario y X-Rol).

## CA1: derivar como Seguimiento → cita visible para Bienestar → resultado → caso en intervención

| Paso | Quién | Acción en la interfaz | Resultado observado |
|---|---|---|---|
| 1 | `seg.uno` (Seguimiento) | Bandeja → caso «Nuevo» C-47C4 → Derivar | Estado «Derivado a Bienestar» |
| 2 | `c.ruiz` (coordinación) | Derivaciones: C-47C4 en «Sin profesional», en el orden de la bandeja → Asignar a b.lopez | Mensaje «C-47C4 quedó asignado a b.lopez» |
| 3 | Sistema | Ronda periódica | Solicitud `agendada`, cita hoy 10:30–10:45 con b.lopez |
| 4 | `b.lopez` (Bienestar) | Agenda: chip «10:30 · Cita C-47C4» → ficha → Completada → resultado «Aceptó el apoyo» → Guardar | Chip «✓ Completada · Cita C-47C4» |
| 5 | Comprobación por la API | `GET /api/casos/{id}` como Seguimiento | `estado = en_intervencion`; `cita.estado = finalizada` con resultado `acepto_apoyo / bienestar` |

En la misma sesión también se comprobó:
- marcar como hecha una tarea propia: `✓ Completada · Llamar para confirmar`;
- completar una cita vencida con su resultado;
- la vista «Vencidas (n)» y la zona horaria en el encabezado.

## CA2: ningún dato personal en la URL, el almacenamiento ni la consola

- **URL:** solo rutas de la aplicación y el identificador técnico del caso (`/casos/{uuid}`), nunca la cédula.
- **Almacenamiento:** solo `permanencia.sesion` = `{"usuario","rol"}`.
- **Consola:** sin mensajes de error ni registros.
- **Calendario:** las respuestas usan códigos cortos de caso (C-XXXX) y nunca `persona_ref`. La prueba `test_api_mi_agenda_y_calendario` lo verifica.

## Dónde se rompió

| Qué pasó | Diagnóstico | Corrección |
|---|---|---|
| El primer clic en la casilla de una tarea abrió la ficha | La casilla mide 0 hasta pasar el cursor (diseño aprobado); el clic sin cursor encima cae sobre el texto | No es un error. Con el cursor encima, la casilla aparece y marcar funciona. En pantallas táctiles siempre se ve |
| En Derivaciones, dos solicitudes «Agendada» no mostraban su cita | La semilla dejaba en `pendiente` solicitudes con cita; además, una cita finalizada no se lista como próxima | Semilla corregida (`agendada`). La columna muestra solo citas reservadas, que es lo esperado |

## E10-T26: configuración para Administración (misma fecha, `adm.uno`)

| Paso | Resultado observado |
|---|---|
| Ventana de búsqueda en 99 → Crear borrador | 422 y «Revisa «Ventana de búsqueda»: debe ser como máximo 30»; el campo queda marcado y conserva el 99 |
| Ventana en 12 → Crear borrador | «Borrador v2 … listo» |
| Motivo «Ventana acordada con Bienestar» → Aprobar | La v2 queda vigente y la v1, retirada |

**Dónde se rompió:** la primera vez, el mensaje salía en inglés (Pydantic) y repetía la ruta del campo. Se tradujo en el contrato de la política, con su prueba.

## Lo que no cubre

- La vista en modo claro se revisó en la maqueta aprobada. Esta sesión corrió en el modo oscuro del producto.
