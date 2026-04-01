#!/usr/bin/env python3
"""
Tests for F1.6 — Circuit breaker por agente
"""

import sys
import time
import uuid
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from circuit_breaker import (
    AgentCircuitBreaker,
    CircuitBreakerRegistry,
    record_agent_failure,
    record_agent_success,
    is_agent_available,
    get_circuit_breaker_status,
)


def _unique_agent_id(base: str) -> str:
    """Generate unique agent ID for test isolation."""
    return f"{base}-{uuid.uuid4().hex[:8]}"


def test_circuit_breaker_creation():
    """Test circuit breaker creation."""
    print("Testing circuit breaker creation...")
    
    agent_id = _unique_agent_id("byte")
    cb = AgentCircuitBreaker(agent_id, threshold=3, cooldown_seconds=60)
    assert cb.agent_id == agent_id
    assert cb.threshold == 3
    assert cb.is_available() is True
    print(f"  ✓ Created: {cb}")


def test_record_failure():
    """Test recording failures."""
    print("Testing record failure...")
    
    agent_id = _unique_agent_id("pixel")
    cb = AgentCircuitBreaker(agent_id, threshold=2, cooldown_seconds=60)
    
    # Fresh instance should have 0 failures
    assert cb.failures == 0, f"Expected 0 failures, got {cb.failures}"
    
    # Record failures
    cb.record_failure()
    assert cb.failures == 1, f"Expected 1 failure after first record_failure, got {cb.failures}"
    assert cb.is_available() is True
    
    cb.record_failure()
    assert cb.failures == 2, f"Expected 2 failures after second record_failure, got {cb.failures}"
    assert cb.is_available() is False  # Threshold reached
    
    print(f"  ✓ Failures recorded: {cb.failures}, available: {cb.is_available()}")


def test_cooldown():
    """Test cooldown mechanism."""
    print("Testing cooldown...")
    
    agent_id = _unique_agent_id("arch")
    cb = AgentCircuitBreaker(agent_id, threshold=1, cooldown_seconds=1)
    
    # Fresh instance should have 0 failures
    assert cb.failures == 0, f"Expected 0 failures initially, got {cb.failures}"
    
    # Trigger cooldown
    cb.record_failure()
    assert cb.is_available() is False
    print(f"  ✓ Cooldown started")
    
    # Wait for cooldown to expire
    time.sleep(1.1)
    assert cb.is_available() is True
    print(f"  ✓ Cooldown expired, agent available again")


def test_record_success_resets():
    """Test that success resets failures."""
    print("Testing success reset...")
    
    agent_id = _unique_agent_id("judge")
    cb = AgentCircuitBreaker(agent_id, threshold=3, cooldown_seconds=60)
    
    # Fresh instance should have 0 failures
    assert cb.failures == 0, f"Expected 0 failures initially, got {cb.failures}"
    
    # Record failures
    cb.record_failure()
    cb.record_failure()
    assert cb.failures == 2, f"Expected 2 failures, got {cb.failures}"
    
    # Success resets
    cb.record_success()
    assert cb.failures == 0
    assert cb.is_available() is True
    
    print(f"  ✓ Success reset failures to 0")


def test_registry():
    """Test circuit breaker registry."""
    print("Testing registry...")
    
    agent_id = _unique_agent_id("byte-registry")
    
    # Get circuit breaker from registry
    cb1 = CircuitBreakerRegistry.get(agent_id)
    cb2 = CircuitBreakerRegistry.get(agent_id)
    
    # Should be same instance
    assert cb1 is cb2
    print(f"  ✓ Registry returns same instance")
    
    # Get all states
    states = CircuitBreakerRegistry.get_all_states()
    assert agent_id in states
    print(f"  ✓ Registry has {len(states)} agents")


def test_convenience_functions():
    """Test convenience functions."""
    print("Testing convenience functions...")
    
    agent_id = _unique_agent_id("test-agent-convenience")
    
    # Record failure
    record_agent_failure(agent_id)
    assert is_agent_available(agent_id) is True  # Below threshold
    
    # Record more failures
    record_agent_failure(agent_id)
    record_agent_failure(agent_id)
    assert is_agent_available(agent_id) is False  # Threshold reached (default 3)
    
    # Record success
    record_agent_success(agent_id)
    assert is_agent_available(agent_id) is True
    
    print(f"  ✓ Convenience functions work")


def test_get_available_agents():
    """Test filtering available agents."""
    print("Testing get available agents...")
    
    # Create unique agent IDs for this test
    agent_a = _unique_agent_id("agent-a")
    agent_b = _unique_agent_id("agent-b")
    agent_c = _unique_agent_id("agent-c")
    
    # Create circuit breakers
    CircuitBreakerRegistry.get(agent_a)
    CircuitBreakerRegistry.get(agent_b)
    cb_c = CircuitBreakerRegistry.get(agent_c)
    
    # Put one in cooldown
    cb_c.record_failure()
    cb_c.record_failure()
    cb_c.record_failure()
    
    available = CircuitBreakerRegistry.get_available_agents([agent_a, agent_b, agent_c])
    
    assert agent_a in available
    assert agent_b in available
    assert agent_c not in available  # In cooldown
    
    print(f"  ✓ Available agents: {available}")


def test_health_status():
    """Test health status endpoint data."""
    print("Testing health status...")
    
    status = get_circuit_breaker_status()
    
    assert "circuit_breakers" in status
    assert "timestamp" in status
    
    print(f"  ✓ Health status contains {len(status['circuit_breakers'])} agents")


def test_state():
    """Test getting circuit breaker state."""
    print("Testing get state...")
    
    agent_id = _unique_agent_id("test-state")
    cb = AgentCircuitBreaker(agent_id, threshold=2, cooldown_seconds=300)
    
    # Fresh instance should have 0 failures
    assert cb.failures == 0, f"Expected 0 failures initially, got {cb.failures}"
    
    cb.record_failure()
    
    state = cb.get_state()
    
    assert state["agent_id"] == agent_id
    assert state["failures"] == 1, f"Expected 1 failure, got {state['failures']}"
    assert state["threshold"] == 2
    assert state["is_available"] is True
    
    print(f"  ✓ State: failures={state['failures']}, available={state['is_available']}")


def run_all_tests():
    """Run all F1.6 tests."""
    print("=" * 60)
    print("F1.6 — Circuit breaker por agente Tests")
    print("=" * 60)
    
    tests = [
        test_circuit_breaker_creation,
        test_record_failure,
        test_cooldown,
        test_record_success_resets,
        test_registry,
        test_convenience_functions,
        test_get_available_agents,
        test_health_status,
        test_state,
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
        print("\n🎉 F1.6 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
