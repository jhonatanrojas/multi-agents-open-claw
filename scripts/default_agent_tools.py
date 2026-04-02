import requests

DASHBOARD_API = "http://localhost:8000"
API_KEY = "" # Add DASHBOARD_API_KEY if configured

def get_headers():
    if API_KEY:
        return {"X-API-Key": API_KEY}
    return {}

def check_orchestrator_state():
    """Fetches the current state of the orchestrator to see what it is doing."""
    response = requests.get(f"{DASHBOARD_API}/api/state", headers=get_headers())
    return response.json()

def force_restart_processes():
    """Stops the orchestrator and allows it to restart."""
    response = requests.post(f"{DASHBOARD_API}/api/project/restart", headers=get_headers())
    return response.json()

def report_multiagent_failure_telegram(message: str):
    """Sends a Telegram alert if the multi-agents fail."""
    response = requests.post(
        f"{DASHBOARD_API}/api/alerts/telegram", 
        json={"message": message},
        headers=get_headers()
    )
    return response.json()

def message_coordinator(content: str):
    """Sends a direct hierarchical message to the coordinator via the new routing."""
    # Miniverse bridge uses its logic, but we can POST directly if we are local CLI
    # In OpenClaw default agent, this could just write an intent file or use Miniverse /api/act
    payload = {
        "agent": "openclaw_default",
        "action": {
            "type": "message",
            "to": "arch", 
            "message": content,
            "from_route": "/root/openclaw/main",
            "to_route": "/root/worker/arch"
        }
    }
    # MINIVERSE_URL
    miniverse_url = "http://127.0.0.1:9999"
    try:
        r = requests.post(f"{miniverse_url}/api/act", json=payload)
        return {"ok": r.ok}
    except Exception as e:
        return {"ok": False, "error": str(e)}
