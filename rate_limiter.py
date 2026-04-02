#!/usr/bin/env python3
"""
rate_limiter.py - Rate limiting per agent (F4.4)

Rate limiting for agent operations.
"""

import time
from typing import Dict
from dataclasses import dataclass


@dataclass
class RateLimiter:
    """Simple rate limiter per agent."""
    
    max_requests: int = 10
    window_seconds: int = 60
    
    def __post_init__(self):
        self._requests: Dict[str, list] = {}
    
    def is_allowed(self, agent_id: str) -> bool:
        """Check if request is allowed for agent."""
        now = time.time()
        
        # Get agent's request history
        requests = self._requests.get(agent_id, [])
        
        # Remove old requests outside window
        requests = [r for r in requests if now - r < self.window_seconds]
        
        # Check if under limit
        if len(requests) < self.max_requests:
            requests.append(now)
            self._requests[agent_id] = requests
            return True
        
        return False


# Global rate limiter
rate_limiter = RateLimiter()


def check_rate_limit(agent_id: str) -> bool:
    """Check if agent is within rate limit."""
    return rate_limiter.is_allowed(agent_id)


__all__ = ["RateLimiter", "rate_limiter", "check_rate_limit"]
