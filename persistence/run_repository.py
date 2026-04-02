"""
run_repository.py - Repository pattern for Run CRUD operations (F1.2)
"""

import json
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from persistence.models import Run


class RunRepository:
    """
    Repository for Run database operations.
    
    Provides CRUD operations and query methods for Run entities.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_id(self) -> str:
        """Generate unique run ID."""
        return f"run-{uuid.uuid4().hex[:12]}"
    
    def create_run(
        self,
        project_id: str,
        status: str = "planning",
        current_phase: Optional[str] = None,
        current_agent: Optional[str] = None,
        context_json: str = "{}"
    ) -> Run:
        """
        Create a new run.
        
        Returns:
            Created Run instance
        """
        db_run = Run(
            id=self.generate_id(),
            project_id=project_id,
            status=status,
            current_phase=current_phase,
            current_agent=current_agent,
            context_json=context_json,
        )
        self.db.add(db_run)
        self.db.commit()
        self.db.refresh(db_run)
        return db_run
    
    def get_run(self, run_id: str) -> Optional[Run]:
        """Get run by ID."""
        return self.db.query(Run).filter(Run.id == run_id).first()
    
    def get_run_by_project(self, project_id: str) -> Optional[Run]:
        """Get most recent run for a project."""
        return (
            self.db.query(Run)
            .filter(Run.project_id == project_id)
            .order_by(desc(Run.created_at))
            .first()
        )
    
    def list_runs(
        self,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Run]:
        """
        List runs with optional filtering.
        
        Args:
            status: Filter by status
            project_id: Filter by project
            limit: Maximum results
            offset: Pagination offset
        
        Returns:
            List of Run instances
        """
        query = self.db.query(Run)
        
        if status:
            query = query.filter(Run.status == status)
        if project_id:
            query = query.filter(Run.project_id == project_id)
        
        return (
            query.order_by(desc(Run.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
    
    def update_run(
        self,
        run_id: str,
        status: Optional[str] = None,
        current_phase: Optional[str] = None,
        current_agent: Optional[str] = None,
        context_json: Optional[str] = None,
    ) -> Optional[Run]:
        """
        Update run fields.
        
        Returns:
            Updated Run or None if not found
        """
        db_run = self.get_run(run_id)
        if not db_run:
            return None
        
        if status is not None:
            db_run.status = status
        if current_phase is not None:
            db_run.current_phase = current_phase
        if current_agent is not None:
            db_run.current_agent = current_agent
        if context_json is not None:
            db_run.context_json = context_json
        
        db_run.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(db_run)
        return db_run
    
    def delete_run(self, run_id: str) -> bool:
        """
        Delete a run.
        
        Returns:
            True if deleted, False if not found
        """
        db_run = self.get_run(run_id)
        if not db_run:
            return False
        
        self.db.delete(db_run)
        self.db.commit()
        return True
    
    def get_active_runs(self) -> List[Run]:
        """Get all active (non-completed, non-failed) runs."""
        return (
            self.db.query(Run)
            .filter(Run.status.in_(["planning", "executing", "blocked", "paused"]))
            .order_by(desc(Run.created_at))
            .all()
        )
    
    def count_runs(self, status: Optional[str] = None) -> int:
        """Count runs, optionally filtered by status."""
        query = self.db.query(Run)
        if status:
            query = query.filter(Run.status == status)
        return query.count()
