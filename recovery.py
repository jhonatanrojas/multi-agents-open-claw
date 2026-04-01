#!/usr/bin/env python3
"""
recovery.py - Startup recovery (F4.2)

Recover state on startup.
"""

from typing import List, Dict, Any
from persistence import get_db, RunRepository


def recover_active_runs() -> List[Dict[str, Any]]:
    """Recover active runs on startup."""
    db = next(get_db())
    repo = RunRepository(db)
    
    active = repo.get_active_runs()
    
    return [
        {
            "run_id": run.id,
            "project_id": run.project_id,
            "status": run.status,
        }
        for run in active
    ]


def startup_recovery() -> Dict[str, Any]:
    """Perform startup recovery."""
    active_runs = recover_active_runs()
    
    return {
        "recovered_runs": len(active_runs),
        "active_runs": active_runs,
    }


__all__ = ["startup_recovery", "recover_active_runs"]
