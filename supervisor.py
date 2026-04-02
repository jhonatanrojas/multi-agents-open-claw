#!/usr/bin/env python3
"""
supervisor.py - SupervisorService for orchestrating agent tasks (F2.1)

The supervisor is the central orchestrator that:
- Decides next steps based on run state
- Assigns tasks to available agents
- Reviews task results
- Handles blockers and interventions

Usage:
    from supervisor import SupervisorService
    
    supervisor = SupervisorService(run_repo, task_repo, circuit_breakers)
    
    # Decide next step
    intent = supervisor.decide_next_step(run_context)
    if intent:
        task = supervisor.assign_task(intent, run_context)
    
    # Review completed task
    verdict = supervisor.review_result(task, run_context)
"""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum, auto

from persistence import RunRepository, TaskRepository
from circuit_breaker import CircuitBreakerRegistry
from graph_state import GraphState, ACTIVE_STATES
from models import RunContext, AgentType, TaskInfo
from action_envelope import ActionType


class ReviewVerdict(str, Enum):
    """Verdict from reviewing a task result."""
    APPROVED = "approved"
    REJECTED = "rejected"
    NEEDS_INFO = "needs_info"


class BlockerResolution(str, Enum):
    """Resolution strategy for blockers."""
    RETRY = "retry"
    REASSIGN = "reassign"
    DECOMPOSE = "decompose"
    ESCALATE = "escalate"


@dataclass
class TaskIntent:
    """
    Intent for the next task to execute.
    
    Created by the supervisor's decision logic.
    """
    next_stage: GraphState
    required_agent: AgentType
    task_type: str  # 'analysis', 'coding', 'design', 'review'
    description: str
    input_data: Optional[Dict[str, Any]] = None
    priority: int = 1  # Higher = more urgent
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "next_stage": self.next_stage.value if isinstance(self.next_stage, GraphState) else self.next_stage,
            "required_agent": self.required_agent.value if isinstance(self.required_agent, AgentType) else self.required_agent,
            "task_type": self.task_type,
            "description": self.description,
            "input_data": self.input_data,
            "priority": self.priority,
        }


