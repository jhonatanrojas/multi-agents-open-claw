#!/usr/bin/env python3
"""
health.py - Enhanced health check utilities (F0.8)

This module provides comprehensive health monitoring for the OpenClaw
Multi-Agent Dashboard, including:
- Service connectivity checks
- Cache status
- Version information
- Uptime tracking
"""

import time
import socket
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# Track start time
_START_TIME = time.time()
VERSION = "2.0.0-f0.8"


def check_gateway_connectivity(host: str, port: int, timeout: float = 2.0) -> dict[str, Any]:
    """
    Check if the OpenClaw Gateway is reachable.
    
    Args:
        host: Gateway host
        port: Gateway port
        timeout: Connection timeout in seconds
    
    Returns:
        Dict with connection status
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return {
            "host": host,
            "port": port,
            "connected": result == 0,
            "latency_ms": None  # Could add timing if needed
        }
    except Exception as e:
        return {
            "host": host,
            "port": port,
            "connected": False,
            "error": str(e)[:100]
        }


def check_miniverse_connectivity(url: str, timeout: float = 2.0) -> dict[str, Any]:
    """
    Check if Miniverse is reachable.
    
    Args:
        url: Miniverse base URL
        timeout: Request timeout in seconds
    
    Returns:
        Dict with connection status
    """
    try:
        import requests
        resp = requests.get(f"{url}/health", timeout=timeout)
        return {
            "url": url,
            "connected": resp.status_code == 200,
            "status_code": resp.status_code
        }
    except Exception as e:
        return {
            "url": url,
            "connected": False,
            "error": str(e)[:100]
        }


def check_model_cache_status(cache_path: Path | None, ttl: int) -> dict[str, Any]:
    """
    Check model status cache health.
    
    Args:
        cache_path: Path to cache file
        ttl: Expected cache TTL in seconds
    
    Returns:
        Dict with cache status
    """
    if not cache_path:
        return {"exists": False, "configured": False}
    
    if not cache_path.exists():
        return {"exists": False, "configured": True, "path": str(cache_path)}
    
    try:
        cache_stat = cache_path.stat()
        cache_age = time.time() - cache_stat.st_mtime
        return {
            "path": str(cache_path),
            "exists": True,
            "size_bytes": cache_stat.st_size,
            "age_seconds": int(cache_age),
            "fresh": cache_age < ttl,
            "ttl_seconds": ttl
        }
    except Exception as e:
        return {
            "path": str(cache_path),
            "exists": True,
            "error": str(e)[:100]
        }


def check_memory_health(memory_path: Path) -> dict[str, Any]:
    """
    Check memory file health.
    
    Args:
        memory_path: Path to MEMORY.json
    
    Returns:
        Dict with memory status
    """
    if not memory_path.exists():
        return {"exists": False, "path": str(memory_path)}
    
    try:
        import json
        memory_stat = memory_path.stat()
        content = json.loads(memory_path.read_text(encoding="utf-8"))
        return {
            "path": str(memory_path),
            "exists": True,
            "size_bytes": memory_stat.st_size,
            "schema_version": content.get("schema_version", "unknown"),
            "has_active_project": bool(content.get("active_project_id")),
            "task_count": len(content.get("tasks", [])),
            "updated_at": content.get("updated_at")
        }
    except Exception as e:
        return {
            "path": str(memory_path),
            "exists": True,
            "error": str(e)[:100]
        }


def build_enhanced_health_snapshot(
    config,
    memory_path: Path,
    lock_file: Path,
    orchestrator_state: dict[str, Any],
    auth_enabled: bool = False
) -> dict[str, Any]:
    """
    Build comprehensive health snapshot for monitoring.
    
    Args:
        config: Configuration object
        memory_path: Path to MEMORY.json
        lock_file: Path to orchestrator lock file
        orchestrator_state: Current orchestrator state
        auth_enabled: Whether authentication is enabled
    
    Returns:
        Dict with comprehensive health information
    """
    import time as time_module
    from datetime import datetime, timezone
    
    issues: list[str] = []
    services: dict[str, Any] = {}
    
    # Check lock file
    lock_state: dict[str, Any] = {"exists": lock_file.exists(), "pid": None, "alive": False}
    if lock_file.exists():
        try:
            import json
            lock_payload = json.loads(lock_file.read_text(encoding="utf-8"))
            lock_state["pid"] = lock_payload.get("pid")
            # Check if process is alive
            if lock_state["pid"]:
                try:
                    import os
                    import signal
                    os.kill(lock_state["pid"], 0)
                    lock_state["alive"] = True
                except (OSError, ProcessLookupError):
                    lock_state["alive"] = False
            lock_state["started_at"] = lock_payload.get("started_at")
        except Exception:
            pass
    
    if lock_state["exists"] and not lock_state["alive"] and lock_state["pid"] is not None:
        issues.append("lockfile obsoleto")
    
    if orchestrator_state.get("status") == "error":
        issues.append("error del orquestador")
    
    # Check Gateway connectivity
    services["gateway"] = check_gateway_connectivity(
        config.OPENCLAW_GATEWAY_HOST,
        config.OPENCLAW_GATEWAY_PORT
    )
    if not services["gateway"]["connected"]:
        issues.append("gateway no disponible")
    
    # Check Miniverse if enabled
    if config.MINIVERSE_ENABLED:
        services["miniverse"] = check_miniverse_connectivity(config.MINIVERSE_URL)
        if not services["miniverse"]["connected"]:
            issues.append("miniverse no disponible")
    
    # Check model cache
    services["model_cache"] = check_model_cache_status(
        config.MODEL_STATUS_CACHE_PATH,
        config.MODEL_STATUS_CACHE_TTL
    )
    
    # Check memory
    services["memory"] = check_memory_health(memory_path)
    
    # Determine overall health
    ok = len(issues) == 0 and all(
        s.get("connected", True) or s.get("fresh", True)
        for s in services.values()
        if isinstance(s, dict) and "connected" in s or "fresh" in s
    )
    
    return {
        "ok": ok,
        "service": "dashboard_api",
        "version": VERSION,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": int(time_module.time() - _START_TIME),
        "lockfile": lock_state,
        "orchestrator": orchestrator_state,
        "services": services,
        "issues": issues,
        "auth_enabled": auth_enabled,
        "config": {
            "runtime_profile": config.OPENCLAW_PROFILE,
            "miniverse_enabled": config.MINIVERSE_ENABLED,
        }
    }


__all__ = [
    "VERSION",
    "check_gateway_connectivity",
    "check_miniverse_connectivity",
    "check_model_cache_status",
    "check_memory_health",
    "build_enhanced_health_snapshot",
]
