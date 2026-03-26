# Guia de despliegue y frontend integrado para OpenClaw

Eres un agente senior de codigo e integracion para OpenClaw.

Objetivo general:
Configurar y dejar persistentes `orchestrator.py` y `dashboard_api.py` con `systemd`, probar la funcionalidad sin interfaz grafica, verificar que todo funcione correctamente y actualizar los scripts o archivos auxiliares que sean necesarios para estabilizar el flujo multiagent.

Adicionalmente, debes integrar el frontend del dashboard dentro de `/var/www/openclaw-portal`, que es un proyecto Laravel 8 ya existente en el VPS, reutilizando los estilos y funcionalidades de `DevSquadDashboard.jsx` y consumiendo el API del orquestador sin romper el portal actual.

Configuracion inicial actualizada para el despliegue:
- Ruta del backend y scripts Python: `/var/www/openclaw-multi-agents`
- Ruta del frontend Laravel 8: `/var/www/openclaw-portal`
- Servicio del orquestador: `openclaw-multiagent.service`
- Servicio del dashboard API: `openclaw-dashboard.service`
- Puerto local del dashboard API: `127.0.0.1:8001`
- Healthcheck del dashboard API: `http://127.0.0.1:8001/health`
- URL publica objetivo: `https://openclaw.deploymatrix.com/`
- Apache ya esta en uso en el VPS y debe actuar como punto de entrada publico
- El puerto `8080` debe considerarse ocupado y no debe usarse
- Archivo de entorno compartido: `/etc/default/openclaw-multiagent`
- Usuario del servicio: `www-data`
- Fuente visual y funcional del dashboard: `DevSquadDashboard.jsx`
- Si el frontend necesita publicar el dashboard, debe hacerlo via Apache reverse proxy o una ruta compatible del portal Laravel
- Scripts disponibles para despliegue y salud: `scripts/install_systemd.sh` y `scripts/check_health.py`

Contexto del proyecto:
- clona Repositorio base: https://github.com/jhonatanrojas/multi-agents-open-claw
- OpenClaw ya esta instalado en el VPS.
- La configuracion vigente de OpenClaw debe respetarse.
- Usa solo los modelos configurados en OpenClaw, no Anthropic.

Archivos prioritarios:
- `orchestrator.py`
- `dashboard_api.py`
- `coordination.py`
- `shared_state.py`
- `DevSquadDashboard.jsx`
- `deploy/systemd/openclaw-multiagent.service`
- `deploy/systemd/openclaw-dashboard.service`
- `deploy/apache/openclaw-dashboard.conf`
- `scripts/install_systemd.sh`
- `scripts/check_health.py`
- `~/.openclaw/gateway.yml`
- rutas, vistas, controladores y assets del proyecto Laravel 8 en `/var/www/openclaw-portal`

Reglas obligatorias:
- No rompas la configuracion actual de OpenClaw.
- No uses comandos destructivos.
- No asumas que la interfaz grafica esta disponible; primero valida todo por CLI y procesos.
- Si un archivo o script no existe, crealo solo si aporta valor real a la operacion persistente.
- Si detectas que falta una pieza para `systemd`, corrigela en el codigo o en los scripts.
- Si algo requiere aprobacion o datos del VPS, informa el bloqueo con precision.
- El backend operativo puede permanecer en `/var/www/openclaw-multi-agents`, pero el frontend final debe integrarse en `/var/www/openclaw-portal`.
- Extrae estilos, layout y comportamiento visual desde `DevSquadDashboard.jsx` para llevarlos a Laravel 8.
- El frontend Laravel debe consumir el API del orquestador por una ruta o proxy compatible, sin exponer el puerto `8001` directamente al navegador.

Fase 1. Auditoria y preparacion
1. Inspecciona `orchestrator.py`, `dashboard_api.py`, `coordination.py`, `shared_state.py` y `~/.openclaw/gateway.yml`.
2. Identifica como se inicia hoy el orquestador, como se persiste el estado y como se supervisan tareas.
3. Detecta dependencias fragiles, rutas rotas, suposiciones sobre la interfaz y cualquier punto que impida ejecutar sin UI.
4. Define que archivos deben quedar listos para correr como servicio persistente.
5. Inspecciona el proyecto Laravel 8 en `/var/www/openclaw-portal` para determinar donde integrar el dashboard.
6. Identifica la ruta, el controlador, la vista y los assets que conviene usar o crear para el dashboard.

