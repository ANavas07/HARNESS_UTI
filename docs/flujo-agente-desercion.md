# Flujo del agente de deserción

Resumen de cómo razona el agente de deserción, desde los datos hasta el caso y la cita, y cómo lo rodea el harness. Es una vista general: no recoge parámetros, umbrales ni configuraciones exactas. Esos detalles están en la documentación técnica del producto y en el [SPEC](SPEC.md).

---

## 1. La idea en una frase

El agente revisa a todos los estudiantes en momentos fijos del semestre, estima qué tan parecida es la situación de cada uno a la de quienes abandonaron, elige a quién conviene acompañar según lo que el equipo puede atender, agrupa esos casos por tipo y sugiere una acción. **No decide nada**: ordena y propone. Las personas de Seguimiento y Bienestar deciden.

```
Datos del periodo ─► Preparar ─► Estimar riesgo ─► Elegir a quién alertar ─► Agrupar por tipo de caso
                                                                                     │
           Cita con Bienestar ◄─ Derivación ◄─ Revisión humana ◄─ Caso + sugerencia ◄─┘
```

---

## 2. El razonamiento paso a paso

### 2.1 Tomar la foto (el corte)

Todo empieza cuando Seguimiento inicia un **corte**. Hay dos momentos:

- **Al inicio del semestre:** solo se sabe la historia previa del estudiante. Sirve para actuar pronto, pero la señal es más débil.
- **Al cierre del semestre:** ya hay notas, asistencia y la ficha del semestre. Es la foto más completa.

El agente trabaja con lo que de verdad se sabía en ese momento. Nunca usa información del futuro.

### 2.2 Preparar los datos

Antes de mirar a nadie, el agente limpia y ordena:

- corrige valores fuera de rango y duplicados;
- construye señales a partir de la historia del estudiante dentro de su carrera (cómo le fue antes, si viene mejorando o empeorando, cuánto lleva, si tuvo pausas);
- completa los vacíos de forma prudente, con lo aprendido en el entrenamiento;
- pasa todo por un **guardia** que solo deja entrar las variables permitidas para ese corte. Rechaza datos personales, variables que delatan el resultado y las que se excluyeron por equidad.

El mismo código prepara los datos al entrenar y al operar, así que el agente ve en producción exactamente lo mismo que vio al aprender.

### 2.3 Estimar el riesgo

Un modelo supervisado, entrenado con la historia de la universidad, da a cada estudiante una **probabilidad de deserción** y la explica: qué señales pesaron más en su caso (por ejemplo, el promedio del semestre o la asistencia).

La probabilidad está calibrada: un valor alto significa que, entre estudiantes con ese mismo valor, una proporción parecida terminó desertando. No es una sentencia sobre la persona.

### 2.4 Elegir a quién alertar

Aquí el agente combina dos criterios:

- **Un piso de riesgo:** no alerta a alguien con riesgo bajo solo porque queda espacio.
- **Un cupo:** no manda más casos de los que Seguimiento puede atender.

Con eso reparte las alertas en niveles (crítico, alto y medio). Además reserva espacio para **primer nivel**, el grupo más vulnerable: si quedó poco representado, sube a los de mayor riesgo de ese grupo, sin inventar casos.

### 2.5 Agrupar: qué tipo de caso es

Este es el paso de la ciencia de datos que **agrupa**. Ojo: no cambia el riesgo ni decide quién entra. Solo responde **qué tipo de caso es** cada estudiante ya seleccionado, para orientar la ayuda.

Cómo razona:

1. **Aprende de la historia.** Toma a los estudiantes que en periodos anteriores quedaron en el grupo de riesgo y los agrupa con un algoritmo no supervisado (K-means). Para agrupar mira el rendimiento, la asistencia, el avance en la malla, la antigüedad y la continuidad. **Nunca** usa variables protegidas como el sexo o la ubicación.
2. **Nombra los grupos por lo que son, no por un número.** Los números de grupo cambian cada vez que se reentrena, así que cada grupo se nombra según cómo se ve su centro:
   - **Desvinculación en curso:** el grupo con menor asistencia. El estudiante se está alejando y conviene un contacto urgente.
   - **Avanzado con bajo rendimiento:** entre los otros dos, el de mayor avance en la malla. Lleva varios semestres, pero viene atrasado o con notas bajas.
   - **Inicio con bajo rendimiento:** el restante. Está en los primeros niveles, asiste pero reprueba.
3. **Verifica que el nombre tenga sentido.** Si el grupo de "desvinculación" en realidad asiste bastante, o si "inicio" y "avanzado" casi no se distinguen por nivel, el nombre no es confiable y se marca como tal.
4. **Aplica lo aprendido al corte actual.** Cada estudiante alertado recibe el perfil del grupo más cercano.
5. **Si algo falla, no bloquea.** Si no hay suficiente historia o el agrupamiento falla, las alertas salen igual, con el perfil vacío.

