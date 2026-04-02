#!/usr/bin/env bash
# scripts/manage.sh — gestión del sistema multiagente OpenClaw
set -euo pipefail

CMD="${1:-status}"

case "$CMD" in
  start)
    systemctl start openclaw-dashboard
    echo "✓ openclaw-dashboard iniciado"
    ;;
  stop)
    systemctl stop openclaw-dashboard 2>/dev/null || true
    pkill -f "orchestrator.py" 2>/dev/null || true
    echo "✓ Servicios detenidos"
    ;;
  restart)
    systemctl restart openclaw-dashboard
    echo "✓ openclaw-dashboard reiniciado"
    ;;
  status)
    echo "=== openclaw-dashboard ==="
    systemctl status openclaw-dashboard --no-pager -l | head -12
    echo ""
    echo "=== Health API ==="
    curl -s http://127.0.0.1:8001/health | python3 -m json.tool 2>/dev/null || echo "API no disponible"
    ;;
  logs)
    journalctl -u openclaw-dashboard -f --no-pager
    ;;
  logs-orch)
    tail -f /var/www/openclaw-multi-agents/logs/orchestrator.jsonl 2>/dev/null | \
      python3 -c "import sys,json
for line in sys.stdin:
    try:
        d=json.loads(line)
        print(f\"[{d.get('ts','?')[:19]}] [{d.get('agent','?'):6}] {d.get('msg','')}\"  )
    except: pass"
    ;;
  dry-run)
    BRIEF="${2:-Test dry-run}"
    cd /var/www/openclaw-multi-agents
    PYTHONPATH=/var/www/openclaw-multi-agents \
      python3 orchestrator.py --dry-run "$BRIEF"
    ;;
  automation-status)
    python3 - <<'PY2'
import json, subprocess
from pathlib import Path
config = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
token = config['gateway']['auth']['token']
url = f"ws://127.0.0.1:{config['gateway']['port']}"
out = subprocess.check_output([
    'openclaw', 'gateway', 'call', 'cron.list',
    '--json', '--url', url, '--token', token, '--params', '{}'
], text=True)
print(out)
PY2
    ;;
  automation-run-now)
    JOB_ID=$(python3 - <<'PY2'
import json, subprocess, sys
from pathlib import Path
config = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
token = config['gateway']['auth']['token']
url = f"ws://127.0.0.1:{config['gateway']['port']}"
out = subprocess.check_output([
    'openclaw', 'gateway', 'call', 'cron.list',
    '--json', '--url', url, '--token', token, '--params', '{}'
], text=True)
data = json.loads(out)
job = next((j for j in data.get('jobs', []) if j.get('name') == 'multiagent-phase-runner'), None)
print(job['id'] if job else '')
PY2
)
    if [ -z "$JOB_ID" ]; then
      echo "Cron job multiagent-phase-runner not found"
      exit 1
    fi
    openclaw cron run "$JOB_ID" --url ws://127.0.0.1:18789 --token "$(python3 - <<'PY2'
import json
from pathlib import Path
print(json.loads(Path('/root/.openclaw/openclaw.json').read_text())['gateway']['auth']['token'])
PY2
)"
    ;;
  automation-pause)
    JOB_ID=$(python3 - <<'PY2'
import json, subprocess, sys
from pathlib import Path
config = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
token = config['gateway']['auth']['token']
url = f"ws://127.0.0.1:{config['gateway']['port']}"
out = subprocess.check_output([
    'openclaw', 'gateway', 'call', 'cron.list',
    '--json', '--url', url, '--token', token, '--params', '{}'
], text=True)
data = json.loads(out)
job = next((j for j in data.get('jobs', []) if j.get('name') == 'multiagent-phase-runner'), None)
print(job['id'] if job else '')
PY2
)
    if [ -z "$JOB_ID" ]; then
      echo "Cron job multiagent-phase-runner not found"
      exit 1
    fi
    openclaw cron disable "$JOB_ID" --url ws://127.0.0.1:18789 --token "$(python3 - <<'PY2'
import json
from pathlib import Path
print(json.loads(Path('/root/.openclaw/openclaw.json').read_text())['gateway']['auth']['token'])
PY2
)"
    ;;
  automation-resume)
    JOB_ID=$(python3 - <<'PY2'
import json, subprocess, sys
from pathlib import Path
config = json.loads(Path('/root/.openclaw/openclaw.json').read_text())
token = config['gateway']['auth']['token']
url = f"ws://127.0.0.1:{config['gateway']['port']}"
out = subprocess.check_output([
    'openclaw', 'gateway', 'call', 'cron.list',
    '--json', '--url', url, '--token', token, '--params', '{}'
], text=True)
data = json.loads(out)
job = next((j for j in data.get('jobs', []) if j.get('name') == 'multiagent-phase-runner'), None)
print(job['id'] if job else '')
PY2
)
    if [ -z "$JOB_ID" ]; then
      echo "Cron job multiagent-phase-runner not found"
      exit 1
    fi
    openclaw cron enable "$JOB_ID" --url ws://127.0.0.1:18789 --token "$(python3 - <<'PY2'
import json
from pathlib import Path
print(json.loads(Path('/root/.openclaw/openclaw.json').read_text())['gateway']['auth']['token'])
PY2
)"
    ;;
  *)
    echo "Uso: $0 {start|stop|restart|status|logs|logs-orch|dry-run [brief]|automation-status|automation-run-now|automation-pause|automation-resume}"
    exit 1
    ;;
esac
