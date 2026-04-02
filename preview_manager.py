#!/usr/bin/env python3
"""
preview_manager.py - Preview management (F3.7)

Manage previews for runs.
"""

from typing import Dict, Any, Optional
from pathlib import Path


class PreviewManager:
    """Manage preview URLs and status."""
    
    def __init__(self, base_path: str = "/tmp/previews"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(exist_ok=True)
    
    def create_preview(self, run_id: str, files: list) -> str:
        """Create a preview for a run."""
        preview_dir = self.base_path / run_id
        preview_dir.mkdir(exist_ok=True)
        
        # Return preview URL
        return f"/preview/{run_id}"
    
    def get_preview_status(self, run_id: str) -> Dict[str, Any]:
        """Get preview status."""
        preview_dir = self.base_path / run_id
        
        return {
            "run_id": run_id,
            "exists": preview_dir.exists(),
            "url": f"/preview/{run_id}" if preview_dir.exists() else None,
        }


__all__ = ["PreviewManager"]