### 2.6 Abrir el caso y sugerir una acción

Con el nivel, la explicación y el perfil, el agente:

- abre un **caso** por persona, o suma la alerta al caso que ya tenía abierto;
- compara con el corte anterior: si el riesgo se mantiene o empeora **aunque hubo intervención**, el caso se **escala**; si nadie intervino, se marca **sin atender**; si el estudiante no se matriculó, el caso lo indica;
- **sugiere una intervención** a partir de reglas por nivel y perfil y de la biblioteca de estrategias que Bienestar aprobó. Si usa un modelo de lenguaje, este nunca ve identificadores.

### 2.7 Lo que hacen las personas

- **Seguimiento** revisa la bandeja por prioridad y decide si **deriva** el caso a Bienestar o lo **descarta** con un motivo.
- **Bienestar** contacta al estudiante y registra la intervención.
- En el siguiente corte, el agente vuelve a calcular y anota si el riesgo bajó, se mantuvo o subió.

### 2.8 De la derivación a la cita (el calendario)

Cuando un caso se **deriva**, el calendario entra en juego: busca un profesional de Bienestar con espacio, respeta la prioridad del caso y reserva una cita según reglas, sin pedir aprobación cita por cita. La cita nunca lleva nombres ni datos de contacto, solo el número de caso.

El asistente de agenda ayuda a consultar derivaciones y la agenda, y a **proponer** reprogramaciones o cancelaciones. **No escribe por su cuenta:** toda propuesta se confirma con un botón y la API vuelve a validar permisos y disponibilidad antes de ejecutar.

---

## 3. El harness alrededor del agente

El harness es lo que rodea al modelo para que sea confiable, medible y mejorable. Vive en este repositorio (HARNESS_UTI). El producto solo lleva lo que tiene que correr dentro de él.

### 3.1 Antes de que el modelo opere (entrenamiento)

- **Validación que imita la realidad:** se entrena con el pasado y se prueba con el futuro, dejando un margen para que el resultado no se filtre por la etiqueta.
- **Prueba de fuga:** se entrena con resultados barajados. Si aun así acierta, algo está filtrando el futuro.
- **Equidad:** se compara cuánto detecta el modelo en distintos grupos (modalidad, sede, sexo). Si la brecha es grande, no se aprueba sin una excepción registrada.
- **Deriva:** se vigila si la población cambió respecto al entrenamiento, para saber cuándo reentrenar.
- **Campeón y retador:** un modelo nuevo reemplaza al actual solo si gana con claridad, no empeora la calibración y puede explicar sus alertas.
- **Ciclo de vida:** todo modelo nuevo entra como candidato, corre **en sombra** junto al activo sin generar alertas y solo se promueve con un motivo y un responsable.

### 3.2 Mientras opera (el ciclo del asistente)

Cada pregunta abre una tarea con un presupuesto. En cada vuelta el harness:

1. arma el contexto con prioridades y verifica que quepa en la ventana del modelo; si no cabe, lo compacta;
2. reserva presupuesto antes de llamar y lo liquida con el consumo real;
3. deja que el modelo pida herramientas solo si su rol lo permite, y valida esquema, argumentos y datos personales;
4. ejecuta solo lecturas o propuestas, nunca escrituras;
5. registra una traza de cada llamada (sin datos personales);
6. guarda siempre la última llamada para responder.

Si el modelo no responde, el flujo sigue: el chat cae a un modo básico y la agenda no se detiene.

### 3.3 Cómo se evalúa y mejora

- **Evals de desarrollo:** tareas para el agente que construye la agenda, calificadas con pruebas ocultas.
- **Evals de runtime:** conversaciones del asistente de agenda en varias categorías, corridas contra el modelo real con una base temporal y un reloj fijo.
- **Guardas en el CI del producto:** fallan antes del merge si se rompe una regla del harness.
- **Loop de mejora:** cada fallo se observa, se diagnostica por pieza (contexto, entorno, herramientas o pruebas), se corrige con un cambio pequeño y se mide. La corrección solo se queda si la medición mejora.

---

## 4. Lo que el agente nunca hace

- No decide por las personas: sugiere y ordena.
- No usa sexo ni estado civil para calcular el riesgo, ni variables protegidas para agrupar.
- No muestra identidades fuera de los roles que las necesitan; los eventos internos viajan sin datos personales.
- No contacta a estudiantes ni escribe en la agenda por su cuenta.
- No presenta la probabilidad como una certeza.
