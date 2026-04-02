# Cómo implementar nuevas tareas con el cron oficial de OpenClaw

Esta guía explica cómo agregar nuevas tareas o fases al sistema multiagente usando el cron oficial de OpenClaw.

## Principio base

El flujo oficial es:

1. `openclaw cron` dispara una sola vez la sesión `main`.
2. `main` lee `STATE_multiagent.md`, `CONTEXT_multiagent.md`, `PLAN_multiagent.md` y `TELEGRAM_multiagent.md`.
3. `main` ejecuta exactamente una fase o un solo paso de fase.
4. Si no hace falta confirmación humana, la fase avanza sola.
5. Si hace falta confirmación, el flujo se pausa y se notifica por Telegram.
6. El estado se actualiza en `STATE_multiagent.md`.
7. La compactación se hace según el calendario del estado.

No se crea un runner paralelo por cada tarea.
No se mezcla este flujo con el dashboard.

## Cuándo usar esta guía

Úsala cuando quieras:

- agregar una fase nueva,
- extender una fase existente,
- reanudar una tarea bloqueada,
- añadir una corrección puntual sobre el mismo proyecto,
- o crear un flujo de trabajo repetible para otro objetivo.

## Qué archivos tocar

### `PLAN_multiagent.md`

Aquí defines la nueva tarea o fase:

- nombre de la fase,
- objetivo,
- criterios de aceptación,
- archivos esperados,
- si requiere o no confirmación humana,
- y cuándo debe compactarse.

### `STATE_multiagent.md`

Aquí registras el estado operativo:

- fase actual,
- estado de cada fase,
- bloqueadores activos,
- hitos,
- y checkpoint de compactación.

### `CONTEXT_multiagent.md`

Aquí dejas el contexto operativo que `main` debe leer antes de ejecutar:

- rutas reales,
- contratos,
- reglas de negocio,
- dependencias,
- y decisiones ya tomadas.

### `TELEGRAM_multiagent.md`

Aquí quedan los mensajes listos para:

- arrancar una fase,
- pedir confirmación,
- avisar bloqueos,
- reanudar después de una respuesta,
- y anunciar compactaciones.

## Cómo agregar una nueva tarea

### 1. Define la fase

Agrega una entrada nueva en `PLAN_multiagent.md`.

Ejemplo:

```text
F5.1 — Agregar health checks formales

Objetivo:
- Crear un endpoint /health estable y usable por monitoreo externo.

Archivos esperados:
- dashboard_api.py
- tests/test_health.py

Criterio de aceptación:
- /health responde 200 con gateway, database y lock_backend.
- El dashboard muestra el estado global sin errores.

Compactar al terminar:
- sí, porque cierra una subfase completa.
```

### 2. Registra la fase en el estado

Agrega la fila correspondiente en `STATE_multiagent.md`:

```text
| F5.1 | Agregar health checks formales | pending |           |       |
```

Si la fase requiere pausa humana, marca el estado como bloqueado cuando llegue ese punto y deja el motivo en `Active Blockers`.

### 3. Actualiza el contexto

Si la nueva tarea introduce rutas, contratos o decisiones nuevas, añádelas en `CONTEXT_multiagent.md`.

Regla práctica:

- si `main` lo necesita para ejecutar la fase, debe estar en `CONTEXT_multiagent.md`;
- si solo es información histórica, puede ir en `STATE_multiagent.md` como milestone o checkpoint.

### 4. Prepara Telegram

Si la nueva fase necesita confirmación, agrega un bloque en `TELEGRAM_multiagent.md` con el texto exacto que debe enviarse.

Ejemplo:

```text
## To execute F5.1
Read F5.1 from PLAN_multiagent.md and CONTEXT_multiagent.md.
Implement it under the official OpenClaw cron job.
If confirmation is required, pause and notify by Telegram.
End with: ✅ F5.1 COMPLETE
```

## Cómo ejecutar la tarea

### Arranque automático

El job oficial `multiagent-phase-runner` se encarga de disparar `main`.

No crees otro job para la misma tarea.

### Arranque manual

Si necesitas probar la tarea ahora mismo, usa el job oficial:

```bash
openclaw gateway call cron.list --json --url ws://127.0.0.1:18789 --token <gateway-token> --params '{}'
openclaw gateway call cron.run --json --url ws://127.0.0.1:18789 --token <gateway-token> --params '{"id":"<job-id>"}'
```

### Lo que debe hacer `main`

Cuando el cron oficial dispare la tarea, `main` debe:

- leer `STATE_multiagent.md`,
- leer `CONTEXT_multiagent.md`,
- leer `PLAN_multiagent.md`,
- ejecutar solo la fase que toca,
- generar archivos o cambios concretos,
- actualizar `STATE_multiagent.md`,
- enviar el resumen por Telegram,
- y compactar si corresponde.

## Si la tarea necesita pausa

Si la nueva tarea no puede continuar sin validación humana:

1. deja el estado como bloqueado,
2. registra el motivo en `Active Blockers`,
3. envía el mensaje de Telegram definido,
4. espera la respuesta,
5. y reanuda la misma fase cuando llegue la confirmación.

No reinicies la tarea desde cero si solo faltaba una respuesta humana.

## Buenas prácticas

- Mantén una sola fuente de verdad operativa en `STATE_multiagent.md`.
- No dupliques la misma fase en el cron oficial y en un script local.
- No mezcles este flujo con el dashboard de proyecto.
- Usa compactación al terminar fases grandes o en los puntos definidos por el plan.
- Si una fase falló por estado inconsistente, corrige primero coordinación y memoria antes de volver a ejecutar.

## Errores comunes

- Crear un job nuevo para cada tarea.
- Ejecutar la misma fase en paralelo desde dos lugares.
- Guardar el avance solo en el chat y no en el estado.
- Olvidar actualizar `STATE_multiagent.md` después de cada fase.
- Pedir confirmación humana sin dejar el bloqueo documentado.

## Plantilla rápida

```text
1. Agregar fase en PLAN_multiagent.md
2. Agregar fila en STATE_multiagent.md
3. Actualizar CONTEXT_multiagent.md si cambian rutas o contratos
4. Ajustar TELEGRAM_multiagent.md si hace falta confirmar o notificar
5. Ejecutar con el job oficial multiagent-phase-runner
6. Actualizar STATE_multiagent.md al terminar
7. Compactar cuando el plan lo indique
```

## Relación con la automatización oficial

Este documento es el playbook oficial para agregar nuevas tareas encima del cron integrado de OpenClaw.
Úsalo como referencia principal para extender fases, actualizar `PLAN_multiagent.md`,
sincronizar `STATE_multiagent.md` y coordinar notificaciones por Telegram.
