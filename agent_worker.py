#!/usr/bin/env python3
"""
agent_worker.py - Agents as pure workers (F2.4)

Agents receive tasks and return results. No state management.
All orchestration is handled by the supervisor.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from dataclasses import dataclass

from task_entity import TaskEntity, TaskStatus
from action_envelope import ActionEnvelope, ActionType, parse_action


@dataclass
class WorkerResult:
    """Result from agent worker execution."""
    success: bool
    output: Dict[str, Any]
    artifacts: Optional[list] = None
    error: Optional[str] = None


class AgentWorker(ABC):
    """
    Abstract base class for agent workers.
    
    Agents are pure workers - they receive tasks and return results.
    They don't manage state or make orchestration decisions.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.tasks_processed = 0
        self.tasks_failed = 0
    
    @abstractmethod
    def execute(self, task: TaskEntity) -> WorkerResult:
        """
        Execute a task.
        
        Args:
            task: Task entity to execute
        
        Returns:
            WorkerResult with success/failure and output
        """
        pass
    
    def process_task(self, task: TaskEntity) -> ActionEnvelope:
        """
        Process a task and return an action envelope.
        
        This is the main entry point for task execution.
        
        Args:
            task: Task entity to process
        
        Returns:
            ActionEnvelope with results
        """
        try:
            # Mark task as started
            task.start()
            
            # Execute task
            result = self.execute(task)
            
            if result.success:
                # Mark task as completed
                task.complete(result.output, result.artifacts or [])
                self.tasks_processed += 1
                
                return ActionEnvelope(
                    action=ActionType.COMPLETE,
                    payload=result.output,
                    reasoning=f"Task completed by {self.agent_id}",
                )
            else:
                # Mark task as failed
                task.fail(result.error or "Unknown error")
                self.tasks_failed += 1
                
                return ActionEnvelope(
                    action=ActionType.ERROR,
                    payload={"error": result.error, "task_id": task.task_id},
                    reasoning=f"Task failed: {result.error}",
                )
        
        except Exception as e:
            # Handle unexpected errors
            task.fail(str(e))
            self.tasks_failed += 1
            
            return ActionEnvelope(
                action=ActionType.ERROR,
                payload={"error": str(e), "task_id": task.task_id},
                reasoning=f"Unexpected error in {self.agent_id}: {str(e)}",
            )


class ArchWorker(AgentWorker):
    """Architecture agent worker."""
    
    def __init__(self):
        super().__init__("arch")
    
    def execute(self, task: TaskEntity) -> WorkerResult:
        """Execute architecture task."""
        # Simulate architecture work
        return WorkerResult(
            success=True,
            output={
                "design": f"Architecture design for: {task.description}",
                "components": ["component1", "component2"],
            },
        )


class ByteWorker(AgentWorker):
    """Implementation agent worker."""
    
    def __init__(self):
        super().__init__("byte")
    
    def execute(self, task: TaskEntity) -> WorkerResult:
        """Execute implementation task."""
        # Simulate coding work
        return WorkerResult(
            success=True,
            output={
                "code": f"# Implementation for: {task.description}",
                "files_created": ["file1.py", "file2.py"],
            },
            artifacts=["file1.py", "file2.py"],
        )


class PixelWorker(AgentWorker):
    """Review agent worker."""
    
    def __init__(self):
        super().__init__("pixel")
    
    def execute(self, task: TaskEntity) -> WorkerResult:
        """Execute review task."""
        # Simulate review work
        return WorkerResult(
            success=True,
            output={
                "review": f"Quality review for: {task.description}",
                "score": 0.95,
                "issues": [],
            },
        )


class JudgeWorker(AgentWorker):
    """
    JUDGE agent worker.
    
    Reviews and validates work from other agents.
    Has veto power over task completion.
    """
    
    def __init__(self):
        super().__init__("judge")
    
    def execute(self, task: TaskEntity) -> WorkerResult:
        """Execute judgment task."""
        # Review the work
        input_data = task.input_data or {}
        work_to_review = input_data.get("work", {})
        
        # Simulate judgment
        quality_score = 0.90  # Would be calculated from actual work
        
        if quality_score >= 0.85:
            return WorkerResult(
                success=True,
                output={
                    "verdict": "APPROVED",
                    "score": quality_score,
                    "feedback": "Work meets quality standards",
                },
            )
        else:
            return WorkerResult(
                success=False,
                output={
                    "verdict": "REJECTED",
                    "score": quality_score,
                    "feedback": "Work needs improvement",
                },
                error="Quality below threshold",
            )


# Worker registry
WORKERS = {
    "arch": ArchWorker,
    "byte": ByteWorker,
    "pixel": PixelWorker,
    "judge": JudgeWorker,
}


def get_worker(agent_id: str) -> Optional[AgentWorker]:
    """Get worker instance for agent ID."""
    worker_class = WORKERS.get(agent_id)
    if worker_class:
        return worker_class()
    return None


__all__ = [
    "AgentWorker",
    "WorkerResult",
    "ArchWorker",
    "ByteWorker",
    "PixelWorker",
    "JudgeWorker",
    "get_worker",
    "WORKERS",
]
