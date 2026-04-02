#!/usr/bin/env python3
"""
graph_state.py - Normalized graph states (F1.5)

This module defines explicit graph states as Python enums.
No code should use string literals to refer to graph states.

Usage:
    from graph_state import GraphState
    
    current_state = GraphState.DISCOVERY
    if current_state == GraphState.EXECUTING:
        pass
    
    # Convert from string (e.g., from DB)
    state = GraphState("discovery")  # Returns GraphState.DISCOVERY
"""

from enum import Enum
from typing import Optional


class GraphState(str, Enum):
    """
    Explicit graph states for the multi-agent system.
    
    These states represent the phases of execution in the agent workflow.
    Never use string literals - always use these enum values.
    """
    
    # Initial phases
    DISCOVERY = "discovery"
    PLANNING = "planning"
    
    # Execution phases
    EXECUTING = "executing"
    IMPLEMENTATION = "implementation"
    REVIEW = "review"
    
    # Qualification and recommendation
    QUALIFICATION = "qualification"
    RECOMMENDATION = "recommendation"
    
    # Discussion and negotiation
    PRICE_DISCUSSION = "price_discussion"
    NEGOTIATION = "negotiation"
    
    # Intent and completion
    PURCHASE_INTENT = "purchase_intent"
    CHECKOUT = "checkout"
    POST_SALE = "post_sale"
    
    # Exception states
    ESCALATE = "escalate"
    BLOCKED = "blocked"
    PAUSED = "paused"
    
    # Terminal states
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    
    @classmethod
    def from_string(cls, value: str) -> Optional["GraphState"]:
        """
        Convert string to GraphState enum.
        
        Args:
            value: String representation of state
        
        Returns:
            GraphState enum or None if invalid
        """
        try:
            return cls(value.lower())
        except ValueError:
            return None
    
    @classmethod
    def is_terminal(cls, state: "GraphState") -> bool:
        """Check if state is terminal (completed, failed, cancelled)."""
        return state in {cls.COMPLETED, cls.FAILED, cls.CANCELLED}
    
    @classmethod
    def is_blocked(cls, state: "GraphState") -> bool:
        """Check if state represents a blocker."""
        return state in {cls.BLOCKED, cls.ESCALATE}
    
    @classmethod
    def can_transition_to(cls, from_state: "GraphState", to_state: "GraphState") -> bool:
        """
        Check if transition between states is valid.
        
        Args:
            from_state: Current state
            to_state: Desired next state
        
        Returns:
            True if transition is valid
        """
        # Terminal states cannot transition
        if cls.is_terminal(from_state):
            return False
        
        # Can always transition to blocked/paused
        if to_state in {cls.BLOCKED, cls.PAUSED}:
            return True
        
        # Can resume from blocked/paused to executing
        if from_state in {cls.BLOCKED, cls.PAUSED} and to_state == cls.EXECUTING:
            return True
        
        # Define valid transitions
        valid_transitions = {
            cls.DISCOVERY: {cls.PLANNING, cls.EXECUTING},
            cls.PLANNING: {cls.EXECUTING, cls.IMPLEMENTATION},
            cls.EXECUTING: {cls.REVIEW, cls.IMPLEMENTATION, cls.COMPLETED},
            cls.IMPLEMENTATION: {cls.REVIEW, cls.EXECUTING},
            cls.REVIEW: {cls.EXECUTING, cls.COMPLETED, cls.FAILED},
            cls.QUALIFICATION: {cls.RECOMMENDATION, cls.NEGOTIATION},
            cls.RECOMMENDATION: {cls.PRICE_DISCUSSION, cls.NEGOTIATION},
            cls.PRICE_DISCUSSION: {cls.NEGOTIATION, cls.PURCHASE_INTENT},
            cls.NEGOTIATION: {cls.PURCHASE_INTENT, cls.CHECKOUT},
            cls.PURCHASE_INTENT: {cls.CHECKOUT},
            cls.CHECKOUT: {cls.POST_SALE, cls.COMPLETED},
            cls.POST_SALE: {cls.COMPLETED},
            cls.ESCALATE: {cls.EXECUTING, cls.BLOCKED},
        }
        
        allowed = valid_transitions.get(from_state, set())
        return to_state in allowed
    
    def get_display_name(self) -> str:
        """Get human-readable display name for this state."""
        display_names = {
            GraphState.DISCOVERY: "Discovery",
            GraphState.PLANNING: "Planning",
            GraphState.EXECUTING: "Executing",
            GraphState.IMPLEMENTATION: "Implementation",
            GraphState.REVIEW: "Review",
            GraphState.QUALIFICATION: "Qualification",
            GraphState.RECOMMENDATION: "Recommendation",
            GraphState.PRICE_DISCUSSION: "Price Discussion",
            GraphState.NEGOTIATION: "Negotiation",
            GraphState.PURCHASE_INTENT: "Purchase Intent",
            GraphState.CHECKOUT: "Checkout",
            GraphState.POST_SALE: "Post-Sale",
            GraphState.ESCALATE: "Escalated",
            GraphState.BLOCKED: "Blocked",
            GraphState.PAUSED: "Paused",
            GraphState.COMPLETED: "Completed",
            GraphState.FAILED: "Failed",
            GraphState.CANCELLED: "Cancelled",
        }
        return display_names.get(self, self.value)
    
    def get_color(self) -> str:
        """Get color code for UI display."""
        colors = {
            GraphState.DISCOVERY: "blue",
            GraphState.PLANNING: "purple",
            GraphState.EXECUTING: "green",
            GraphState.IMPLEMENTATION: "orange",
            GraphState.REVIEW: "yellow",
            GraphState.QUALIFICATION: "blue",
            GraphState.RECOMMENDATION: "cyan",
            GraphState.PRICE_DISCUSSION: "orange",
            GraphState.NEGOTIATION: "purple",
            GraphState.PURCHASE_INTENT: "green",
            GraphState.CHECKOUT: "green",
            GraphState.POST_SALE: "blue",
            GraphState.ESCALATE: "red",
            GraphState.BLOCKED: "red",
            GraphState.PAUSED: "gray",
            GraphState.COMPLETED: "green",
            GraphState.FAILED: "red",
            GraphState.CANCELLED: "gray",
        }
        return colors.get(self, "gray")