Fase 2. Persistencia con systemd
1. Crea o actualiza un servicio `systemd` para ejecutar el orquestador de forma persistente.
2. Asegura reinicio automatico, logs utiles y arranque al boot.
3. Verifica que el servicio use el directorio correcto y que no dependa de la interfaz.
4. Crea o actualiza el segundo servicio `systemd` para el dashboard, escuchando solo en `127.0.0.1:8001`.
5. Si hace falta, crea o ajusta scripts auxiliares para:
   - iniciar el sistema
   - detenerlo
   - reiniciarlo
   - consultar estado
   - revisar logs
6. Si Apache debe publicar el panel, prepara el reverse proxy correspondiente sin chocar con otras apps del VPS.

Fase 3. Integracion del frontend Laravel 8
1. Analiza la estructura del proyecto Laravel 8 en `/var/www/openclaw-portal`.
2. Identifica o crea una ruta real, un controlador y una vista Blade para el dashboard.
3. Extrae y adapta los estilos, componentes y layout de `DevSquadDashboard.jsx`.
4. Reproduce en Laravel 8 la misma experiencia del dashboard original, conservando sus funcionalidades.
5. Conecta el frontend Laravel con el API del orquestador mediante una ruta o proxy seguro.
6. Si el dashboard original dependia de React, extrae el estilo y la logica de presentacion para llevarla a Blade, CSS y assets de Laravel 8.
7. No rompas las rutas existentes del portal ni sustituyas su layout principal sin justificarlo.
8. Asegura que el frontend integrado consuma:
   - estado
   - logs
   - health
   - inicio de proyectos
   - revision de tareas y progreso
   - mensajes de bloqueo o errores

Fase 4. Pruebas sin interfaz
1. Ejecuta una prueba completa desde CLI.
2. Verifica que el orquestador:
   - levanta correctamente
   - detecta o crea repositorio cuando corresponde
   - asigna skills dinamicos por stack
   - escribe progreso por agente
   - notifica avances o bloqueos
3. Valida que `dashboard_api.py` pueda responder aunque no se use la UI.
4. Comprueba que no haya errores silenciosos, loops rotos o tareas estancadas.
5. Verifica que el frontend Laravel 8 puede consumir el API del orquestador correctamente.

Fase 5. Ajustes y correcciones
1. Si encuentras bugs, gaps o inconsistencias, corrige el codigo.
2. Actualiza scripts, rutas, variables de entorno o mensajes de estado si es necesario.
3. Mejora la robustez del arranque, la reconexion, el manejo de errores y la persistencia.
4. Asegura que los archivos de progreso y memoria queden en un estado coherente.
5. Si el frontend Laravel requiere proxy, middleware, config o assets adicionales, integralos sin romper el portal.

Fase 6. Verificacion final
1. Confirma que el servicio queda persistente con `systemd`.
2. Confirma que el orquestador funciona sin interfaz grafica.
3. Confirma que el flujo multiagent responde y actualiza estado correctamente.
4. Confirma que el dashboard queda accesible localmente por healthcheck y que Apache puede publicarlo sin usar el puerto `8080`.
5. Confirma que el frontend Laravel 8 en `/var/www/openclaw-portal` renderiza la vista correcta y consume el API del orquestador.
6. Entrega instrucciones exactas para:
   - habilitar el servicio
   - revisar logs
   - reiniciar el orquestador
   - integrar el cambio en el OpenClaw actual del VPS
   - desplegar el frontend en Laravel 8
   - validar la ruta y vista integradas

Entregables obligatorios:
- Resumen de auditoria.
- Lista de bugs corregidos.
- Lista de scripts creados o actualizados.
- Archivo(s) `systemd` creados o modificados.
- Configuracion de Apache creada o actualizada, si aplica.
- Ruta, controlador, vista o componente Laravel creados o modificados para el frontend.
- Evidencia de que el frontend Laravel consume el API del orquestador.
- Comandos exactos para instalar, habilitar y verificar el servicio.
- Resultado de las pruebas sin interfaz.
- Riesgos o pendientes, si quedo alguno.

Criterio de exito:
El multiagent queda corriendo como servicio persistente, con backend operativo en `/var/www/openclaw-multi-agents`, frontend integrado en Laravel 8 dentro de `/var/www/openclaw-portal`, estado verificable por CLI y OpenClaw actual intacto.
