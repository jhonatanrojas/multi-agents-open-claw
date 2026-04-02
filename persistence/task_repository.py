"""
task_repository.py - Repository pattern for Task CRUD operations (F1.2)
"""

import json
import uuid
from datetime import datetime
from typing import Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import desc

from persistence.models import Task


class TaskRepository:
    """
    Repository for Task database operations.
    
    Provides CRUD operations and query methods for Task entities.
    """
    
    def __init__(self, db: Session):
        self.db = db
    
    def generate_id(self) -> str:
        """Generate unique task ID."""
        return f"task-{uuid.uuid4().hex[:12]}"
    
    def create_task(
        self,
        run_id: str,
        agent: str,
        description: str,
        status: str = "pending",
        input_data: Optional[dict] = None,
    ) -> Task:
        """
        Create a new task.
        
        Returns:
            Created Task instance
        """
        db_task = Task(
            id=self.generate_id(),
            run_id=run_id,
            agent=agent,
            description=description,
            status=status,
            input_json=json.dumps(input_data) if input_data else None,
        )
        self.db.add(db_task)
        self.db.commit()
        self.db.refresh(db_task)
        return db_task
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task by ID."""
        return self.db.query(Task).filter(Task.id == task_id).first()
    
    def list_tasks(
        self,
        run_id: Optional[str] = None,
        agent: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[Task]:
        """
        List tasks with optional filtering.
        
        Returns:
            List of Task instances
        """
        query = self.db.query(Task)
        
        if run_id:
            query = query.filter(Task.run_id == run_id)
        if agent:
            query = query.filter(Task.agent == agent)
        if status:
            query = query.filter(Task.status == status)
        
        return (
            query.order_by(desc(Task.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )
    
    def update_task(
        self,
        task_id: str,
        status: Optional[str] = None,
        output_data: Optional[dict] = None,
    ) -> Optional[Task]:
        """
        Update task fields.
        
        Returns:
            Updated Task or None if not found
        """
        db_task = self.get_task(task_id)
        if not db_task:
            return None
        
        if status is not None:
            db_task.status = status
            if status in ["completed", "failed"]:
                db_task.completed_at = datetime.utcnow()
        
        if output_data is not None:
            db_task.output_json = json.dumps(output_data)
        
        db_task.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(db_task)
        return db_task
    
    def delete_task(self, task_id: str) -> bool:
        """
        Delete a task.
        
        Returns:
            True if deleted, False if not found
        """
        db_task = self.get_task(task_id)
        if not db_task:
            return False
        
        self.db.delete(db_task)
        self.db.commit()
        return True
    
    def get_tasks_for_run(self, run_id: str) -> List[Task]:
        """Get all tasks for a specific run."""
        return (
            self.db.query(Task)
            .filter(Task.run_id == run_id)
            .order_by(desc(Task.created_at))
            .all()
        )
    
    def count_tasks(self, run_id: Optional[str] = None, status: Optional[str] = None) -> int:
        """Count tasks with optional filtering."""
        query = self.db.query(Task)
        if run_id:
            query = query.filter(Task.run_id == run_id)
        if status:
            query = query.filter(Task.status == status)
        return query.count()
