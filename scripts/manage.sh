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
  *)
    echo "Uso: $0 {start|stop|restart|status|logs|logs-orch|dry-run [brief]}"
    exit 1
    ;;
esac
