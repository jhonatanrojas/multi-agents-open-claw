#!/usr/bin/env python3
"""
pytest configuration and fixtures for multi-agent tests.

This module provides common fixtures for test isolation.
"""

import os
import sys
import pytest
import tempfile
import shutil

# Add project to path
sys.path.insert(0, '/var/www/openclaw-multi-agents')


@pytest.fixture(autouse=True)
def reset_environment():
    """Reset environment variables before each test."""
    # Store original values
    original_environ = os.environ.copy()
    
    yield
    
    # Restore original values
    os.environ.clear()
    os.environ.update(original_environ)


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Clear circuit breaker state before each test."""
    # Import here to avoid circular imports
    from pathlib import Path
    
    state_dir = Path("/tmp/openclaw-circuit-breakers")
    state_file = state_dir / "circuit_breaker_state.json"
    
    # Clear state file
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass
    
    # Clear registry instances
    try:
        from circuit_breaker import CircuitBreakerRegistry
        CircuitBreakerRegistry._breakers.clear()
    except Exception:
        pass
    
    yield
    
    # Cleanup after test
    if state_file.exists():
        try:
            state_file.unlink()
        except Exception:
            pass
    
    try:
        from circuit_breaker import CircuitBreakerRegistry
        CircuitBreakerRegistry._breakers.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def reset_dashboard_api_state():
    """Reset dashboard_api module state before each test."""
    # Clear any cached modules
    modules_to_clear = [
        'dashboard_api',
        'config',
    ]
    
    for mod in modules_to_clear:
        if mod in sys.modules:
            del sys.modules[mod]
    
    yield
    
    # Cleanup after test
    for mod in modules_to_clear:
        if mod in sys.modules:
            del sys.modules[mod]


@pytest.fixture
def temp_state_dir():
    """Create a temporary directory for state files."""
    temp_dir = tempfile.mkdtemp(prefix="openclaw_test_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_memory_json():
    """Create a temporary MEMORY.json for testing."""
    temp_dir = tempfile.mkdtemp(prefix="openclaw_memory_")
    memory_path = os.path.join(temp_dir, "MEMORY.json")
    
    yield memory_path
    
    shutil.rmtree(temp_dir, ignore_errors=True)