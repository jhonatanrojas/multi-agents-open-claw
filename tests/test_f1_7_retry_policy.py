#!/usr/bin/env python3
"""
Tests for F1.7 — Retry con backoff exponencial
"""

import sys
import time
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from retry_policy import (
    ErrorType,
    RetryPolicy,
    POLICY_MODEL_ERROR,
    POLICY_TOOL_ERROR,
    POLICY_FORMAT_ERROR,
    classify_error,
    retry_with_backoff,
    retry_decorator,
    RetryContext,
)


def test_calculate_delay():
    """Test exponential backoff delay calculation."""
    print("Testing delay calculation...")
    
    policy = RetryPolicy(base_delay=2.0, max_delay=60.0)
    
    # Attempt 0: ~2 seconds
    delay0 = policy.calculate_delay(0)
    assert 1.5 <= delay0 <= 2.5  # With jitter
    
    # Attempt 1: ~4 seconds
    delay1 = policy.calculate_delay(1)
    assert 3.0 <= delay1 <= 5.0
    
    # Attempt 2: ~8 seconds
    delay2 = policy.calculate_delay(2)
    assert 6.0 <= delay2 <= 10.0
    
    print(f"  ✓ Delays: {delay0:.2f}s, {delay1:.2f}s, {delay2:.2f}s")


def test_max_delay_cap():
    """Test that delay is capped at max_delay."""
    print("Testing max delay cap...")
    
    policy = RetryPolicy(base_delay=2.0, max_delay=10.0)
    
    # High attempt should be capped
    delay = policy.calculate_delay(10)
    assert delay <= 10.0 * 1.25  # Allow for jitter
    
    print(f"  ✓ Delay capped at ~{policy.max_delay}s")


def test_should_retry_rules():
    """Test retry rules by error type."""
    print("Testing retry rules...")
    
    # Model error: retry up to 3
    policy = POLICY_MODEL_ERROR
    should, _ = policy.should_retry(0, Exception("timeout"))
    assert should is True
    should, _ = policy.should_retry(2, Exception("timeout"))
    assert should is False  # Max attempts
    print("  ✓ Model error: max 3 attempts")
    
    # Tool error: no retry (max_attempts=1 means no retries)
    policy = POLICY_TOOL_ERROR
    should, reason = policy.should_retry(0, Exception("file not found"))
    assert should is False
    # With max_attempts=1, the first attempt is also the last
    assert "Max attempts" in reason or "not retryable" in reason
    print("  ✓ Tool error: no retry")
    
    # Format error: max 2
    policy = POLICY_FORMAT_ERROR
    should, _ = policy.should_retry(0, Exception("invalid JSON"))
    assert should is True
    should, _ = policy.should_retry(1, Exception("invalid JSON"))
    assert should is False  # Max 2 attempts
    print("  ✓ Format error: max 2 attempts")


def test_classify_error():
    """Test error classification."""
    print("Testing error classification...")
    
    # Model errors
    assert classify_error(TimeoutError("timeout")) == ErrorType.MODEL_ERROR
    assert classify_error(Exception("rate limit exceeded")) == ErrorType.MODEL_ERROR
    print("  ✓ Model errors classified")
    
    # Tool errors
    assert classify_error(FileNotFoundError("file not found")) == ErrorType.TOOL_ERROR
    assert classify_error(PermissionError("permission denied")) == ErrorType.TOOL_ERROR
    print("  ✓ Tool errors classified")
    
    # Format errors
    assert classify_error(ValueError("invalid JSON")) == ErrorType.FORMAT_ERROR
    print("  ✓ Format errors classified")


def test_retry_with_backoff_success():
    """Test successful execution without retry."""
    print("Testing successful execution...")
    
    attempts = []
    
    def success_func():
        attempts.append(1)
        return "success"
    
    result = retry_with_backoff(success_func)
    assert result == "success"
    assert len(attempts) == 1
    print("  ✓ Success on first attempt")


def test_retry_with_backoff_eventual_success():
    """Test eventual success after retries."""
    print("Testing eventual success...")
    
    attempts = []
    
    def fail_then_succeed():
        attempts.append(1)
        if len(attempts) < 3:
            raise TimeoutError("temporary failure")
        return "success"
    
    start = time.time()
    result = retry_with_backoff(
        fail_then_succeed,
        POLICY_MODEL_ERROR,
    )
    elapsed = time.time() - start
    
    assert result == "success"
    assert len(attempts) == 3
    assert elapsed >= 2.0  # Should have delays
    print(f"  ✓ Success after {len(attempts)} attempts in {elapsed:.2f}s")


def test_retry_decorator():
    """Test retry decorator."""
    print("Testing retry decorator...")
    
    attempts = []
    
    @retry_decorator(POLICY_FORMAT_ERROR)
    def decorated_func():
        attempts.append(1)
        if len(attempts) < 2:
            raise ValueError("invalid format")
        return "success"
    
    result = decorated_func()
    assert result == "success"
    assert len(attempts) == 2
    print("  ✓ Decorator works")


def test_retry_context():
    """Test RetryContext."""
    print("Testing RetryContext...")
    
    attempts = []
    
    with RetryContext(POLICY_MODEL_ERROR) as ctx:
        for attempt in ctx:
            attempts.append(attempt)
            if attempt == 1:
                ctx.succeed()
                break
    
    assert len(attempts) == 2  # 0 and 1
    assert ctx.succeeded is True
    print("  ✓ RetryContext works")


def test_predefined_policies():
    """Test predefined policies."""
    print("Testing predefined policies...")
    
    assert POLICY_MODEL_ERROR.max_attempts == 3
    assert POLICY_TOOL_ERROR.max_attempts == 1
    assert POLICY_FORMAT_ERROR.max_attempts == 2
    
    print("  ✓ Predefined policies configured")


def run_all_tests():
    """Run all F1.7 tests."""
    print("=" * 60)
    print("F1.7 — Retry con backoff exponencial Tests")
    print("=" * 60)
    
    tests = [
        test_calculate_delay,
        test_max_delay_cap,
        test_should_retry_rules,
        test_classify_error,
        test_retry_with_backoff_success,
        test_retry_with_backoff_eventual_success,
        test_retry_decorator,
        test_retry_context,
        test_predefined_policies,
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
        print("\n🎉 F1.7 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
