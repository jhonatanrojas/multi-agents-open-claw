# Arquitectura Hibrida Objetivo Para OpenClaw

## Objetivo

Mover el sistema desde un esquema donde OpenClaw funciona casi solo como proveedor de LLM hacia una arquitectura hibrida donde OpenClaw asume la ejecucion nativa de agentes, sesiones, tool-calls, continuaciones y streaming; mientras que nuestra capa custom se queda con la orquestacion de alto nivel, las reglas de negocio, la validacion y la presentacion.

La idea no es eliminar la capa custom. La idea es reducirla a lo que realmente aporta valor:
- politica de producto,
- estructura del proyecto,
- aprobaciones y aclaraciones,
- lifecycle del proyecto,
- validacion final,
- dashboard y observabilidad.

## Problema Del Enfoque Actual

Hoy el sistema funciona, pero esta sobrerrepresentando el codigo custom y subutilizando OpenClaw como plataforma de agentes.

### Sintomas concretos
- OpenClaw se usa para lanzar agentes, pero el flujo real depende mucho de prompts largos y parseo custom.
- La continuidad de sesion se ha tenido que robustecer a mano con `session_id`, fallbacks y diagnosticos.
- La estructura del proyecto se ha inferido tarde y a veces se ha mezclado con rutas de ejecucion temporales.
- El orquestador ha asumido funciones de planner, policy engine, reviewer, router de prompts y reconciliador de estado.
- El dashboard ha tenido que compensar residuos de runs anteriores, loops de eventos y estados obsoletos.
- Telegram se ha usado mas como canal de reactividad que como mecanismo de aclaracion temprana.

### Costes de ese enfoque
- Mas fragilidad en el contrato de salida.
- Mas reintentos por formato, no por contenido.
- Mas problemas de loops y estados duplicados.
- Menor autonomia real de BYTE y PIXEL.
- Mayor probabilidad de que el coordinador marque falsos negativos.
- Dificultad para escalar a proyectos mas complejos sin incrementar aun mas la complejidad del orquestador.

## Como Lo Resuelve La Arquitectura Hibrida

La arquitectura hibrida separa responsabilidades con mas precision.

### OpenClaw native
Debe manejar el ciclo tactico del agente:
- ejecucion,
- sesiones,
- tool-calls,
- stream de pensamientos,
- continuidad,
- reanudacion,
- recovery del gateway.

### Capa custom
Debe manejar la capa estrategica y de producto:
- clasificacion del proyecto,
- deteccion del stack,
- definicion de estructura canonica,
- aclaraciones por Telegram,
- bootstrap y limpieza,
- validacion final,
- dashboard,
- lifecycle del proyecto.

### Resultado esperado
- OpenClaw deja de ser solo un wrapper de LLM.
- BYTE y PIXEL pasan a comportarse como agentes reales.
- ARCH reduce su peso operacional y concentra su energia en decision y supervision.
- El sistema deja de pelear con estados duplicados y rutas inventadas.

## Reparto De Responsabilidades

### OpenClaw Native
- Ejecucion de agentes.
- Tool-calls y tool streaming.
- Continuacion de sesiones.
- Manejo de partial responses y eventos de pensamiento.
- Recovery del gateway.
- Reanudacion de trabajo sin reescribir el protocolo desde fuera.

### Capa Custom
- Clasificacion del proyecto.
- Deteccion de stack y estructura.
- Prompting de alto nivel.
- Aclaraciones por Telegram.
- Bootstrap y limpieza de proyectos.
- Reglas de aceptacion.
- Revision final.
- Dashboard, filtros y observabilidad.

## Estructuras Canonicas Por Tipo De Proyecto

### 1. Sitio Estatico O App Pequena Con Vanilla HTML/CSS/JS

Estructura esperada:

```text
root/
  index.html
  css/
    styles.css
  js/
    main.js
  assets/
  fonts/
```

Reglas:
- `index.html` vive en la raiz.
- `css/` contiene estilos.
- `js/` contiene logica.
- `assets/` o `img/` contiene recursos.
- `vendor/` solo si de verdad hay librerias externas.
- `output/frontend` no es una ruta canonica por defecto.

### 2. Aplicacion Web Con Framework

Estructura esperada:

```text
src/
  components/
  features/
  hooks/
  services/
  utils/
  pages/
public/
```

Reglas:
- La UI se organiza por componentes y funcionalidades.
- `src/` es la raiz logica.
- `public/` solo para estaticos publicos.
- La decision de framework debe quedar clara en planning antes de generar estructura.

### 3. Backend / API

Estructura esperada:

```text
backend/
  app/
  services/
  routes/
  config/
  tests/
```

Reglas:
- Separar dominio, rutas y tests.
- No mezclar salida de frontend con backend.
- Si el proyecto es API pura, la UI no debe inventarse una estructura paralela.

