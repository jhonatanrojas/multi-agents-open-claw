#!/usr/bin/env python3
"""
retry_policy.py - Retry with exponential backoff (F1.7)

Provides retry mechanisms with exponential backoff and type-specific rules.

Usage:
    from retry_policy import RetryPolicy, retry_with_backoff, ErrorType
    
    # Define retry policy
    policy = RetryPolicy(
        max_attempts=3,
        base_delay=2.0,
        max_delay=60.0,
        error_type=ErrorType.MODEL_ERROR
    )
    
    # Execute with retry
    result = retry_with_backoff(
        func=my_function,
        policy=policy,
        args=(arg1, arg2),
        kwargs={"key": "value"}
    )
"""

import time
import random
from enum import Enum, auto
from dataclasses import dataclass
from typing import Callable, Any, Optional, Type, Tuple
from functools import wraps


class ErrorType(Enum):
    """Types of errors with specific retry rules."""
    MODEL_ERROR = auto()        # timeout, rate limit → retry with backoff, max 3
    TOOL_ERROR = auto()         # file not found → no retry, mark blocked
    FORMAT_ERROR = auto()       # invalid JSON → retry with different prompt, max 2
    VALIDATION_ERROR = auto()   # output validation failed → retry, max 2
    NETWORK_ERROR = auto()      # connection issues → retry with backoff, max 3
    UNKNOWN_ERROR = auto()      # unknown → retry once, then escalate


@dataclass
class RetryPolicy:
    """
    Retry policy configuration.
    
    Attributes:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        max_delay: Maximum delay in seconds
        error_type: Type of error for specific retry rules
        exponential_base: Base for exponential calculation (default 2.0)
        jitter: Add random jitter to prevent thundering herd (default True)
    """
    max_attempts: int = 3
    base_delay: float = 2.0
    max_delay: float = 60.0
    error_type: ErrorType = ErrorType.UNKNOWN_ERROR
    exponential_base: float = 2.0
    jitter: bool = True
    
    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a specific attempt using exponential backoff.
        
        Args:
            attempt: Attempt number (0-indexed)
        
        Returns:
            Delay in seconds
        """
        # Exponential: base * (exponential_base ^ attempt)
        delay = self.base_delay * (self.exponential_base ** attempt)
        
        # Cap at max_delay
        delay = min(delay, self.max_delay)
        
        # Add jitter (±25%) to prevent thundering herd
        if self.jitter:
            delay = delay * (0.75 + random.random() * 0.5)
        
        return delay
    
    def should_retry(self, attempt: int, error: Exception) -> Tuple[bool, Optional[str]]:
        """
        Determine if retry should be attempted based on policy and error type.
        
        Args:
            attempt: Current attempt number (0-indexed)
            error: The exception that occurred
        
        Returns:
            Tuple of (should_retry, reason_if_not)
        """
        # Check max attempts
        if attempt >= self.max_attempts - 1:
            return False, f"Max attempts ({self.max_attempts}) reached"
        
        # Type-specific rules
        if self.error_type == ErrorType.TOOL_ERROR:
            # Tool errors (file not found, etc.) should not retry
            return False, "Tool errors are not retryable"
        
        if self.error_type == ErrorType.FORMAT_ERROR and attempt >= 1:
            # Format errors: max 2 attempts
            return False, "Format errors: max 2 attempts"
        
        if self.error_type == ErrorType.UNKNOWN_ERROR and attempt >= 0:
            # Unknown errors: retry once only
            return False, "Unknown errors: retry once only"
        
        return True, None


# Predefined policies for common scenarios
POLICY_MODEL_ERROR = RetryPolicy(
    max_attempts=3,
    base_delay=2.0,
    max_delay=60.0,
    error_type=ErrorType.MODEL_ERROR,
)

POLICY_TOOL_ERROR = RetryPolicy(
    max_attempts=1,  # No retry
    error_type=ErrorType.TOOL_ERROR,
)

POLICY_FORMAT_ERROR = RetryPolicy(
    max_attempts=2,
    base_delay=1.0,
    max_delay=10.0,
    error_type=ErrorType.FORMAT_ERROR,
)

POLICY_NETWORK_ERROR = RetryPolicy(
    max_attempts=3,
    base_delay=2.0,
    max_delay=60.0,
    error_type=ErrorType.NETWORK_ERROR,
)

POLICY_UNKNOWN_ERROR = RetryPolicy(
    max_attempts=2,
    base_delay=2.0,
    max_delay=30.0,
    error_type=ErrorType.UNKNOWN_ERROR,
)


def classify_error(error: Exception) -> ErrorType:
    """
    Classify an exception into an ErrorType.
    
    Args:
        error: The exception to classify
    
    Returns:
        ErrorType classification
    """
    error_str = str(error).lower()
    error_type = type(error).__name__.lower()
    
    # Model errors
    if any(kw in error_str for kw in ["timeout", "rate limit", "rate_limit", "quota"]):
        return ErrorType.MODEL_ERROR
    
    if error_type in ["timeouterror", "asynciotimeouterror"]:
        return ErrorType.MODEL_ERROR
    
    # Network errors
    if any(kw in error_str for kw in ["connection", "network", "unreachable", "refused"]):
        return ErrorType.NETWORK_ERROR
    
    # Tool errors
    if any(kw in error_str for kw in ["file not found", "filenotfound", "no such file", "permission denied"]):
        return ErrorType.TOOL_ERROR
    
    # Format errors
    if any(kw in error_str for kw in ["json", "parse", "format", "invalid", "decode", "encoding"]):
        return ErrorType.FORMAT_ERROR
    
    # Validation errors
    if any(kw in error_str for kw in ["validation", "schema", "constraint", "required"]):
        return ErrorType.VALIDATION_ERROR
    
    return ErrorType.UNKNOWN_ERROR


def retry_with_backoff(
    func: Callable,
    policy: Optional[RetryPolicy] = None,
    args: tuple = (),
    kwargs: Optional[dict] = None,
    on_retry: Optional[Callable[[int, Exception, float], None]] = None,
) -> Any:
    """
    Execute a function with retry and exponential backoff.
    
    Args:
        func: Function to execute
        policy: Retry policy (uses default if None)
        args: Positional arguments for function
        kwargs: Keyword arguments for function
        on_retry: Callback function(attempt, error, delay) called on each retry
    
    Returns:
        Function result
    
    Raises:
        Exception: Last exception if all retries exhausted
    """
    if policy is None:
        policy = POLICY_UNKNOWN_ERROR
    
    if kwargs is None:
        kwargs = {}
    
    last_error = None
    
    for attempt in range(policy.max_attempts):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_error = e
            
            # Classify error if policy is auto
            if policy.error_type == ErrorType.UNKNOWN_ERROR:
                detected_type = classify_error(e)
                if detected_type != ErrorType.UNKNOWN_ERROR:
                    # Create new policy with detected type
                    policy = RetryPolicy(
                        max_attempts=policy.max_attempts,
                        base_delay=policy.base_delay,
                        max_delay=policy.max_delay,
                        error_type=detected_type,
                    )
            
            # Check if should retry
            should_retry, reason = policy.should_retry(attempt, e)
            
            if not should_retry:
                # Log why we're not retrying
                raise type(e)(f"{e} (not retrying: {reason})") from e
            
            # Calculate delay
            delay = policy.calculate_delay(attempt)
            
            # Call retry callback if provided
            if on_retry:
                on_retry(attempt, e, delay)
            
            # Sleep before retry
            time.sleep(delay)
    
    # All retries exhausted
    raise last_error


def retry_decorator(policy: Optional[RetryPolicy] = None):
    """
    Decorator for retry with exponential backoff.
    
    Usage:
        @retry_decorator(POLICY_MODEL_ERROR)
        def my_function():
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return retry_with_backoff(func, policy, args, kwargs)
        return wrapper
    return decorator


