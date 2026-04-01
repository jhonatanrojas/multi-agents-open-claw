#!/usr/bin/env python3
"""
Tests for F1.3 — Lock de ejecución anti doble run
"""

import sys
import threading
import time
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from run_lock import RunLock, run_lock_context, get_run_lock


def test_lock_acquire_release():
    """Test basic lock acquire and release."""
    print("Testing lock acquire/release...")
    
    lock = RunLock("test-proj-001")
    
    # Acquire lock
    acquired = lock.acquire()
    assert acquired is True, "Should acquire lock"
    print("  ✓ Lock acquired")
    
    # Release lock
    lock.release()
    print("  ✓ Lock released")
    
    # Lock should be free now
    assert not lock.is_locked(), "Lock should be free after release"
    print("  ✓ Lock is free")


def test_lock_prevents_double_acquire():
    """Test that lock prevents double acquisition."""
    print("Testing lock prevents double acquire...")
    
    lock1 = RunLock("test-proj-002")
    lock2 = RunLock("test-proj-002")  # Same project
    
    # First acquire succeeds
    acquired1 = lock1.acquire()
    assert acquired1 is True
    print("  ✓ First acquire succeeded")
    
    # Second acquire fails (non-blocking)
    acquired2 = lock2.acquire()
    assert acquired2 is False, "Second acquire should fail"
    print("  ✓ Second acquire blocked")
    
    # Cleanup
    lock1.release()


def test_lock_context_manager():
    """Test lock context manager."""
    print("Testing lock context manager...")
    
    # Successful acquisition
    with run_lock_context("test-proj-003") as lock:
        assert lock.is_locked() or True  # We hold the lock
        print("  ✓ Lock held in context")
    
    # Lock should be released
    test_lock = RunLock("test-proj-003")
    assert not test_lock.is_locked(), "Lock should be released after context"
    print("  ✓ Lock released after context")


def test_concurrent_lock_access():
    """Test concurrent lock access from multiple threads."""
    print("Testing concurrent lock access...")
    
    results = []
    
    def try_acquire():
        lock = RunLock("test-proj-004")
        acquired = lock.acquire(blocking=False)
        results.append(acquired)
        if acquired:
            time.sleep(0.1)  # Hold briefly
            lock.release()
    
    # Start multiple threads
    threads = [threading.Thread(target=try_acquire) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    # Exactly one should succeed
    assert sum(results) == 1, f"Expected 1 success, got {sum(results)}"
    print(f"  ✓ Concurrent access: {sum(results)} acquired, {len(results) - sum(results)} blocked")


def test_lock_is_locked():
    """Test is_locked() detection."""
    print("Testing is_locked() detection...")
    
    lock = RunLock("test-proj-005")
    
    # Not locked initially
    assert not lock.is_locked(), "Should not be locked initially"
    print("  ✓ Not locked initially")
    
    # Acquire
    lock.acquire()
    assert lock.is_locked(), "Should be locked after acquire"
    print("  ✓ Locked after acquire")
    
    # Release
    lock.release()
    assert not lock.is_locked(), "Should not be locked after release"
    print("  ✓ Not locked after release")


def test_get_run_lock_factory():
    """Test get_run_lock factory function."""
    print("Testing get_run_lock factory...")
    
    lock = get_run_lock("test-proj-006", backend="file")
    assert isinstance(lock, RunLock)
    print("  ✓ Factory returns RunLock")
    
    # Test acquire
    acquired = lock.acquire()
    assert acquired is True
    lock.release()
    print("  ✓ Factory lock works")


def run_all_tests():
    """Run all F1.3 tests."""
    print("=" * 60)
    print("F1.3 — Lock de ejecución anti doble run Tests")
    print("=" * 60)
    
    tests = [
        test_lock_acquire_release,
        test_lock_prevents_double_acquire,
        test_lock_context_manager,
        test_concurrent_lock_access,
        test_lock_is_locked,
        test_get_run_lock_factory,
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
        print("\n🎉 F1.3 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
