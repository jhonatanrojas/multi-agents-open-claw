# Guía de despliegue — Dev Squad en VPS con systemd

Agente senior de integración para OpenClaw `2026.3.23-2`.

**Objetivo:** dejar `orchestrator.py` y `dashboard_api.py` corriendo de forma persistente en el VPS mediante `systemd`, con Apache como reverse proxy, autenticación por API key, WebSocket habilitado y estado verificable por CLI sin depender de ninguna interfaz gráfica.

---

## Configuración del entorno

| Parámetro                    | Valor                                            |
|------------------------------|--------------------------------------------------|
| Ruta del proyecto en el VPS  | `/var/www/openclaw-multi-agents`                 |
| Servicio del orquestador     | `openclaw-multiagent.service`                    |
| Servicio del dashboard       | `openclaw-dashboard.service`                     |
| Puerto local del dashboard   | `127.0.0.1:8001`                                 |
| URL pública objetivo         | `https://openclaw.deploymatrix.com/`             |
| Health check                 | `http://127.0.0.1:8001/health`                   |
| Archivo de entorno compartido| `/etc/default/openclaw-multiagent`               |
| Usuario del servicio         | `www-data`                                       |
| Puerto 8080                  | **Ocupado — no usar**                            |
| Proxy público                | Apache reverse proxy (no exponer uvicorn directo)|
| Repositorio base             | `https://github.com/jhonatanrojas/multi-agents-open-claw` |

---

## Reglas obligatorias

- No romper la configuración actual de OpenClaw.
- No usar comandos destructivos (`rm -rf`, `git reset --hard`, `DROP TABLE`…).
- Validar todo por CLI antes de asumir que la interfaz gráfica funciona.
- Si un archivo no existe, crearlo solo si aporta valor real a la operación persistente.
- Reportar cualquier bloqueo con precisión antes de continuar.

---

## Variables de entorno — `/etc/default/openclaw-multiagent`

Todas las variables sensibles van aquí. El archivo lo leen ambos servicios systemd.

```ini
# ── Auth dashboard (todos los endpoints excepto /health) ──────────────────────
DASHBOARD_API_KEY=dev-squad-api-key-2026

# ── Telegram (opcional) ───────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=

# ── Miniverse ─────────────────────────────────────────────────────────────────
MINIVERSE_URL=https://miniverse-public-production.up.railway.app

# ── Git identity ──────────────────────────────────────────────────────────────
GIT_AUTHOR_NAME=OpenClaw
GIT_AUTHOR_EMAIL=openclaw@example.com

# ── Modelos (override sobre gateway.yml) ──────────────────────────────────────
ARCH_MODEL=nvidia/z-ai/glm5
BYTE_MODEL=nvidia/moonshotai/kimi-k2.5
BYTE_MODEL_FALLBACK=deepseek/deepseek-chat
PIXEL_MODEL=deepseek/deepseek-chat

# ── Python ────────────────────────────────────────────────────────────────────
PYTHONUNBUFFERED=1
```

Crear o actualizar el archivo:
```bash
sudo cp /var/www/openclaw-multi-agents/.env.example /etc/default/openclaw-multiagent
sudo chmod 640 /etc/default/openclaw-multiagent
sudo chown root:www-data /etc/default/openclaw-multiagent
# Editar con valores reales:
sudo nano /etc/default/openclaw-multiagent
```

---

## Fase 1 — Auditoría y preparación

```bash
cd /var/www/openclaw-multi-agents

# 1. Verificar Python y dependencias
python3 --version                    # >= 3.11
python3 -m pip show openclaw-sdk fastapi uvicorn requests

# 2. Verificar que OpenClaw esté instalado y configurado
openclaw --version
cat ~/.openclaw/gateway.yml          # confirmar modelos y rutas

# 3. Verificar que los paths relativos en gateway.yml resuelvan desde el proyecto
ls workspaces/coordinator/SOUL.md
ls skills/miniverse-bridge/SKILL.md
ls shared/MEMORY.json 2>/dev/null || echo "Se creará en el primer arranque"

# 4. Probar importaciones
python3 -c "from orchestrator import *; print('OK')"
python3 -c "from dashboard_api import app; print('OK')"

# 5. Dry-run para validar flujo completo sin consumir tokens
python3 orchestrator.py --dry-run "Proyecto de prueba para auditoría"
```

Puntos a verificar en la auditoría:

- [ ] `gateway.yml` apunta a los modelos correctos (`nvidia/z-ai/glm5`, `kimi-k2.5`, `deepseek`)
- [ ] `shared/MEMORY.json` existe o se creará correctamente
- [ ] `logs/` existe con permisos de escritura para `www-data`
- [ ] `output/` existe con permisos de escritura para `www-data`
- [ ] El lockfile `logs/orchestrator.lock` no está de una corrida anterior colgada

---

## Fase 2 — Persistencia con systemd

### 2.1 Instalar los servicios

