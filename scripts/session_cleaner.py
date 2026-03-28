#!/usr/bin/env python3
"""
session_cleaner.py - Limpia sesiones antiguas de agentes para evitar overflow de contexto

Uso:
    python session_cleaner.py --agent arch --max-size-kb 100
    python session_cleaner.py --all --max-size-kb 50
"""

import argparse
import os
import json
from pathlib import Path
from datetime import datetime

AGENTS_DIR = Path("/root/.openclaw/agents")
MAX_SESSION_SIZE_DEFAULT = 100  # KB


def get_session_files(agent_id: str) -> list[Path]:
    """Retorna lista de archivos de sesión para un agente."""
    sessions_dir = AGENTS_DIR / agent_id / "sessions"
    if not sessions_dir.exists():
        return []
    return list(sessions_dir.glob("*.jsonl"))


def get_session_size_kb(session_file: Path) -> float:
    """Retorna el tamaño del archivo en KB."""
    return session_file.stat().st_size / 1024


def clean_session(session_file: Path, max_size_kb: float, dry_run: bool = False) -> dict:
    """
    Limpia una sesión si excede el tamaño máximo.
    Retorna un dict con el resultado de la operación.
    """
    size_kb = get_session_size_kb(session_file)
    
    if size_kb <= max_size_kb:
        return {
            "file": str(session_file),
            "size_kb": size_kb,
            "action": "skipped",
            "reason": f"below threshold ({size_kb:.1f}KB <= {max_size_kb}KB)"
        }
    
    action = "would_delete" if dry_run else "deleted"
    
    if not dry_run:
        # Crear backup mínimo (solo metadata)
        backup = {
            "original_file": str(session_file),
            "original_size_kb": size_kb,
            "cleaned_at": datetime.utcnow().isoformat(),
            "reason": "context_overflow_prevention"
        }
        backup_file = session_file.with_suffix(".cleaned.json")
        with open(backup_file, "w") as f:
            json.dump(backup, f, indent=2)
        
        # Eliminar el archivo de sesión grande
        session_file.unlink()
        
        # También eliminar el archivo de lock si existe
        lock_file = session_file.with_suffix(".jsonl.lock")
        if lock_file.exists():
            lock_file.unlink()
    
    return {
        "file": str(session_file),
        "size_kb": size_kb,
        "action": action,
        "reason": f"exceeded threshold ({size_kb:.1f}KB > {max_size_kb}KB)"
    }


def clean_agent_sessions(agent_id: str, max_size_kb: float, dry_run: bool = False) -> list[dict]:
    """Limpia todas las sesiones de un agente."""
    results = []
    for session_file in get_session_files(agent_id):
        result = clean_session(session_file, max_size_kb, dry_run)
        results.append(result)
    return results


def clean_all_agents(max_size_kb: float, dry_run: bool = False) -> dict:
    """Limpia sesiones de todos los agentes."""
    all_results = {}
    for agent_dir in AGENTS_DIR.iterdir():
        if agent_dir.is_dir() and (agent_dir / "sessions").exists():
            agent_id = agent_dir.name
            results = clean_agent_sessions(agent_id, max_size_kb, dry_run)
            all_results[agent_id] = results
    return all_results


def main():
    parser = argparse.ArgumentParser(description="Limpia sesiones antiguas de agentes")
    parser.add_argument("--agent", help="ID del agente (ej: arch, byte, pixel)")
    parser.add_argument("--all", action="store_true", help="Limpiar todos los agentes")
    parser.add_argument("--max-size-kb", type=float, default=MAX_SESSION_SIZE_DEFAULT,
                        help=f"Tamaño máximo en KB (default: {MAX_SESSION_SIZE_DEFAULT})")
    parser.add_argument("--dry-run", action="store_true", help="Solo mostrar qué se haría")
    
    args = parser.parse_args()
    
    if args.all:
        results = clean_all_agents(args.max_size_kb, args.dry_run)
        for agent_id, agent_results in results.items():
            print(f"\n=== {agent_id} ===")
            for r in agent_results:
                print(f"  {r['file']}: {r['size_kb']:.1f}KB - {r['action']} ({r['reason']})")
    elif args.agent:
        results = clean_agent_sessions(args.agent, args.max_size_kb, args.dry_run)
        print(f"\n=== {args.agent} ===")
        for r in results:
            print(f"  {r['file']}: {r['size_kb']:.1f}KB - {r['action']} ({r['reason']})")
    else:
        parser.error("Especifica --agent <id> o --all")


if __name__ == "__main__":
    main()
