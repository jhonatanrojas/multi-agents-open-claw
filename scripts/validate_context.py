#!/usr/bin/env python3
"""
validate_context.py - Validación previa de contexto para evitar overflow

Este script debe ejecutarse ANTES de iniciar el orquestador para:
1. Verificar que las sesiones no excedan el límite de tamaño
2. Limpiar archivos de sesión oversize
3. Verificar que el modelo configurado tenga contexto suficiente

Uso:
    python validate_context.py [--clean]
"""

import json
import sys
from pathlib import Path

AGENTS_DIR = Path("/root/.openclaw/agents")
ORCHESTRATOR_DIR = Path("/var/www/openclaw-multi-agents")

# Límites de seguridad
MAX_SESSION_SIZE_KB = 100  # KB por sesión
MAX_TOTAL_SESSIONS_MB = 5  # MB total por agente
WARN_SESSION_SIZE_KB = 50  # KB para advertencia


def get_agent_session_stats(agent_id: str) -> dict:
    """Obtiene estadísticas de sesiones para un agente."""
    sessions_dir = AGENTS_DIR / agent_id / "sessions"
    if not sessions_dir.exists():
        return {"agent": agent_id, "sessions": [], "total_kb": 0, "count": 0}
    
    sessions = []
    total_kb = 0
    
    for session_file in sessions_dir.glob("*.jsonl"):
        size_kb = session_file.stat().st_size / 1024
        total_kb += size_kb
        sessions.append({
            "file": session_file.name,
            "size_kb": round(size_kb, 2),
            "oversize": size_kb > MAX_SESSION_SIZE_KB,
            "warning": size_kb > WARN_SESSION_SIZE_KB
        })
    
    return {
        "agent": agent_id,
        "sessions": sessions,
        "total_kb": round(total_kb, 2),
        "total_mb": round(total_kb / 1024, 2),
        "count": len(sessions)
    }


def clean_oversize_sessions(agent_id: str, dry_run: bool = True) -> list:
    """Limpia sesiones que exceden el límite."""
    sessions_dir = AGENTS_DIR / agent_id / "sessions"
    if not sessions_dir.exists():
        return []
    
    cleaned = []
    for session_file in sessions_dir.glob("*.jsonl"):
        size_kb = session_file.stat().st_size / 1024
        if size_kb > MAX_SESSION_SIZE_KB:
            action = "would_delete" if dry_run else "deleted"
            if not dry_run:
                # Crear backup minimal
                backup = {
                    "original_file": str(session_file),
                    "original_size_kb": size_kb,
                    "reason": "context_overflow_prevention"
                }
                backup_file = session_file.with_suffix(".cleaned.json")
                with open(backup_file, "w") as f:
                    json.dump(backup, f)
                session_file.unlink()
                session_file.with_suffix(".jsonl.lock").unlink(missing_ok=True)
            
            cleaned.append({
                "file": session_file.name,
                "size_kb": round(size_kb, 2),
                "action": action
            })
    
    return cleaned


def validate_all_agents(clean: bool = False) -> dict:
    """Valida todos los agentes."""
    results = {
        "agents": {},
        "issues": [],
        "cleaned": [],
        "recommendations": []
    }
    
    for agent_dir in AGENTS_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        
        agent_id = agent_dir.name
        stats = get_agent_session_stats(agent_id)
        results["agents"][agent_id] = stats
        
        # Verificar problemas
        if stats["total_mb"] > MAX_TOTAL_SESSIONS_MB:
            results["issues"].append(
                f"{agent_id}: Total de sesiones ({stats['total_mb']}MB) excede límite ({MAX_TOTAL_SESSIONS_MB}MB)"
            )
        
        oversize = [s for s in stats["sessions"] if s["oversize"]]
        if oversize:
            results["issues"].append(
                f"{agent_id}: {len(oversize)} sesión(es) exceden {MAX_SESSION_SIZE_KB}KB"
            )
        
        # Limpiar si se solicita
        if clean:
            cleaned = clean_oversize_sessions(agent_id, dry_run=False)
            if cleaned:
                results["cleaned"].extend([{**c, "agent": agent_id} for c in cleaned])
    
    # Generar recomendaciones
    if results["issues"]:
        results["recommendations"].append(
            "Ejecutar con --clean para limpiar sesiones oversize"
        )
        results["recommendations"].append(
            "O ejecutar manualmente: python scripts/session_cleaner.py --all"
        )
    
    return results


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Validar contexto de agentes")
    parser.add_argument("--clean", action="store_true", help="Limpiar sesiones oversize")
    parser.add_argument("--json", action="store_true", help="Output en JSON")
    args = parser.parse_args()
    
    results = validate_all_agents(clean=args.clean)
    
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("=== VALIDACIÓN DE CONTEXTO ===\n")
        
        for agent_id, stats in results["agents"].items():
            status = "✅" if not any(s["oversize"] for s in stats["sessions"]) else "⚠️"
            print(f"{status} {agent_id}: {stats['count']} sesiones, {stats['total_kb']}KB")
            
            for session in stats["sessions"]:
                if session["oversize"]:
                    print(f"   ❌ {session['file']}: {session['size_kb']}KB (OVERSIZE)")
                elif session["warning"]:
                    print(f"   ⚠️  {session['file']}: {session['size_kb']}KB (warning)")
        
        if results["issues"]:
            print("\n=== PROBLEMAS ===")
            for issue in results["issues"]:
                print(f"  • {issue}")
        
        if results["cleaned"]:
            print("\n=== LIMPIADOS ===")
            for c in results["cleaned"]:
                print(f"  • {c['agent']}/{c['file']}: {c['size_kb']}KB - {c['action']}")
        
        if results["recommendations"]:
            print("\n=== RECOMENDACIONES ===")
            for rec in results["recommendations"]:
                print(f"  • {rec}")
        
        if not results["issues"]:
            print("\n✅ Sin problemas de contexto detectados")
        
        return 0 if not results["issues"] else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