### 4. Laravel / Aplicaciones Existentes

Estructura esperada:
- Respetar la estructura del proyecto ya existente.
- Integrar dentro de `app/`, `resources/`, `views/`, `public/` y `tests/` segun corresponda.
- No sustituir el layout principal sin justificacion.

## Problemas Del Sistema Custom Y Como Los Corrige La Arquitectura Hibrida

### Problema 1. El coordinador se convierte en un super-agente
Hoy ARCH no solo coordina: decide estructura, parsea salida, revalida archivos, reescribe contexto y compensa fallos de ejecucion.

Correccion:
- ARCH debe devolver a OpenClaw la ejecucion tactica.
- ARCH se queda con planificacion, decisiones y desbloqueos.
- La coordinacion deja de ser una cadena de parches y pasa a ser una politica clara.

### Problema 2. Se confunde el estado del chat con el estado real
Ha pasado que un agente parecia fallar porque el texto no era limpio, aunque el archivo existia en disco.

Correccion:
- La fuente de verdad final pasa a ser filesystem + manifest.
- El chat solo documenta el proceso.
- El reviewer debe reconciliar lo que existe, no inferir solo desde la salida textual.

### Problema 3. Las rutas de ejecucion se inventan o llegan tarde
El sistema termino usando rutas como `output/frontend` o directorios de ejecucion poco representativos.

Correccion:
- La estructura la define el planner al inicio.
- El workspace incluye `project_structure`.
- Cada tarea tiene un `execution_dir` canonico derivado del tipo de proyecto.

### Problema 4. Los fallos de infraestructura se leen como fallos de contenido
Hubo errores de gateway, sesiones rotas y respuestas vacias que el orquestador trato como `Invalid JSON`.

Correccion:
- Clasificacion de fallos por tipo: `infra`, `formato`, `contenido`, `bloqueo`.
- Reintentar solo cuando tenga sentido.
- No seguir preguntando por JSON cuando el problema es timeout o provider failure.

### Problema 5. Telegram se usa demasiado tarde
Antes el sistema reaccionaba a bloqueos en vez de preguntar lo minimo necesario antes de planificar.

Correccion:
- Si el brief es ambiguo y el proyecto es nuevo, ARCH pregunta por Telegram antes de crear el plan.
- El flujo queda bloqueado de forma explicita hasta aclarar Vanilla vs framework o el alcance real.

### Problema 6. El dashboard muestra residuos de runs anteriores
Parte del ruido visual venia de eventos repetidos, tareas viejas o proyectos eliminados que seguian visibles.

Correccion:
- El dashboard consume snapshots consolidados.
- Los proyectos eliminados no se muestran.
- La eliminacion limpia workspaces y artefactos asociados.

## Fases De Implementacion

### Fase 0. Contrato Base Y Diagnostico

Objetivo:
- Definir que tipo de proyecto es cada brief.
- Normalizar la estructura canonica.
- Dejar claro que `output/frontend` no es la estructura por defecto.

Tareas:
- Añadir `project_structure` al contexto de memoria y de workspace.
- Unificar reglas de deteccion de stack y tipo de proyecto.
- Diferenciar con claridad `proyecto nuevo` vs `feature sobre proyecto existente`.
- Alinear las rutas de ejecucion con el tipo de entrega real.

Salida esperada:
- Cada proyecto tiene una estructura de referencia antes de ejecutar agentes.

### Fase 1. Planificador Con Preguntas Por Telegram

Objetivo:
- Hacer que ARCH pregunte cuando el brief no especifica lo importante.

Tareas:
- Si el proyecto es nuevo y no define Vanilla vs framework, enviar aclaracion por Telegram.
- Si el brief no requiere arquitectura, seguir sin frenar el flujo.
- Guardar la aclaracion pendiente en memoria para no repetirla en bucle.
- Registrar la respuesta en el runtime del proyecto para que no se pierda.

Salida esperada:
- El plan no se crea hasta resolver la ambiguedad critica.

### Fase 2. OpenClaw Como Motor De Agente

Objetivo:
- Pasar el ciclo tactico al runtime nativo de OpenClaw.

Tareas:
- Reducir parsing custom de stdout.
- Confiar mas en sesiones, eventos y continuaciones nativas.
- Mantener `session_id` estable solo como contrato de continuidad.
- Usar eventos de herramienta y pensamiento para el dashboard.
- Dejar que el agente nativo gestione su continuidad y solo exponer diagnostico al coordinador.

Salida esperada:
- BYTE y PIXEL se comportan como agentes reales, no como simples generadores de texto.

### Fase 3. Contrato De Archivos Y Workspace

