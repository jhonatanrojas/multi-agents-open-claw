#!/usr/bin/env python3
"""
circuit_breaker.py - Circuit breaker per agent (F1.6)

Prevents assigning tasks to agents that are failing repeatedly.

Usage:
    from circuit_breaker import AgentCircuitBreaker, CircuitBreakerRegistry
    
    # Register an agent
    cb = CircuitBreakerRegistry.get("byte")
    
    # Check if available
    if cb.is_available():
        assign_task(agent_id="byte", ...)
    else:
        # Agent in cooldown, route to alternative
        pass
    
    # Record failure
    cb.record_failure()
    
    # Record success (resets failures)
    cb.record_success()
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any
from threading import Lock

# State file for persistence across restarts
STATE_DIR = Path("/tmp/openclaw-circuit-breakers")
STATE_DIR.mkdir(exist_ok=True)
STATE_FILE = STATE_DIR / "circuit_breaker_state.json"


class AgentCircuitBreaker:
    """
    Circuit breaker for a single agent.
    
    Tracks failures and enters cooldown after threshold is reached.
    """
    
    def __init__(
        self,
        agent_id: str,
        threshold: int = 3,
        cooldown_seconds: int = 300,  # 5 minutes default
    ):
        self.agent_id = agent_id
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        
        self.failures = 0
        self.cooldown_until: Optional[datetime] = None
        self.last_failure: Optional[datetime] = None
        self.last_success: Optional[datetime] = None
        
        # Try to load persisted state
        self._load_state()
    
    def record_failure(self) -> None:
        """Record a failure for this agent."""
        self.failures += 1
        self.last_failure = datetime.utcnow()
        
        if self.failures >= self.threshold:
            self.cooldown_until = datetime.utcnow() + timedelta(seconds=self.cooldown_seconds)
        
        self._save_state()
    
    def record_success(self) -> None:
        """Record a success - resets failure count."""
        self.failures = 0
        self.cooldown_until = None
        self.last_success = datetime.utcnow()
        self._save_state()
    
    def is_available(self) -> bool:
        """
        Check if agent is available for task assignment.
        
        Returns:
            True if agent can receive tasks, False if in cooldown
        """
        if self.cooldown_until is None:
            return True
        
        # Check if cooldown has expired
        if datetime.utcnow() >= self.cooldown_until:
            # Auto-reset after cooldown
            self.cooldown_until = None
            self.failures = 0
            self._save_state()
            return True
        
        return False
    
    def get_state(self) -> Dict[str, Any]:
        """Get current circuit breaker state for monitoring."""
        return {
            "agent_id": self.agent_id,
            "failures": self.failures,
            "threshold": self.threshold,
            "is_available": self.is_available(),
            "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
            "cooldown_remaining_seconds": self._get_cooldown_remaining(),
            "last_failure": self.last_failure.isoformat() if self.last_failure else None,
            "last_success": self.last_success.isoformat() if self.last_success else None,
        }
    
    def _get_cooldown_remaining(self) -> int:
        """Get remaining cooldown seconds."""
        if self.cooldown_until is None:
            return 0
        
        remaining = (self.cooldown_until - datetime.utcnow()).total_seconds()
        return max(0, int(remaining))
    
    def _load_state(self) -> None:
        """Load state from persistence file."""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, 'r') as f:
                    all_states = json.load(f)
                
                agent_state = all_states.get(self.agent_id, {})
                self.failures = agent_state.get("failures", 0)
                
                cooldown_str = agent_state.get("cooldown_until")
                if cooldown_str:
                    self.cooldown_until = datetime.fromisoformat(cooldown_str)
                
                last_failure_str = agent_state.get("last_failure")
                if last_failure_str:
                    self.last_failure = datetime.fromisoformat(last_failure_str)
                
                last_success_str = agent_state.get("last_success")
                if last_success_str:
                    self.last_success = datetime.fromisoformat(last_success_str)
        except Exception:
            # Ignore load errors, start fresh
            pass
    
    def _save_state(self) -> None:
        """Save state to persistence file."""
        try:
            all_states = {}
            if STATE_FILE.exists():
                with open(STATE_FILE, 'r') as f:
                    all_states = json.load(f)
            
            all_states[self.agent_id] = {
                "failures": self.failures,
                "cooldown_until": self.cooldown_until.isoformat() if self.cooldown_until else None,
                "last_failure": self.last_failure.isoformat() if self.last_failure else None,
                "last_success": self.last_success.isoformat() if self.last_success else None,
            }
            
            with open(STATE_FILE, 'w') as f:
                json.dump(all_states, f, indent=2)
        except Exception:
            # Ignore save errors
            pass
    
    def __repr__(self) -> str:
        status = "available" if self.is_available() else "cooldown"
        return f"<AgentCircuitBreaker({self.agent_id}, {status}, failures={self.failures})>"


class CircuitBreakerRegistry:
    """
    Registry for all agent circuit breakers.
    
    Provides centralized access to circuit breaker instances.
    """
    
    _instance = None
    _lock = Lock()
    _breakers: Dict[str, AgentCircuitBreaker] = {}
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def get(
        cls,
        agent_id: str,
        threshold: int = 3,
        cooldown_seconds: int = 300
    ) -> AgentCircuitBreaker:
        """
        Get or create circuit breaker for an agent.
        
        Args:
            agent_id: Agent identifier
            threshold: Failure threshold before cooldown
            cooldown_seconds: Cooldown duration
        
        Returns:
            AgentCircuitBreaker instance
        """
        with cls._lock:
            if agent_id not in cls._breakers:
                cls._breakers[agent_id] = AgentCircuitBreaker(
                    agent_id=agent_id,
                    threshold=threshold,
                    cooldown_seconds=cooldown_seconds,
                )
            return cls._breakers[agent_id]
    
    @classmethod
    def get_all_states(cls) -> Dict[str, Dict[str, Any]]:
        """Get states of all circuit breakers."""
        with cls._lock:
            return {
                agent_id: cb.get_state()
                for agent_id, cb in cls._breakers.items()
            }
    
    @classmethod
    def reset_all(cls) -> None:
        """Reset all circuit breakers."""
        with cls._lock:
            for cb in cls._breakers.values():
                cb.record_success()
    
    @classmethod
    def clear_all(cls) -> None:
        """Clear all circuit breakers state (for testing)."""
        with cls._lock:
            cls._breakers.clear()
            # Also clear persisted state file
            try:
                if STATE_FILE.exists():
                    STATE_FILE.unlink()
            except Exception:
                pass
    
    @classmethod
    def get_available_agents(cls, agent_ids: list[str]) -> list[str]:
        """
        Filter list of agents to only those available.
        
        Args:
            agent_ids: List of agent IDs to check
        
        Returns:
            List of available agent IDs
        """
        available = []
        for agent_id in agent_ids:
            cb = cls.get(agent_id)
            if cb.is_available():
                available.append(agent_id)
        return available


# Convenience functions
def record_agent_failure(agent_id: str) -> None:
    """Record a failure for an agent."""
    CircuitBreakerRegistry.get(agent_id).record_failure()


def record_agent_success(agent_id: str) -> None:
    """Record a success for an agent."""
    CircuitBreakerRegistry.get(agent_id).record_success()


def is_agent_available(agent_id: str) -> bool:
    """Check if an agent is available."""
    return CircuitBreakerRegistry.get(agent_id).is_available()


def get_circuit_breaker_status() -> Dict[str, Any]:
    """Get status for all circuit breakers (for /health endpoint)."""
    return {
        "circuit_breakers": CircuitBreakerRegistry.get_all_states(),
        "timestamp": datetime.utcnow().isoformat(),
    }


__all__ = [
    "AgentCircuitBreaker",
    "CircuitBreakerRegistry",
    "record_agent_failure",
    "record_agent_success",
    "is_agent_available",
    "get_circuit_breaker_status",
]
