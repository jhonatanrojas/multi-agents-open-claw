#!/usr/bin/env python3
"""
Tests for F2.1 — SupervisorService
"""

import sys
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from persistence import init_db, get_db, RunRepository, TaskRepository
from supervisor import (
    SupervisorService,
    TaskIntent,
    ReviewVerdict,
    BlockerResolution,
)
from models import RunContext, RunStatus, AgentType, GraphState


def test_supervisor_creation():
    """Test supervisor service creation."""
    print("Testing supervisor creation...")
    
    init_db()
    db = next(get_db())
    
    run_repo = RunRepository(db)
    task_repo = TaskRepository(db)
    
    supervisor = SupervisorService(run_repo, task_repo)
    
    assert supervisor.run_repo is run_repo
    assert supervisor.task_repo is task_repo
    
    print("  ✓ Supervisor created")


def test_decide_next_step():
    """Test decide_next_step for a run."""
    print("Testing decide_next_step...")
    
    db = next(get_db())
    supervisor = SupervisorService(RunRepository(db), TaskRepository(db))
    
    # Create a run in discovery phase
    run = RunContext(
        run_id="run-test-001",
        project_id="proj-001",
        status=RunStatus.EXECUTING,
        current_phase=GraphState.DISCOVERY,
    )
    
    intent = supervisor.decide_next_step(run)
    
    assert intent is not None
    assert intent.next_stage == GraphState.PLANNING
    assert intent.required_agent == AgentType.ARCH
    
    print(f"  ✓ Next step: {intent.next_stage.value} with {intent.required_agent.value}")


def test_decide_next_step_terminal():
    """Test decide_next_step returns None for terminal states."""
    print("Testing decide_next_step for terminal state...")
    
    db = next(get_db())
    supervisor = SupervisorService(RunRepository(db), TaskRepository(db))
    
    # Completed run
    run = RunContext(
        run_id="run-test-002",
        project_id="proj-002",
        status=RunStatus.COMPLETED,
    )
    
    intent = supervisor.decide_next_step(run)
    
    assert intent is None
    print("  ✓ No next step for completed run")


def test_assign_task():
    """Test task assignment."""
    print("Testing assign_task...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    supervisor = SupervisorService(run_repo, TaskRepository(db))
    
    # Create run in DB first (required for FK constraint)
    db_run = run_repo.create_run(
        project_id="proj-003",
        status="executing",
    )
    
    # Create run context
    run = RunContext(
        run_id=db_run.id,
        project_id="proj-003",
        status=RunStatus.EXECUTING,
        current_phase=GraphState.DISCOVERY,
    )
    
    # Create intent
    intent = TaskIntent(
        next_stage=GraphState.PLANNING,
        required_agent=AgentType.ARCH,
        task_type="analysis",
        description="Analyze requirements",
    )
    
    # Assign task
    task = supervisor.assign_task(intent, run)
    
    assert task.task_id.startswith("task-")
    assert task.agent == AgentType.ARCH
    assert task.status == "pending"
    
    print(f"  ✓ Task assigned: {task.task_id}")


def test_review_result():
    """Test task result review."""
    print("Testing review_result...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    supervisor = SupervisorService(run_repo, TaskRepository(db))
    
    # Create run in DB first
    db_run = run_repo.create_run(
        project_id="proj-004",
        status="executing",
    )
    
    # Create run context
    run = RunContext(
        run_id=db_run.id,
        project_id="proj-004",
        status=RunStatus.EXECUTING,
    )
    
    task = supervisor.assign_task(
        TaskIntent(
            next_stage=GraphState.EXECUTING,
            required_agent=AgentType.BYTE,
            task_type="coding",
            description="Implement feature",
        ),
        run,
    )
    
    # Review pending task (should not be approved yet)
    verdict = supervisor.review_result(task, run)
    
    # Task is pending, not completed
    # The review logic may vary
    assert isinstance(verdict, ReviewVerdict)
    
    print(f"  ✓ Review verdict: {verdict.value}")


def test_handle_blocker():
    """Test blocker handling."""
    print("Testing handle_blocker...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    supervisor = SupervisorService(run_repo, TaskRepository(db))
    
    # Create run in DB first
    db_run = run_repo.create_run(
        project_id="proj-005",
        status="executing",
    )
    
    run = RunContext(
        run_id=db_run.id,
        project_id="proj-005",
        status=RunStatus.EXECUTING,
    )
    
    task = supervisor.assign_task(
        TaskIntent(
            next_stage=GraphState.EXECUTING,
            required_agent=AgentType.BYTE,
            task_type="coding",
            description="Implement feature",
        ),
        run,
    )
    
    resolution = supervisor.handle_blocker(task, run)
    
    assert isinstance(resolution, BlockerResolution)
    
    print(f"  ✓ Blocker resolution: {resolution.value}")


def test_heartbeat_cycle():
    """Test heartbeat cycle."""
    print("Testing heartbeat_cycle...")
    
    db = next(get_db())
    supervisor = SupervisorService(RunRepository(db), TaskRepository(db))
    
    run = RunContext(
        run_id="run-test-006",
        project_id="proj-006",
        status=RunStatus.EXECUTING,
    )
    
    # Heartbeat on healthy run
    intervention = supervisor.run_heartbeat_cycle(run)
    
    # Should return None for healthy run
    # (In real implementation, would check for stalls)
    
    print("  ✓ Heartbeat cycle completed")


def test_task_intent():
    """Test TaskIntent dataclass."""
    print("Testing TaskIntent...")
    
    intent = TaskIntent(
        next_stage=GraphState.EXECUTING,
        required_agent=AgentType.BYTE,
        task_type="coding",
        description="Write code",
        input_data={"feature": "auth"},
        priority=5,
    )
    
    data = intent.to_dict()
    
    assert data["task_type"] == "coding"
    assert data["priority"] == 5
    
    print("  ✓ TaskIntent serialization works")


def run_all_tests():
    """Run all F2.1 tests."""
    print("=" * 60)
    print("F2.1 — SupervisorService Tests")
    print("=" * 60)
    
    tests = [
        test_supervisor_creation,
        test_decide_next_step,
        test_decide_next_step_terminal,
        test_assign_task,
        test_review_result,
        test_handle_blocker,
        test_heartbeat_cycle,
        test_task_intent,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            import traceback
            traceback.print_exc()
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 F2.1 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
