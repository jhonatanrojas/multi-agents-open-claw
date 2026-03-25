#!/usr/bin/env bash
set -euo pipefail

ORCHESTRATOR_SERVICE="openclaw-multiagent"
DASHBOARD_SERVICE="openclaw-dashboard"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ORCHESTRATOR_UNIT_SRC="$ROOT_DIR/deploy/systemd/${ORCHESTRATOR_SERVICE}.service"
DASHBOARD_UNIT_SRC="$ROOT_DIR/deploy/systemd/${DASHBOARD_SERVICE}.service"
ORCHESTRATOR_UNIT_DST="/etc/systemd/system/${ORCHESTRATOR_SERVICE}.service"
DASHBOARD_UNIT_DST="/etc/systemd/system/${DASHBOARD_SERVICE}.service"
ENV_DST="/etc/default/openclaw-multiagent"

if [[ "${1:-}" != "" ]]; then
  ROOT_DIR="$1"
  UNIT_SRC="$ROOT_DIR/deploy/systemd/${SERVICE_NAME}.service"
fi

if [[ ! -f "$ORCHESTRATOR_UNIT_SRC" ]]; then
  echo "No se encontro el archivo de servicio: $ORCHESTRATOR_UNIT_SRC" >&2
  exit 1
fi

if [[ ! -f "$DASHBOARD_UNIT_SRC" ]]; then
  echo "No se encontro el archivo de servicio: $DASHBOARD_UNIT_SRC" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Ejecuta este script como root o con sudo." >&2
  exit 1
fi

install -Dm644 "$ORCHESTRATOR_UNIT_SRC" "$ORCHESTRATOR_UNIT_DST"
install -Dm644 "$DASHBOARD_UNIT_SRC" "$DASHBOARD_UNIT_DST"

if [[ ! -f "$ENV_DST" ]]; then
  cat >"$ENV_DST" <<'EOF'
# Configuracion opcional para OpenClaw Multi-Agent
# OPENCLAW_HEALTH_URL=http://127.0.0.1:8001/health
# TELEGRAM_BOT_TOKEN=...
# TELEGRAM_CHAT_ID=...
# MINIVERSE_URL=https://miniverse-public-production.up.railway.app
EOF
  chmod 600 "$ENV_DST"
fi

systemctl daemon-reload
systemctl enable "$ORCHESTRATOR_SERVICE"
systemctl enable "$DASHBOARD_SERVICE"

echo "Servicios instalados:"
echo "- $ORCHESTRATOR_UNIT_DST"
echo "- $DASHBOARD_UNIT_DST"
echo "Activalos con:"
echo "  systemctl start $ORCHESTRATOR_SERVICE"
echo "  systemctl start $DASHBOARD_SERVICE"
echo "Consulta estado con:"
echo "  systemctl status $ORCHESTRATOR_SERVICE --no-pager"
echo "  systemctl status $DASHBOARD_SERVICE --no-pager"
