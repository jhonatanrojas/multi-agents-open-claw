"""Files router - handles file viewing and listing."""

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import Any

router = APIRouter(prefix="/api/files", tags=["files"])


def _resolve_output_dir(project: dict[str, Any]) -> Path:
    """Resolve output directory for a project."""
    output_dir = str(project.get("output_dir") or "output").strip()
    candidate = Path(output_dir).expanduser()
    if candidate.is_absolute():
        return candidate
    from shared_state import BASE_DIR
    return (BASE_DIR / candidate).resolve()


def _load_manifest_file_paths(project: dict[str, Any]) -> list[str]:
    """Load file paths from project manifest."""
    output_dir = _resolve_output_dir(project)
    manifest_path = output_dir / "PROJECT_MANIFEST.json"
    
    if not manifest_path.exists():
        return []
    
    try:
        import json
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files", [])
        return [str(f) for f in files if isinstance(f, str)]
    except Exception:
        return []


@router.get("/view")
def get_file_view(path: str = Query(..., description="File path to view")):
    """Return file content for preview (live or archived)."""
    try:
        from shared_state import load_memory
        from dashboard_api import _build_file_view_response
        
        mem = load_memory()
        requested_path = str(path or "").strip()
        
        if not requested_path:
            return JSONResponse(
                {"error": "path es obligatorio"},
                status_code=422
            )
        
        file_view = _build_file_view_response(mem, requested_path)
        if not file_view:
            return JSONResponse(
                {"error": f"Archivo no encontrado: {requested_path}"},
                status_code=404,
            )
        
        return {"file": file_view}
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )


@router.get("")
def get_files():
    """Return file listings for all projects with manifest file counts."""
    try:
        from shared_state import load_memory, BASE_DIR
        
        mem = load_memory()
        project = mem.get("project", {}) if isinstance(mem.get("project"), dict) else {}
        
        current_files = [
            str(path).strip()
            for path in (mem.get("files_produced", []) if isinstance(mem.get("files_produced", []), list) else [])
            if isinstance(path, str) and path.strip()
        ]
        progress_files = [
            str(path).strip()
            for path in (mem.get("progress_files", []) if isinstance(mem.get("progress_files", []), list) else [])
            if isinstance(path, str) and path.strip()
        ]
        
        produced = list(dict.fromkeys(current_files + progress_files))
        if not produced:
            produced = _load_manifest_file_paths(project)
        
        # Build project entries
        project_entries: list[dict[str, Any]] = []
        seen_project_ids: set[str] = set()
        
        for project_entry in (mem.get("projects", []) if isinstance(mem.get("projects", []), list) else []):
            if not isinstance(project_entry, dict):
                continue
            project_id = str(project_entry.get("id") or "").strip()
            if project_id and project_id in seen_project_ids:
                continue
            
            project_output_dir = _resolve_output_dir(project_entry)
            manifest_path = project_output_dir / "PROJECT_MANIFEST.json"
            file_count = 0
            
            if manifest_path.exists():
                try:
                    import json
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    file_count = len(manifest.get("files", [])) if isinstance(manifest.get("files", []), list) else 0
                except Exception:
                    file_count = 0
            
            project_entries.append({
                "id": project_entry.get("id"),
                "name": project_entry.get("name"),
                "status": project_entry.get("status"),
                "roots": [],
                "total_files": file_count,
            })
            
            if project_id:
                seen_project_ids.add(project_id)
        
        # Add current project if not already in list
        if project and project.get("id"):
            current_project_id = str(project.get("id") or "").strip()
            if current_project_id not in seen_project_ids:
                project_output_dir = _resolve_output_dir(project)
                manifest_path = project_output_dir / "PROJECT_MANIFEST.json"
                file_count = len(produced)
                
                if manifest_path.exists():
                    try:
                        import json
                        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                        if isinstance(manifest.get("files", []), list) and manifest.get("files"):
                            file_count = len(manifest.get("files", []))
                    except Exception:
                        pass
                
                project_entries.append({
                    "id": project.get("id"),
                    "name": project.get("name"),
                    "status": project.get("status"),
                    "roots": [],
                    "total_files": file_count,
                })
        
        return {
            "projects": project_entries,
            "files_produced": produced,
            "progress_files": progress_files,
        }
    except Exception as e:
        return JSONResponse(
            {"ok": False, "error": str(e)},
            status_code=500
        )
