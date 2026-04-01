"""
models.py - SQLAlchemy models for database persistence (F1.2)
"""

from sqlalchemy import Column, String, DateTime, Text, ForeignKey, Index
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from persistence.database import Base


class Run(Base):
    """
    Run model - stores run execution state.
    
    This replaces MEMORY.json as the source of truth for run state.
    """
    __tablename__ = "runs"
    
    id = Column(String(32), primary_key=True, index=True)
    project_id = Column(String(32), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="planning")
    current_phase = Column(String(50), nullable=True)
    current_agent = Column(String(20), nullable=True)
    plan_version = Column(String(10), default="1")
    context_json = Column(Text, nullable=False, default="{}")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    tasks = relationship("Task", back_populates="run", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="run", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Run(id={self.id}, project_id={self.project_id}, status={self.status})>"


class Task(Base):
    """
    Task model - stores individual task execution state.
    """
    __tablename__ = "tasks"
    
    id = Column(String(32), primary_key=True, index=True)
    run_id = Column(String(32), ForeignKey("runs.id"), nullable=False, index=True)
    agent = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    description = Column(Text, nullable=True)
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    run = relationship("Run", back_populates="tasks")
    events = relationship("Event", back_populates="task", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Task(id={self.id}, run_id={self.run_id}, agent={self.agent}, status={self.status})>"


class Event(Base):
    """
    Event model - append-only event log for observability.
    
    Prepared for F3.2 (Event Log persistent).
    """
    __tablename__ = "events"
    
    id = Column(String(32), primary_key=True, index=True)
    run_id = Column(String(32), ForeignKey("runs.id"), nullable=False, index=True)
    task_id = Column(String(32), ForeignKey("tasks.id"), nullable=True, index=True)
    event_type = Column(String(50), nullable=False, index=True)
    agent = Column(String(20), nullable=True)
    payload_json = Column(Text, nullable=False, default="{}")
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Relationships
    run = relationship("Run", back_populates="events")
    task = relationship("Task", back_populates="events")
    
    def __repr__(self):
        return f"<Event(id={self.id}, type={self.event_type}, run_id={self.run_id})>"
    
    # Indexes for common queries
    __table_args__ = (
        Index('idx_events_run_created', 'run_id', 'created_at'),
        Index('idx_events_type_created', 'event_type', 'created_at'),
    )
