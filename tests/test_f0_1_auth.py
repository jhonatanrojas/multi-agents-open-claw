#!/usr/bin/env python3
"""Test script for F0.1 SSE authentication fix."""

import sys
import os
sys.path.insert(0, '/var/www/openclaw-multi-agents')

# Set test environment
os.environ['DASHBOARD_API_KEY'] = 'test-api-key-123'
os.environ['DASHBOARD_SESSION_SECRET'] = 'test-secret-456'

from dashboard_api import (
    _create_session,
    _validate_session,
    _active_sessions,
    _SESSION_MAX_AGE_SEC,
    _API_KEY,
)

def test_session_creation():
    """Test that sessions can be created."""
    print("Testing session creation...")
    token = _create_session()
    assert token is not None
    assert len(token) > 0
    assert token in _active_sessions
    print(f"  Created session: {token[:16]}...")
    return token

def test_session_validation():
    """Test that sessions can be validated."""
    print("Testing session validation...")
    token = _create_session()
    assert _validate_session(token) == True
    print("  Valid session accepted")

def test_invalid_session():
    """Test that invalid sessions are rejected."""
    print("Testing invalid session rejection...")
    assert _validate_session("invalid-token") == False
    assert _validate_session(None) == False
    assert _validate_session("") == False
    print("  Invalid sessions rejected correctly")

def test_api_key_config():
    """Test that API key is loaded."""
    print("Testing API key configuration...")
    assert _API_KEY == 'test-api-key-123'
    print(f"  API key configured: {_API_KEY[:10]}...")

def test_session_cleanup():
    """Test that sessions can be cleaned up."""
    print("Testing session cleanup...")
    from dashboard_api import _cleanup_expired_sessions
    _cleanup_expired_sessions()
    print("  Cleanup executed")

def run_all_tests():
    """Run all F0.1 tests."""
    print("=" * 50)
    print("F0.1 SSE Authentication Fix Tests")
    print("=" * 50)
    
    try:
        test_api_key_config()
        token = test_session_creation()
        test_session_validation(token)
        test_invalid_session()
        test_session_cleanup()
        
        print("=" * 50)
        print("All tests PASSED ✓")
        print("=" * 50)
        return True
    except AssertionError as e:
        print(f"Test FAILED: {e}")
        return False
    except Exception as e:
        print(f"Test ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
