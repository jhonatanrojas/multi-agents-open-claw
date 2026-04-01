#!/usr/bin/env python3
"""
Tests for F1.1 — Formalizar RunContext
"""

import sys
import os
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from models import (
    RunContext,
    RunStatus,
    AgentType,
    TaskInfo,
    Artifact,
    Blocker,
    Milestone,
    generate_run_id,
    generate_task_id,
)
from datetime import datetime


def test_run_context_creation():
    """Test RunContext creation with all fields."""
    print("Testing RunContext creation...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-001",
        status=RunStatus.PLANNING,
        current_phase="discovery",
        current_agent=AgentType.ARCH,
        plan_version=1,
    )
    
    assert context.run_id == run_id
    assert context.project_id == "proj-001"
    assert context.status == RunStatus.PLANNING
    assert context.current_agent == AgentType.ARCH
    print(f"  ✓ Created: {run_id}")
    

def test_run_context_serialization():
    """Test serialization and deserialization."""
    print("Testing serialization...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-002",
        status=RunStatus.EXECUTING,
        current_agent=AgentType.BYTE,
    )
    
    # Serialize
    data = context.to_dict()
    assert "run_id" in data
    assert "status" in data
    assert data["status"] == "executing"
    print("  ✓ Serialized to dict")
    
    # Deserialize
    context2 = RunContext.from_dict(data)
    assert context2.run_id == run_id
    assert context2.status == RunStatus.EXECUTING
    print("  ✓ Deserialized from dict")
    
    # JSON roundtrip
    json_str = context.to_json()
    context3 = RunContext.from_json(json_str)
    assert context3.run_id == run_id
    print("  ✓ JSON roundtrip")


def test_checkpoint_persistence():
    """Test checkpoint save and load."""
    print("Testing checkpoint persistence...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-003",
        status=RunStatus.EXECUTING,
        current_agent=AgentType.PIXEL,
    )
    
    # Save checkpoint
    path = context.checkpoint()
    assert path.exists()
    print(f"  ✓ Checkpoint saved: {path}")
    
    # Load checkpoint
    loaded = RunContext.load(run_id)
    assert loaded is not None
    assert loaded.run_id == run_id
    assert loaded.status == RunStatus.EXECUTING
    print("  ✓ Checkpoint loaded")
    

def test_task_management():
    """Test adding tasks."""
    print("Testing task management...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-004",
        status=RunStatus.EXECUTING,
    )
    
    task = TaskInfo(
        task_id=generate_task_id(),
        agent=AgentType.BYTE,
        status="in_progress",
        description="Implement feature",
        created_at=datetime.utcnow(),
    )
    
    context.add_task(task)
    assert len(context.tasks) == 1
    assert context.tasks[0].description == "Implement feature"
    print("  ✓ Task added")
    

def test_blocker_management():
    """Test adding and resolving blockers."""
    print("Testing blocker management...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-005",
        status=RunStatus.EXECUTING,
    )
    
    blocker = Blocker(
        blocker_id="blk-001",
        description="API rate limit exceeded",
        created_at=datetime.utcnow(),
    )
    
    context.add_blocker(blocker)
    assert context.status == RunStatus.BLOCKED
    assert len(context.blockers) == 1
    print("  ✓ Blocker added, status changed to BLOCKED")
    
    # Resolve blocker
    resolved = context.resolve_blocker("blk-001", "Waited for rate limit reset")
    assert resolved is True
    assert context.blockers[0].resolved_at is not None
    assert context.status == RunStatus.EXECUTING  # Auto-resolved
    print("  ✓ Blocker resolved, status restored")
    

def test_summary():
    """Test run summary."""
    print("Testing summary generation...")
    
    run_id = generate_run_id()
    context = RunContext(
        run_id=run_id,
        project_id="proj-006",
        status=RunStatus.EXECUTING,
        current_agent=AgentType.JUDGE,
    )
    
    summary = context.get_summary()
    assert "run_id" in summary
    assert "status" in summary
    assert summary["task_count"] == 0
    print("  ✓ Summary generated")


def test_list_all_runs():
    """Test listing all runs."""
    print("Testing list all runs...")
    
    # Create a few runs
    for i in range(3):
        run_id = generate_run_id()
        context = RunContext(
            run_id=run_id,
            project_id=f"proj-{i}",
            status=RunStatus.COMPLETED,
        )
        context.checkpoint()
    
    runs = RunContext.list_all()
    assert len(runs) >= 3
    print(f"  ✓ Listed {len(runs)} runs")


def run_all_tests():
    """Run all F1.1 tests."""
    print("=" * 60)
    print("F1.1 — Formalizar RunContext Tests")
    print("=" * 60)
    
    tests = [
        test_run_context_creation,
        test_run_context_serialization,
        test_checkpoint_persistence,
        test_task_management,
        test_blocker_management,
        test_summary,
        test_list_all_runs,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ FAILED: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)
    
    if failed == 0:
        print("\n🎉 F1.1 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
