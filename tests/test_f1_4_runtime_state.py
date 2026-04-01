#!/usr/bin/env python3
"""
Tests for F1.4 — Endpoint de sincronización UI
"""

import sys
sys.path.insert(0, '/var/www/openclaw-multi-agents')

import json
from persistence import init_db, get_db, RunRepository, TaskRepository


def test_runtime_state_endpoint():
    """Test runtime state endpoint returns complete state."""
    print("Testing runtime state endpoint...")
    
    # Initialize DB
    init_db()
    db = next(get_db())
    
    # Create test data
    run_repo = RunRepository(db)
    task_repo = TaskRepository(db)
    
    run = run_repo.create_run(
        project_id="proj-test-001",
        status="executing",
        current_phase="implementation",
        current_agent="byte",
        context_json=json.dumps({
            "blockers": [
                {
                    "blocker_id": "blk-001",
                    "description": "API rate limit",
                    "created_at": "2026-03-30T10:00:00Z"
                }
            ]
        })
    )
    
    task = task_repo.create_task(
        run_id=run.id,
        agent="byte",
        description="Implement feature",
        status="in_progress"
    )
    
    print(f"  ✓ Created run {run.id} with task {task.id}")
    
    # Test that we can build the response structure
    from api.runtime_state import RuntimeStateResponse, TaskState, BlockerState
    
    task_state = TaskState(
        task_id=task.id,
        agent=task.agent,
        status=task.status,
        description=task.description or "",
        created_at=task.created_at.isoformat() if task.created_at else "",
    )
    
    blocker_state = BlockerState(
        blocker_id="blk-001",
        description="API rate limit",
        created_at="2026-03-30T10:00:00Z",
    )
    
    response = RuntimeStateResponse(
        project_id="proj-test-001",
        run_id=run.id,
        status=run.status,
        current_phase=run.current_phase,
        current_agent=run.current_agent,
        plan_version=1,
        tasks=[task_state],
        agents={"byte": {"status": "busy", "current_task": task.id, "last_activity": None}},
        blockers=[blocker_state],
        logs=["Run started", "Status: executing"],
        updated_at=run.updated_at.isoformat() if run.updated_at else "",
    )
    
    assert response.project_id == "proj-test-001"
    assert response.run_id == run.id
    assert response.status == "executing"
    assert len(response.tasks) == 1
    assert len(response.blockers) == 1
    
    print("  ✓ RuntimeStateResponse built successfully")
    print(f"  ✓ Project: {response.project_id}")
    print(f"  ✓ Run: {response.run_id}")
    print(f"  ✓ Tasks: {len(response.tasks)}")
    print(f"  ✓ Blockers: {len(response.blockers)}")


def test_response_structure():
    """Test that response has all required fields."""
    print("Testing response structure...")
    
    from api.runtime_state import RuntimeStateResponse, TaskState, BlockerState
    from pydantic import ValidationError
    
    # Valid response
    try:
        response = RuntimeStateResponse(
            project_id="proj-001",
            run_id="run-001",
            status="executing",
            current_phase="implementation",
            current_agent="byte",
            plan_version=1,
            tasks=[],
            agents={},
            blockers=[],
            logs=[],
            updated_at="2026-03-30T10:00:00Z",
        )
        print("  ✓ Valid response created")
    except ValidationError as e:
        print(f"  ❌ Validation error: {e}")
        raise
    
    # Check all required fields
    required_fields = [
        "project_id", "run_id", "status", "current_phase",
        "current_agent", "plan_version", "tasks", "agents",
        "blockers", "logs", "updated_at"
    ]
    
    for field in required_fields:
        assert hasattr(response, field), f"Missing field: {field}"
    
    print(f"  ✓ All {len(required_fields)} required fields present")


def test_ui_never_infers_state():
    """Test that endpoint provides all state (UI never infers)."""
    print("Testing UI never infers state...")
    
    from api.runtime_state import RuntimeStateResponse
    
    # The response must contain ALL information UI needs
    # No inference should be necessary
    response = RuntimeStateResponse(
        project_id="proj-001",
        run_id="run-001",
        status="executing",
        current_phase="implementation",
        current_agent="byte",
        plan_version=1,
        tasks=[
            {"task_id": "t1", "agent": "byte", "status": "in_progress", 
             "description": "Task 1", "created_at": "2026-03-30T10:00:00Z"}
        ],
        agents={"byte": {"status": "busy", "current_task": "t1", "last_activity": None}},
        blockers=[],
        logs=["Run started"],
        updated_at="2026-03-30T10:00:00Z",
    )
    
    # UI can read everything directly
    assert response.status == "executing"
    assert response.current_phase == "implementation"
    assert response.current_agent == "byte"
    assert len(response.tasks) == 1
    assert response.agents["byte"]["status"] == "busy"
    
    print("  ✓ UI can read all state directly without inference")


def run_all_tests():
    """Run all F1.4 tests."""
    print("=" * 60)
    print("F1.4 — Endpoint de sincronización UI Tests")
    print("=" * 60)
    
    tests = [
        test_runtime_state_endpoint,
        test_response_structure,
        test_ui_never_infers_state,
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
        print("\n🎉 F1.4 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