```bash
sudo bash /var/www/openclaw-multi-agents/scripts/install_systemd.sh \
  /var/www/openclaw-multi-agents

sudo systemctl daemon-reload
```

El script copia los archivos de `deploy/systemd/` a `/etc/systemd/system/` y crea el archivo de entorno en `/etc/default/openclaw-multiagent`.

### 2.2 Verificar los archivos de servicio

**`/etc/systemd/system/openclaw-multiagent.service`** (orquestador):
```ini
[Unit]
Description=Dev Squad Multi-Agent Orchestrator
After=network.target openclaw-gateway.service
Wants=openclaw-gateway.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/openclaw-multi-agents
EnvironmentFile=/etc/default/openclaw-multiagent
ExecStart=/var/www/openclaw-multi-agents/.venv/bin/python orchestrator.py \
  --task-timeout-sec 1800 \
  --phase-timeout-sec 7200 \
  --retry-attempts 3 \
  --max-parallel-byte 1 \
  --max-parallel-pixel 1
Restart=always
RestartSec=5
StandardOutput=append:/var/www/openclaw-multi-agents/logs/orchestrator.log
StandardError=append:/var/www/openclaw-multi-agents/logs/orchestrator.log
ProtectSystem=full
ProtectHome=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/openclaw-dashboard.service`** (dashboard API):
```ini
[Unit]
Description=Dev Squad Dashboard API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/openclaw-multi-agents
EnvironmentFile=/etc/default/openclaw-multiagent
ExecStart=/var/www/openclaw-multi-agents/.venv/bin/uvicorn \
  dashboard_api:app \
  --host 127.0.0.1 \
  --port 8001 \
  --workers 1
Restart=always
RestartSec=5
ProtectSystem=full
ProtectHome=true
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
```

### 2.3 Habilitar y arrancar

```bash
sudo systemctl enable openclaw-dashboard
sudo systemctl enable openclaw-multiagent

sudo systemctl start openclaw-dashboard
sudo systemctl start openclaw-multiagent

# Verificar estado
sudo systemctl status openclaw-dashboard --no-pager
sudo systemctl status openclaw-multiagent --no-pager
```

---

## Fase 3 — Apache Reverse Proxy

Archivo: `deploy/apache/openclaw-dashboard.conf`

```apache
<VirtualHost *:80>
    ServerName openclaw.deploymatrix.com
    Redirect permanent / https://openclaw.deploymatrix.com/
</VirtualHost>

<VirtualHost *:443>
    ServerName openclaw.deploymatrix.com

    SSLEngine on
    SSLCertificateFile    /etc/letsencrypt/live/openclaw.deploymatrix.com/fullchain.pem
    SSLCertificateKeyFile /etc/letsencrypt/live/openclaw.deploymatrix.com/privkey.pem

    # REST + SSE
    ProxyPreserveHost On
    ProxyPass        /api/  http://127.0.0.1:8001/api/
    ProxyPassReverse /api/  http://127.0.0.1:8001/api/
    ProxyPass        /health http://127.0.0.1:8001/health
    ProxyPassReverse /health http://127.0.0.1:8001/health

    # WebSocket (/ws/state) — GAP-9
    RewriteEngine On
    RewriteCond %{HTTP:Upgrade} websocket [NC]
    RewriteCond %{HTTP:Connection} upgrade [NC]
    RewriteRule ^/ws/(.*)$ ws://127.0.0.1:8001/ws/$1 [P,L]
    ProxyPass        /ws/  ws://127.0.0.1:8001/ws/
    ProxyPassReverse /ws/  ws://127.0.0.1:8001/ws/

    # SSE — desactivar buffering para que los eventos fluyan inmediatamente
    ProxyPass        /api/stream http://127.0.0.1:8001/api/stream flushpackets=on
    SetEnv proxy-sendchunked 1

    ErrorLog  /var/log/apache2/openclaw-dashboard-error.log
    CustomLog /var/log/apache2/openclaw-dashboard-access.log combined
</VirtualHost>
```

Instalar y habilitar:
```bash
sudo cp deploy/apache/openclaw-dashboard.conf \
  /etc/apache2/sites-available/openclaw-dashboard.conf
sudo a2ensite openclaw-dashboard
sudo a2enmod proxy proxy_http proxy_wstunnel rewrite ssl
sudo apache2ctl configtest
sudo systemctl reload apache2
```

---

## Fase 4 — Pruebas sin interfaz gráfica

### 4.1 Health check
```bash
# Sin auth (endpoint público)
curl -s http://127.0.0.1:8001/health | python3 -m json.tool

# Desde script
python3 scripts/check_health.py --url http://127.0.0.1:8001/health
```

Respuesta esperada (sistema en reposo):
```json
{
  "ok": true,
  "service": "dashboard_api",
  "lockfile": { "exists": false },
  "orchestrator": { "status": "idle" },
  "issues": [],
  "auth_enabled": true
}
```

### 4.2 Estado de memoria
```bash
curl -s http://127.0.0.1:8001/api/state \
  -H "X-API-Key: dev-squad-api-key-2026" | python3 -m json.tool
```