# Aliases for common state groupings
ACTIVE_STATES = {
    GraphState.DISCOVERY,
    GraphState.PLANNING,
    GraphState.EXECUTING,
    GraphState.IMPLEMENTATION,
    GraphState.REVIEW,
    GraphState.QUALIFICATION,
    GraphState.RECOMMENDATION,
    GraphState.PRICE_DISCUSSION,
    GraphState.NEGOTIATION,
    GraphState.PURCHASE_INTENT,
    GraphState.CHECKOUT,
    GraphState.POST_SALE,
}

TERMINAL_STATES = {
    GraphState.COMPLETED,
    GraphState.FAILED,
    GraphState.CANCELLED,
}

BLOCKED_STATES = {
    GraphState.BLOCKED,
    GraphState.PAUSED,
    GraphState.ESCALATE,
}


def validate_state_transition(
    current_state: Optional[str],
    new_state: str
) -> tuple[bool, Optional[str]]:
    """
    Validate a state transition.
    
    Args:
        current_state: Current state (can be None for initial state)
        new_state: Desired new state
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Parse states
    current = GraphState.from_string(current_state) if current_state else None
    new = GraphState.from_string(new_state)
    
    if new is None:
        return False, f"Invalid state: {new_state}"
    
    # Initial state is always valid
    if current is None:
        return True, None
    
    # Check transition
    if GraphState.can_transition_to(current, new):
        return True, None
    
    return False, f"Cannot transition from {current.value} to {new.value}"


__all__ = [
    "GraphState",
    "ACTIVE_STATES",
    "TERMINAL_STATES",
    "BLOCKED_STATES",
    "validate_state_transition",
]
