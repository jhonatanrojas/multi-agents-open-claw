# BUGs Encontrados - Sistema Multi-Agentes OpenClaw

## Fecha: 2026-03-27

## BUGs Críticos

### 1. ✅ MiniverseBridge.check_inbox() no existe (ARREGLADO)
**Síntoma:** `'MiniverseBridge' object has no attribute 'check_inbox'`
**Causa:** El orquestador llama a `bridge.check_inbox()` pero la clase solo tenía `get_inbox()`
**Fix:** Agregado método `check_inbox()` como alias de `get_inbox()`
**Archivos:** 
- `/var/www/openclaw-multi-agents/miniverse_bridge.py`
- `/var/www/openclaw-multi-agents/skills/shared/miniverse_bridge.py`

### 2. ✅ _run_agent_task() llamado con argumentos incorrectos (ARREGLADO)
**Síntoma:** `_run_agent_task() missing 3 required positional arguments`
**Causa:** La llamada a `_run_agent_task` no incluía los parámetros `task_timeout_sec`, `retry_attempts`, `retry_delay_sec`
**Fix:** Actualizada la llamada para incluir todos los parámetros requeridos
**Archivo:** `/var/www/openclaw-multi-agents/orchestrator.py`

### 3. ⚠️ Rate Limit de API NVIDIA GLM5 (EXTERNO)
**Síntoma:** `429 - API rate limit reached` cuando se usa `nvidia/z-ai/glm5`
**Causa:** El modelo GLM5 tiene límites de uso de API
**Solución temporal:** Cambiar a modelos alternativos (DeepSeek, Mistral)
**Estado:** Pendiente de configuración de fallbacks adecuados

### 4. ⚠️ DeepSeek Insufficient Balance (EXTERNO)
**Síntoma:** `402 - Insufficient Balance` cuando se usa `deepseek/deepseek-chat`
**Causa:** Cuenta de DeepSeek sin saldo
**Solución temporal:** Usar otros modelos (Mistral, Kimi)
**Estado:** Requiere recarga de saldo en DeepSeek

### 5. ❌ Estado de proyecto persistente entre ejecuciones (NO ARREGLADO)
**Síntoma:** `Recuperadas 1 tarea(s) bloqueadas en in_progress → pending`
**Causa:** El orquestador carga MEMORY.json que puede tener tareas de ejecuciones anteriores fallidas
**Impacto:** Las nuevas solicitudes de proyecto se mezclan con tareas antiguas
**Sugerencia:** 
  - Agregar flag `--fresh` para limpiar estado antes de iniciar
  - O limpiar automáticamente tareas en `in_progress` al iniciar nuevo proyecto

### 6. ❌ Loop infinito de errores de inbox (ARREGLADO parcialmente)
**Síntoma:** Repetición de errores cada 2 segundos
**Causa:** El error de `check_inbox` se repetía en un loop
**Estado:** Arreglado con el fix del BUG #1

## Mejoras Sugeridas

### Arquitectura

1. **Sistema de Fallbacks de Modelos**
   - Implementar rotación automática de modelos cuando hay rate limits
   - Configurar fallbacks jerárquicos: GLM5 → DeepSeek → Mistral → Kimi

2. **Gestión de Estado Mejorada**
   - Separar estado de proyecto activo de histórico
   - Implementar `MEMORY.json` por proyecto, no global
   - Agregar comando `clear-state` en la API

3. **Timeouts y Reintentos**
   - Agregar timeout para tareas individuales
   - Implementar backoff exponencial para reintentos
   - Logs más detallados para debugging

4. **Selector de Modelo Dinámico**
   - El dashboard ya tiene endpoints para cambiar modelos
   - Agregar persistencia en config por agente
   - Implementar hot-reload sin reiniciar orquestador

### Código

5. **Validación de Argumentos**
   - Agregar type hints completos
   - Validar argumentos en runtime
   - Tests unitarios para funciones críticas

6. **Manejo de Errores**
   - Categorizar errores: infra, content, blocked
   - Diferentes estrategias por tipo de error
   - Notificaciones diferenciadas

## Configuración Actual de Modelos

| Agente | Modelo | Estado |
|--------|--------|--------|
| arch | deepseek/deepseek-chat | ⚠️ Sin saldo |
| byte | mistral/mistral-large-latest | ✅ OK |
| pixel | deepseek/deepseek-chat | ⚠️ Sin saldo |
| main | nvidia/z-ai/glm5 | ⚠️ Rate limit |

## Próximos Pasos

1. Configurar modelos con balance disponible
2. Implementar limpieza de estado al iniciar nuevo proyecto
3. Agregar tests de integración
4. Documentar API del dashboard