class SupervisorService:
    """
    Central supervisor service for orchestrating multi-agent execution.
    
    This is the only component that modifies run state.
    Agents only receive tasks and return results.
    """
    
    def __init__(
        self,
        run_repo: RunRepository,
        task_repo: TaskRepository,
        circuit_breakers: Optional[Any] = None,
    ):
        self.run_repo = run_repo
        self.task_repo = task_repo
        self.circuit_breakers = circuit_breakers or CircuitBreakerRegistry
    
    def decide_next_step(self, run: RunContext) -> Optional[TaskIntent]:
        """
        Decide the next task to execute based on run state.
        
        Args:
            run: Current run context
        
        Returns:
            TaskIntent if there's work to do, None if run is complete/blocked
        """
        # Check if run is in terminal state
        if run.status in ["completed", "failed", "cancelled"]:
            return None
        
        # Check if run is paused
        if run.status == "paused":
            return None
        
        # Check for active blockers
        active_blockers = [b for b in run.blockers if b.resolved_at is None]
        if active_blockers:
            # Handle blocker first
            return self._create_blocker_resolution_intent(run, active_blockers[0])
        
        # Determine next phase based on current state
        current_phase = run.current_phase or GraphState.DISCOVERY
        
        # Simple state machine for task generation
        transitions = {
            GraphState.DISCOVERY: (GraphState.PLANNING, AgentType.ARCH, "analysis"),
            GraphState.PLANNING: (GraphState.EXECUTING, AgentType.ARCH, "design"),
            GraphState.EXECUTING: (GraphState.IMPLEMENTATION, AgentType.BYTE, "coding"),
            GraphState.IMPLEMENTATION: (GraphState.REVIEW, AgentType.PIXEL, "review"),
            GraphState.REVIEW: (GraphState.COMPLETED, AgentType.JUDGE, "validation"),
        }
        
        if current_phase in transitions:
            next_stage, agent, task_type = transitions[current_phase]
            
            # Check if agent is available
            cb = self.circuit_breakers.get(agent.value)
            if not cb.is_available():
                # Agent in cooldown, try alternative
                alternative = self._find_alternative_agent(agent)
                if alternative:
                    agent = alternative
                else:
                    # No alternative available, wait
                    return None
            
            return TaskIntent(
                next_stage=next_stage,
                required_agent=agent,
                task_type=task_type,
                description=f"Execute {task_type} for {next_stage.value} phase",
                input_data={"current_phase": current_phase.value},
            )
        
        return None
    
    def assign_task(self, intent: TaskIntent, run: RunContext) -> TaskInfo:
        """
        Create and assign a task from an intent.
        
        Args:
            intent: Task intent from decide_next_step
            run: Current run context
        
        Returns:
            Created TaskInfo
        """
        from models import generate_task_id
        
        task_id = generate_task_id()
        
        # Create task in database
        db_task = self.task_repo.create_task(
            run_id=run.run_id,
            agent=intent.required_agent.value,
            description=intent.description,
            status="pending",
            input_data=intent.input_data,
        )
        
        # Create TaskInfo for return
        task = TaskInfo(
            task_id=db_task.id,
            agent=intent.required_agent,
            status="pending",
            description=intent.description,
            created_at=datetime.utcnow(),
        )
        
        # Update run context
        run.add_task(task)
        run.current_phase = intent.next_stage
        run.current_agent = intent.required_agent
        
        # Persist run context
        run.checkpoint()
        
        return task
    
    def review_result(self, task: TaskInfo, run: RunContext) -> ReviewVerdict:
        """
        Review a completed task result.
        
        F2.5: Integrated JUDGE review for quality validation.
        
        Args:
            task: Completed task
            run: Current run context
        
        Returns:
            Review verdict
        """
        # Get task from DB
        db_task = self.task_repo.get_task(task.task_id)
        if not db_task:
            return ReviewVerdict.REJECTED
        
        # Check if task failed
        if db_task.status == "failed":
            # Record failure in circuit breaker
            cb = self.circuit_breakers.get(task.agent.value)
            cb.record_failure()
            return ReviewVerdict.REJECTED
        
        # F2.5: JUDGE review for significant tasks
        if task.agent in [AgentType.ARCH, AgentType.BYTE]:
            judge_approval = self._judge_review(task, run)
            if not judge_approval:
                return ReviewVerdict.REJECTED
        
        # Check output quality (simplified)
        output = db_task.output_json
        if output:
            try:
                output_data = json.loads(output)
                # Basic validation
                if "error" in output_data:
                    return ReviewVerdict.NEEDS_INFO
            except json.JSONDecodeError:
                return ReviewVerdict.REJECTED
        
        # Record success in circuit breaker
        cb = self.circuit_breakers.get(task.agent.value)
        cb.record_success()
        
        return ReviewVerdict.APPROVED
    
    def _judge_review(self, task: TaskInfo, run: RunContext) -> bool:
        """
        F2.5: JUDGE agent review for quality validation.
        
        Args:
            task: Task to review
            run: Current run context
        
        Returns:
            True if JUDGE approves, False otherwise
        """
        from agent_worker import JudgeWorker
        from task_entity import TaskEntity, TaskStatus
        
        # Create JUDGE worker
        judge = JudgeWorker()
        
        # Create review task using TaskEntity (has start/complete/fail methods)
        review_task = TaskEntity(
            task_id=f"review-{task.task_id}",
            run_id=run.run_id,
            agent_id="judge",
            status=TaskStatus.IN_PROGRESS,
            title=f"Review task {task.task_id}",
            description=f"Review task {task.task_id} from {task.agent.value}",
        )
        
        # Get task output for review
        db_task = self.task_repo.get_task(task.task_id)
        work_output = {}
        if db_task and db_task.output_json:
            try:
                work_output = json.loads(db_task.output_json)
            except json.JSONDecodeError:
                pass
        
        review_task.input_data = {"work": work_output, "original_task": task.description}
        
        # Execute JUDGE review
        result = judge.process_task(review_task)
        
        # Check verdict
        if result.action == ActionType.COMPLETE:
            payload = result.payload
            if payload.get("verdict") == "APPROVED":
                return True
        
        return False
    
    def handle_blocker(self, task: TaskInfo, run: RunContext) -> BlockerResolution:
        """
        Decide how to handle a blocker.
        
        Args:
            task: Task that encountered a blocker
            run: Current run context
        
        Returns:
            Resolution strategy
        """
        # Get circuit breaker state
        cb = self.circuit_breakers.get(task.agent.value)
        
        # If agent has many failures, reassign
        if cb.failures >= 2:
            alternative = self._find_alternative_agent(task.agent)
            if alternative:
                return BlockerResolution.REASSIGN
        
        # If task has been retried multiple times, decompose
        task_attempts = sum(1 for t in run.tasks if t.agent == task.agent)
        if task_attempts >= 3:
            return BlockerResolution.DECOMPOSE
        
        # Default: retry
        return BlockerResolution.RETRY
    
    def run_heartbeat_cycle(self, run: RunContext) -> Optional[str]:
        """
        Called periodically to detect stalls and intervene.
        
        Args:
            run: Current run context
        
        Returns:
            Intervention action or None if healthy
        """
        # Check for stalled tasks (no update in > 5 minutes)
        # This is a simplified check
        for task in run.tasks:
            if task.status == "in_progress":
                # Check if task is stalled
                # In real implementation, compare timestamps
                pass
        
        # Check if current phase hasn't changed in too long
        # This would need persisted timestamps
        
        return None
    
    def _create_blocker_resolution_intent(
        self,
        run: RunContext,
        blocker: Any
    ) -> Optional[TaskIntent]:
        """Create an intent to resolve a blocker."""
        # Simplified: create a task to resolve the blocker
        return TaskIntent(
            next_stage=GraphState.ESCALATE,
            required_agent=AgentType.JUDGE,
            task_type="analysis",
            description=f"Resolve blocker: {blocker.description}",
            priority=10,  # High priority
        )
    
    def _find_alternative_agent(self, preferred: AgentType) -> Optional[AgentType]:
        """Find an alternative agent if preferred is unavailable."""
        alternatives = {
            AgentType.ARCH: [AgentType.BYTE, AgentType.PIXEL],
            AgentType.BYTE: [AgentType.PIXEL, AgentType.ARCH],
            AgentType.PIXEL: [AgentType.BYTE, AgentType.ARCH],
            AgentType.JUDGE: [AgentType.ARCH],  # Judge is special
        }
        
        for alternative in alternatives.get(preferred, []):
            cb = self.circuit_breakers.get(alternative.value)
            if cb.is_available():
                return alternative
        
        return None


__all__ = [
    "SupervisorService",
    "TaskIntent",
    "ReviewVerdict",
    "BlockerResolution",
]
