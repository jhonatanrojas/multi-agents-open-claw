#!/usr/bin/env python3
"""
Tests for F1.2 — Capa de persistencia
"""

import sys
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from persistence import init_db, get_db, RunRepository, TaskRepository, EventRepository
import json


def test_database_initialization():
    """Test database initialization."""
    print("Testing database initialization...")
    init_db()
    print("  ✓ Database initialized")


def test_run_repository():
    """Test RunRepository CRUD operations."""
    print("Testing RunRepository...")
    
    db = next(get_db())
    repo = RunRepository(db)
    
    # Create
    run = repo.create_run(
        project_id="proj-001",
        status="planning",
        current_phase="discovery",
        current_agent="arch"
    )
    assert run.id.startswith("run-")
    assert run.project_id == "proj-001"
    print(f"  ✓ Run created: {run.id}")
    
    # Read
    run2 = repo.get_run(run.id)
    assert run2 is not None
    assert run2.id == run.id
    print("  ✓ Run retrieved")
    
    # Update
    run3 = repo.update_run(run.id, status="executing", current_phase="implementation")
    assert run3.status == "executing"
    print("  ✓ Run updated")
    
    # List
    runs = repo.list_runs()
    assert len(runs) >= 1
    print(f"  ✓ Listed {len(runs)} runs")
    
    # Active runs
    active = repo.get_active_runs()
    print(f"  ✓ Found {len(active)} active runs")


def test_task_repository():
    """Test TaskRepository CRUD operations."""
    print("Testing TaskRepository...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    task_repo = TaskRepository(db)
    
    # Create run first
    run = run_repo.create_run(project_id="proj-002", status="executing")
    
    # Create task
    task = task_repo.create_task(
        run_id=run.id,
        agent="byte",
        description="Implement feature X",
        status="pending",
        input_data={"brief": "Create API endpoint"}
    )
    assert task.id.startswith("task-")
    print(f"  ✓ Task created: {task.id}")
    
    # Get tasks for run
    tasks = task_repo.get_tasks_for_run(run.id)
    assert len(tasks) == 1
    print("  ✓ Tasks retrieved for run")
    
    # Update task
    task2 = task_repo.update_task(
        task.id,
        status="completed",
        output_data={"result": "API created successfully"}
    )
    assert task2.status == "completed"
    assert task2.completed_at is not None
    print("  ✓ Task updated and completed")


def test_event_repository():
    """Test EventRepository append-only operations."""
    print("Testing EventRepository...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    event_repo = EventRepository(db)
    
    # Create run
    run = run_repo.create_run(project_id="proj-003", status="executing")
    
    # Create events
    for i in range(3):
        event_repo.create_event(
            run_id=run.id,
            event_type="task_started" if i == 0 else "task_progress",
            agent="byte",
            payload={"step": i, "progress": i * 33}
        )
    
    print("  ✓ 3 events created")
    
    # Get events for run
    events = event_repo.get_events_for_run(run.id)
    assert len(events) == 3
    print("  ✓ Events retrieved for run")
    
    # Get recent events
    recent = event_repo.get_recent_events(minutes=5)
    assert len(recent) >= 3
    print(f"  ✓ Found {len(recent)} recent events")


def test_relationships():
    """Test model relationships."""
    print("Testing model relationships...")
    
    db = next(get_db())
    run_repo = RunRepository(db)
    task_repo = TaskRepository(db)
    event_repo = EventRepository(db)
    
    # Create run with tasks and events
    run = run_repo.create_run(project_id="proj-004", status="executing")
    task = task_repo.create_task(run_id=run.id, agent="arch", description="Design")
    event_repo.create_event(run_id=run.id, task_id=task.id, event_type="task_created")
    
    # Refresh run to get relationships
    db.refresh(run)
    
    assert len(run.tasks) >= 1
    assert len(run.events) >= 1
    print("  ✓ Run-task-event relationships working")


def run_all_tests():
    """Run all F1.2 tests."""
    print("=" * 60)
    print("F1.2 — Capa de persistencia Tests")
    print("=" * 60)
    
    tests = [
        test_database_initialization,
        test_run_repository,
        test_task_repository,
        test_event_repository,
        test_relationships,
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
        print("\n🎉 F1.2 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
