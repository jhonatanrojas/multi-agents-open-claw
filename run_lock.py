"""
run_lock.py - Execution lock to prevent double runs (F1.3)

This module provides locking mechanisms to prevent concurrent execution
of the same project. Supports file-based and Redis-based locking.

Usage:
    from run_lock import RunLock, get_run_lock
    
    lock = RunLock("proj-001")
    if lock.acquire():
        try:
            # Execute run
            pass
        finally:
            lock.release()
    else:
        # Another run is active
        raise HTTPException(409, "Run already active")
"""

import os
import fcntl
import tempfile
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

# Base directory for lock files
LOCK_DIR = Path(tempfile.gettempdir()) / "openclaw-locks"
LOCK_DIR.mkdir(exist_ok=True)


class RunLock:
    """
    File-based run lock using POSIX fcntl.
    
    Prevents concurrent execution of the same project.
    """
    
    def __init__(self, project_id: str):
        self.project_id = project_id
        self.lock_path = LOCK_DIR / f"run-lock-{project_id}.lock"
        self._file: Optional[file] = None
        self._acquired = False
    
    def acquire(self, blocking: bool = False) -> bool:
        """
        Acquire the lock.
        
        Args:
            blocking: If True, block until lock is available
        
        Returns:
            True if lock acquired, False otherwise
        """
        try:
            self._file = open(self.lock_path, 'w')
            
            if blocking:
                # Blocking lock
                fcntl.flock(self._file, fcntl.LOCK_EX)
            else:
                # Non-blocking lock
                fcntl.flock(self._file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            
            # Write PID to file for debugging
            self._file.write(str(os.getpid()))
            self._file.flush()
            
            self._acquired = True
            return True
            
        except (OSError, IOError):
            # Lock already held
            if self._file:
                self._file.close()
                self._file = None
            return False
    
    def release(self) -> None:
        """Release the lock."""
        if self._acquired and self._file:
            try:
                fcntl.flock(self._file, fcntl.LOCK_UN)
                self._file.close()
                
                # Clean up lock file
                try:
                    self.lock_path.unlink()
                except FileNotFoundError:
                    pass
                    
            except Exception:
                pass
            finally:
                self._file = None
                self._acquired = False
    
    def is_locked(self) -> bool:
        """Check if lock is currently held (by anyone)."""
        if not self.lock_path.exists():
            return False
        
        # Try to acquire non-blocking
        try:
            with open(self.lock_path, 'r') as f:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                # We got the lock, so it wasn't locked
                fcntl.flock(f, fcntl.LOCK_UN)
                return False
        except (OSError, IOError):
            # Lock is held by someone else
            return True
    
    def get_holder_pid(self) -> Optional[int]:
        """Get PID of current lock holder (if available)."""
        if not self.lock_path.exists():
            return None
        
        try:
            with open(self.lock_path, 'r') as f:
                content = f.read().strip()
                return int(content) if content else None
        except (ValueError, IOError):
            return None
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError(f"Could not acquire lock for {self.project_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


class RedisRunLock:
    """
    Redis-based distributed run lock.
    
    Use when RUN_LOCK_BACKEND=redis is configured.
    """
    
    def __init__(self, project_id: str, redis_client=None, ttl_seconds: int = 300):
        self.project_id = project_id
        self.lock_key = f"run-lock:{project_id}"
        self.ttl_seconds = ttl_seconds
        self._redis = redis_client
        self._acquired = False
    
    def _get_redis(self):
        """Lazy load Redis client."""
        if self._redis is None:
            import redis
            from config import config
            
            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self._redis = redis.from_url(redis_url, decode_responses=True)
        return self._redis
    
    def acquire(self) -> bool:
        """Acquire Redis lock."""
        try:
            r = self._get_redis()
            # SET NX (only if not exists) with TTL
            result = r.set(
                self.lock_key,
                str(os.getpid()),
                nx=True,  # Only if not exists
                ex=self.ttl_seconds
            )
            self._acquired = result is not None
            return self._acquired
        except Exception:
            # Redis unavailable, fallback to file lock
            return False
    
    def release(self) -> None:
        """Release Redis lock."""
        if self._acquired:
            try:
                r = self._get_redis()
                # Only delete if we own it
                current = r.get(self.lock_key)
                if current and int(current) == os.getpid():
                    r.delete(self.lock_key)
            except Exception:
                pass
            finally:
                self._acquired = False
    
    def is_locked(self) -> bool:
        """Check if lock exists in Redis."""
        try:
            r = self._get_redis()
            return r.exists(self.lock_key) > 0
        except Exception:
            return False
    
    def __enter__(self):
        """Context manager entry."""
        if not self.acquire():
            raise RuntimeError(f"Could not acquire Redis lock for {self.project_id}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.release()


def get_run_lock(project_id: str, backend: str = "auto") -> RunLock:
    """
    Factory function to get appropriate lock implementation.
    
    Args:
        project_id: The project to lock
        backend: "auto", "file", or "redis"
    
    Returns:
        RunLock instance
    """
    import os
    
    if backend == "auto":
        backend = os.getenv("RUN_LOCK_BACKEND", "file")
    
    if backend == "redis":
        try:
            return RedisRunLock(project_id)
        except Exception:
            # Fallback to file lock
            pass
    
    return RunLock(project_id)


@contextmanager
def run_lock_context(project_id: str, backend: str = "auto"):
    """
    Context manager for run locks.
    
    Usage:
        with run_lock_context("proj-001"):
            # Run is protected by lock
            execute_run()
    
    Raises:
        RuntimeError: If lock cannot be acquired
    """
    lock = get_run_lock(project_id, backend)
    try:
        if not lock.acquire():
            raise RuntimeError(f"Run already active for project {project_id}")
        yield lock
    finally:
        lock.release()


__all__ = [
    "RunLock",
    "RedisRunLock",
    "get_run_lock",
    "run_lock_context",
]