### 4.3 Modelos actuales
```bash
curl -s http://127.0.0.1:8001/api/models \
  -H "X-API-Key: dev-squad-api-key-2026" | python3 -m json.tool
```

### 4.4 Lanzar proyecto vía API
```bash
curl -X POST http://127.0.0.1:8001/api/project/start \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-squad-api-key-2026" \
  -d '{
    "brief": "Construye una API REST de tareas con FastAPI y SQLite",
    "allow_init_repo": true,
    "dry_run": true
  }'
```

### 4.5 Seguimiento de logs en tiempo real
```bash
# Logs del orquestador
journalctl -u openclaw-multiagent -f

# Log estructurado JSONL
tail -f /var/www/openclaw-multi-agents/logs/orchestrator.jsonl | \
  python3 -c "import sys,json; [print(json.dumps(json.loads(l), ensure_ascii=False)) for l in sys.stdin]"

# Log plano
tail -f /var/www/openclaw-multi-agents/logs/orchestrator.log
```

### 4.6 Prueba de SSE desde CLI
```bash
curl -N -H "X-API-Key: dev-squad-api-key-2026" \
  http://127.0.0.1:8001/api/stream
# Deben aparecer líneas "data: {...}" cada 2 s o ": keepalive" si no hay cambios
```

### 4.7 Prueba de WebSocket
```bash
# Requiere wscat: npm install -g wscat
wscat -c "ws://127.0.0.1:8001/ws/state" \
  -H "X-API-Key: dev-squad-api-key-2026"
```

---

## Fase 5 — Verificación final y operación

### Comandos de operación diaria

```bash
# Estado de ambos servicios
sudo systemctl status openclaw-multiagent openclaw-dashboard --no-pager

# Reiniciar orquestador (sin tocar el dashboard)
sudo systemctl restart openclaw-multiagent

# Reiniciar dashboard
sudo systemctl restart openclaw-dashboard

# Ver logs del servicio (últimas 50 líneas)
journalctl -u openclaw-multiagent -n 50 --no-pager
journalctl -u openclaw-dashboard  -n 50 --no-pager

# Detener ambos
sudo systemctl stop openclaw-multiagent openclaw-dashboard

# Forzar un health check completo
python3 /var/www/openclaw-multi-agents/scripts/check_health.py \
  --url http://127.0.0.1:8001/health
```

### Cambiar modelo de un agente en caliente

```bash
# Cambiar BYTE a deepseek como primario
curl -X PUT http://127.0.0.1:8001/api/models \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-squad-api-key-2026" \
  -d '{"byte": "deepseek/deepseek-chat"}'

# Actualizar también gateway.yml y reiniciar openclaw-gateway para que el
# gateway tome el nuevo modelo en la próxima sesión
sudo nano ~/.openclaw/gateway.yml
openclaw restart   # o el comando equivalente de tu instalación
```

### Actualizar el proyecto desde git

```bash
cd /var/www/openclaw-multi-agents
sudo -u www-data git pull origin main
sudo -u www-data .venv/bin/pip install -r requirements.txt --quiet
sudo systemctl restart openclaw-multiagent openclaw-dashboard
```

---

## Checklist de éxito

- [ ] `sudo systemctl is-active openclaw-multiagent` devuelve `active`
- [ ] `sudo systemctl is-active openclaw-dashboard` devuelve `active`
- [ ] `curl http://127.0.0.1:8001/health` devuelve `{"ok": true, ...}`
- [ ] `curl https://openclaw.deploymatrix.com/health` devuelve 200 vía Apache
- [ ] SSE stream devuelve eventos o keepalives sin cortes
- [ ] WebSocket en `/ws/state` conecta y recibe estado inicial
- [ ] Un dry-run lanza, ejecuta tareas y genera `DELIVERY.md`
- [ ] Los logs aparecen en `journalctl` y en `logs/orchestrator.jsonl`
- [ ] La autenticación rechaza requests sin `X-API-Key` (HTTP 401)
- [ ] OpenClaw gateway sigue activo e intacto después del despliegue

---

## Riesgos y pendientes

| Riesgo                                      | Mitigación                                                   |
|---------------------------------------------|--------------------------------------------------------------|
| `openclaw-gateway` no arranca como servicio | Verificar con `openclaw status`; agregar `After=` en el unit |
| Puerto 8001 ocupado                         | `ss -tlnp | grep 8001`; ajustar en el unit y en Apache       |
| Permisos de `www-data` sobre el proyecto    | `sudo chown -R www-data:www-data /var/www/openclaw-multi-agents` |
| Certificado SSL de Apache vencido           | `sudo certbot renew --dry-run`                               |
| MEMORY.json corrompido en crash             | Borrar el archivo; se regenera vacío en el próximo arranque  |
| Lockfile obsoleto tras crash                | `rm logs/orchestrator.lock` y reiniciar el servicio          |
| Modelo no disponible en OpenClaw            | Verificar con `openclaw models list`; ajustar `models_config.json` |
