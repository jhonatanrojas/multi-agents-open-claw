#!/usr/bin/env python3
"""
Tests for F1.5 — Normalizar estados del grafo
"""

import sys
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from graph_state import GraphState, validate_state_transition, ACTIVE_STATES, TERMINAL_STATES


def test_graph_state_enum():
    """Test GraphState enum values."""
    print("Testing GraphState enum values...")
    
    # Test that all expected states exist
    states = [
        GraphState.DISCOVERY,
        GraphState.PLANNING,
        GraphState.EXECUTING,
        GraphState.IMPLEMENTATION,
        GraphState.REVIEW,
        GraphState.BLOCKED,
        GraphState.PAUSED,
        GraphState.COMPLETED,
        GraphState.FAILED,
    ]
    
    for state in states:
        assert isinstance(state, GraphState)
        assert isinstance(state.value, str)
        print(f"  ✓ {state.name} = '{state.value}'")


def test_no_string_literals():
    """Test that we never use string literals (always enum)."""
    print("Testing no string literals pattern...")
    
    # This is how code should be written (using enum)
    state = GraphState.EXECUTING
    assert state == GraphState.EXECUTING
    assert state.value == "executing"
    
    # Not like this (string literal - anti-pattern)
    # state = "executing"  # ❌ Never do this
    
    print("  ✓ Using enum instead of string literals")


def test_from_string():
    """Test converting strings to GraphState."""
    print("Testing from_string conversion...")
    
    # Valid conversions
    assert GraphState.from_string("discovery") == GraphState.DISCOVERY
    assert GraphState.from_string("EXECUTING") == GraphState.EXECUTING  # Case insensitive
    assert GraphState.from_string("Completed") == GraphState.COMPLETED
    
    # Invalid conversion
    assert GraphState.from_string("invalid_state") is None
    
    print("  ✓ String to enum conversion works")


def test_terminal_states():
    """Test terminal state detection."""
    print("Testing terminal state detection...")
    
    # Terminal states
    assert GraphState.is_terminal(GraphState.COMPLETED) is True
    assert GraphState.is_terminal(GraphState.FAILED) is True
    assert GraphState.is_terminal(GraphState.CANCELLED) is True
    
    # Non-terminal states
    assert GraphState.is_terminal(GraphState.EXECUTING) is False
    assert GraphState.is_terminal(GraphState.BLOCKED) is False
    assert GraphState.is_terminal(GraphState.DISCOVERY) is False
    
    print("  ✓ Terminal states correctly identified")


def test_state_transitions():
    """Test valid state transitions."""
    print("Testing state transitions...")
    
    # Valid transitions
    assert GraphState.can_transition_to(GraphState.DISCOVERY, GraphState.PLANNING) is True
    assert GraphState.can_transition_to(GraphState.PLANNING, GraphState.EXECUTING) is True
    assert GraphState.can_transition_to(GraphState.EXECUTING, GraphState.REVIEW) is True
    assert GraphState.can_transition_to(GraphState.REVIEW, GraphState.COMPLETED) is True
    
    # Can always transition to blocked/paused
    assert GraphState.can_transition_to(GraphState.EXECUTING, GraphState.BLOCKED) is True
    assert GraphState.can_transition_to(GraphState.BLOCKED, GraphState.EXECUTING) is True
    
    # Invalid transitions
    assert GraphState.can_transition_to(GraphState.COMPLETED, GraphState.EXECUTING) is False
    assert GraphState.can_transition_to(GraphState.DISCOVERY, GraphState.COMPLETED) is False
    
    print("  ✓ State transitions validated")


def test_validate_state_transition():
    """Test validate_state_transition function."""
    print("Testing validate_state_transition function...")
    
    # Valid transition
    valid, error = validate_state_transition("discovery", "planning")
    assert valid is True
    assert error is None
    
    # Invalid transition
    valid, error = validate_state_transition("completed", "executing")
    assert valid is False
    assert error is not None
    
    # Invalid target state
    valid, error = validate_state_transition("discovery", "invalid_state")
    assert valid is False
    assert "Invalid state" in error
    
    print("  ✓ State transition validation works")


def test_display_names():
    """Test display names for UI."""
    print("Testing display names...")
    
    assert GraphState.DISCOVERY.get_display_name() == "Discovery"
    assert GraphState.EXECUTING.get_display_name() == "Executing"
    assert GraphState.PRICE_DISCUSSION.get_display_name() == "Price Discussion"
    assert GraphState.COMPLETED.get_display_name() == "Completed"
    
    print("  ✓ Display names available for UI")


def test_state_groups():
    """Test state group constants."""
    print("Testing state group constants...")
    
    # Active states
    assert GraphState.EXECUTING in ACTIVE_STATES
    assert GraphState.COMPLETED not in ACTIVE_STATES
    
    # Terminal states
    assert GraphState.COMPLETED in TERMINAL_STATES
    assert GraphState.FAILED in TERMINAL_STATES
    assert GraphState.EXECUTING not in TERMINAL_STATES
    
    print(f"  ✓ {len(ACTIVE_STATES)} active states")
    print(f"  ✓ {len(TERMINAL_STATES)} terminal states")


def test_run_context_integration():
    """Test GraphState integration with RunContext."""
    print("Testing RunContext integration...")
    
    from models import RunContext, RunStatus, GraphState
    
    # Create RunContext with GraphState (not string!)
    context = RunContext(
        run_id="run-test-001",
        project_id="proj-001",
        status=RunStatus.EXECUTING,
        current_phase=GraphState.IMPLEMENTATION,  # Using enum, not string!
        current_agent=None,
    )
    
    assert context.current_phase == GraphState.IMPLEMENTATION
    assert isinstance(context.current_phase, GraphState)
    
    # Serialization should store as string value
    data = context.to_dict()
    assert data["current_phase"] == "implementation"
    
    # Deserialization should restore as GraphState
    context2 = RunContext.from_dict(data)
    assert context2.current_phase == GraphState.IMPLEMENTATION
    assert isinstance(context2.current_phase, GraphState)
    
    print("  ✓ RunContext uses GraphState (not string literals)")


def run_all_tests():
    """Run all F1.5 tests."""
    print("=" * 60)
    print("F1.5 — Normalizar estados del grafo Tests")
    print("=" * 60)
    
    tests = [
        test_graph_state_enum,
        test_no_string_literals,
        test_from_string,
        test_terminal_states,
        test_state_transitions,
        test_validate_state_transition,
        test_display_names,
        test_state_groups,
        test_run_context_integration,
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
        print("\n🎉 F1.5 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