Objetivo:
- Que cada agente trabaje sobre una estructura declarada y no inventada.

Tareas:
- Incluir la estructura canonica en `active_task.md/json`.
- Validar que los archivos finales estan donde el planificador dijo.
- Bloquear rutas inventadas o inconsistentes.
- Corregir tareas que ya tengan artefactos validos en vez de reiniciarlas.
- Hacer que el workspace refleje la tarea actual, no un run historico mezclado.

Salida esperada:
- El workspace y el manifest reflejan lo que realmente existe en disco.

### Fase 4. Revision, Recovery Y Observabilidad

Objetivo:
- Mejorar diagnostico, no solo ejecucion.

Tareas:
- Clasificar fallos en `infra`, `formato`, `contenido` o `bloqueo`.
- Reducir reintentos ciegos cuando el problema es de gateway o provider.
- Mostrar en el dashboard solo eventos consolidados y no duplicados.
- Conservar logs utiles para revision humana.
- Mantener el historial, pero sin contaminar la vista activa del proyecto.

Salida esperada:
- Un fallo de transporte deja de parecer un fallo de JSON.

### Fase 5. Dashboard Y Lifecycle Del Proyecto

Objetivo:
- Hacer que el dashboard sea la vista real del proyecto, no una capa confusa de residuos.

Tareas:
- Filtrar proyectos eliminados.
- Permitir borrar un proyecto y limpiar su workspace.
- Reanudar proyectos desde un estado limpio.
- Mostrar archivos producidos por proyecto y por tarea.
- Dejar claro el estado de cada tarea con evidencias reales.

Salida esperada:
- El dashboard representa el estado actual, no historicos mezclados.

### Fase 6. Simplificacion Y Retiro De Codigo Custom Redundante

Objetivo:
- Eliminar lo que ya no aporte valor.

Tareas:
- Retirar prompts o reglas duplicadas.
- Eliminar rutas antiguas como `output/frontend` si ya no aplican.
- Consolidar la logica de validacion y contexto.
- Dejar solo la capa custom que realmente agrega control de producto.

Salida esperada:
- La base de codigo es mas corta, mas predecible y mas facil de mantener.

## Detalle De Implementacion Por Componente

### `orchestrator.py`
Debe concentrar:
- la planificacion,
- la decision de estructura,
- el checkpoint de aclaraciones por Telegram,
- el mapeo de tareas a `execution_dir`,
- la transicion de estado,
- y la entrega final.

No debe convertirse en un parser de todo ni en un segundo runtime de agente.

### `coordination.py`
Debe concentrar:
- la deteccion de stack,
- la inferencia de estructura,
- la construccion del workspace,
- la generacion del contexto de tarea,
- y el contrato de salida para BYTE y PIXEL.

Aqui debe vivir la referencia canonica de estructura por tipo de proyecto.

### `openclaw_sdk.py`
Debe ser el wrapper fino del runtime:
- ejecutar agentes,
- manejar sesiones,
- recoger progress,
- soportar tool calls,
- exponer diagnostico de forma estable.

La meta es disminuir la logica custom que intenta simular lo que OpenClaw ya trae.

### `dashboard_api.py`
Debe exponer:
- estado,
- logs,
- snapshots consolidados,
- eliminacion de proyectos,
- reseteo limpio del workspace,
- y diagnostico operativo.

No debe ser una segunda fuente de verdad.

### `README.md`
Debe servir como entrada rapida y como indice hacia los documentos de arquitectura y operacion.

## Secuencia Recomendada De Migracion
1. Alinear tipos de proyecto y estructura canonica.
2. Hacer que ARCH pregunte por Telegram cuando falte stack o tipo.
3. Reducir la logica custom de continuidad de agente.
4. Normalizar los artefactos y el workspace.
5. Consolidar observabilidad y diagnostico.
6. Limpiar el codigo custom que quede obsoleto.

## Riesgos
- Si se migra demasiado rapido, se puede perder trazabilidad.
- Si se delega todo a OpenClaw sin contrato, el sistema puede volverse menos determinista.
- Si se deja la capa custom demasiado grande, OpenClaw seguira infrautilizado.
- Si no se actualiza el dashboard y el manifest al mismo tiempo, la vista del usuario seguira desalineada.

## Definicion De Exito

La arquitectura hibrida queda bien resuelta cuando:
- OpenClaw ejecuta agentes con continuidad y herramientas de forma natural.
- ARCH solo supervisa y decide lo que realmente es estrategico.
- La estructura de proyecto se define por tipo y no por improvisacion.
- El dashboard muestra estados reales, no residuos de runs anteriores.
- El flujo de trabajo puede empezar desde cero, preguntar lo necesario y entregar artefactos coherentes.
- El sistema deja de depender de parches para que los agentes parezcan agentes.