class RetryContext:
    """
    Context manager for retry operations with state tracking.
    
    Usage:
        with RetryContext(POLICY_MODEL_ERROR) as retry_ctx:
            for attempt in retry_ctx:
                try:
                    result = do_something()
                    retry_ctx.succeed()
                    return result
                except Exception as e:
                    retry_ctx.fail(e)
    """
    
    def __init__(self, policy: Optional[RetryPolicy] = None):
        self.policy = policy or POLICY_UNKNOWN_ERROR
        self.attempt = 0
        self.errors = []
        self.succeeded = False
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.succeeded and exc_val is None:
            # Context exited without success or exception
            raise RuntimeError("RetryContext exited without calling succeed()")
    
    def __iter__(self):
        return self
    
    def __next__(self):
        if self.attempt >= self.policy.max_attempts:
            # All attempts exhausted
            if self.errors:
                raise self.errors[-1]
            raise StopIteration
        
        if self.attempt > 0:
            # Delay before retry
            delay = self.policy.calculate_delay(self.attempt - 1)
            time.sleep(delay)
        
        current_attempt = self.attempt
        self.attempt += 1
        return current_attempt
    
    def succeed(self):
        """Mark the operation as successful."""
        self.succeeded = True
    
    def fail(self, error: Exception):
        """Mark an attempt as failed."""
        self.errors.append(error)
        
        # Check if should continue
        should_retry, reason = self.policy.should_retry(self.attempt - 1, error)
        if not should_retry:
            raise type(error)(f"{error} (not retrying: {reason})") from error


__all__ = [
    "ErrorType",
    "RetryPolicy",
    "POLICY_MODEL_ERROR",
    "POLICY_TOOL_ERROR",
    "POLICY_FORMAT_ERROR",
    "POLICY_NETWORK_ERROR",
    "POLICY_UNKNOWN_ERROR",
    "classify_error",
    "retry_with_backoff",
    "retry_decorator",
    "RetryContext",
]
