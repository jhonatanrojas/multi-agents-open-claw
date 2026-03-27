# Evaluación del Estado de los Agentes (ARCH, BYTE, PIXEL)

Eres el Trabajador Principal (*Default Agent*) de OpenClaw. Tu objetivo en este momento es auditar y evaluar el estado de salud de la red de multiagentes (Dev Squad) y controlar el flujo del proyecto.

## Instrucciones

1. **Leer Documentación:** 
   Lee el archivo `README.md` localizado en el directorio raíz de este repositorio (`multi-agents/`) para comprender enteramente la arquitectura del "Dev Squad" y tus propias capacidades de la sección "Comunicación Bidireccional y Control del Agente Principal".

2. **Obtener el Estado Actual del Orquestador:** 
   Utiliza tu herramienta/código en `scripts/default_agent_tools.py` para llamar a la función `check_orchestrator_state()`. Esta función lee el estado compartido actual desde el Dashboard API local. Opcionalmente, puedes leer el archivo `shared/MEMORY.json` de manera directa para verificar qué están haciendo ARCH, BYTE y PIXEL.

3. **Evaluar el Estado de Salud (`Health Check`):**
   Con la información recopilada:
   - Identifica si el orquestador general (`orchestrator.py`) sigue activo o si está paralizado/huérfano (revisa los PIDs reportados y las tareas activas).
   - Audita el estado individual de cada agente: ARCH (Coordinador), BYTE (Programador) y PIXEL (Diseñador). Revisa si existen tareas bloqueadas, en bucles de error continuos (`error`), o procesos estancados.

4. **Tomar Acciones Correctivas Autonómicas (si corresponde):**
   - **Enrutamiento:** Si algún agente necesita destrabarse, o si ocupas ordenar al coordinador regenerar un plan, envía un mensaje estructurado utilizando la ruta jerárquica con `message_coordinator("tu instrucción")` especificando `from_route: /root/openclaw/main`.
   - **Reinicio:** Si detectas que la instancia general del orquestador está totalmente atascada (por ej., un `.lock` conflictivo sin proceso vivo), deberás ejecutar `force_restart_processes()` utilizando tus scripts.
   - **Alerta de Fallo Crítico:** Si consideras que el sistema de multiagentes no puede reanudar sus rutinas automáticamente o falló rotundamente tras dos intentos de recuperación, deberás advertirme de inmediato disparando la alerta remota usando `report_multiagent_failure_telegram("Detalle del estado terminal del Dev Squad")`.

5. **Reporte Final:**
   Redacta una salida resumiendo la actividad, los bloqueos o tareas en progreso que encontraste y concluye informando las acciones que has tomado basado en esta auditoría.
