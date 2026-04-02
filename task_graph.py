#!/usr/bin/env python3
"""
task_graph.py - Graph as intent generator (F2.2)

The graph no longer executes logic directly. Instead, it returns
intents that the supervisor converts into tasks.
"""

from dataclasses import dataclass
from typing import Optional, List, Dict, Any
from enum import Enum

from graph_state import GraphState
from models import AgentType
from supervisor import TaskIntent


class GraphNode:
    """A node in the execution graph."""
    
    def __init__(
        self,
        state: GraphState,
        agent: AgentType,
        task_type: str,
        description: str,
        next_states: Optional[List[GraphState]] = None,
    ):
        self.state = state
        self.agent = agent
        self.task_type = task_type
        self.description = description
        self.next_states = next_states or []
    
    def generate_intent(
        self,
        context: Optional[Dict[str, Any]] = None
    ) -> TaskIntent:
        """
        Generate a TaskIntent for this node.
        
        Args:
            context: Additional context for intent generation
        
        Returns:
            TaskIntent for the supervisor
        """
        # Determine next state
        next_stage = self.next_states[0] if self.next_states else GraphState.COMPLETED
        
        return TaskIntent(
            next_stage=next_stage,
            required_agent=self.agent,
            task_type=self.task_type,
            description=self.description,
            input_data=context,
        )


class TaskGraph:
    """
    Execution graph that generates task intents.
    
    The graph defines the workflow but doesn't execute it.
    Execution is handled by the supervisor.
    """
    
    def __init__(self):
        self.nodes: Dict[GraphState, GraphNode] = {}
        self._build_graph()
    
    def _build_graph(self):
        """Build the default execution graph."""
        # Discovery → Planning
        self.nodes[GraphState.DISCOVERY] = GraphNode(
            state=GraphState.DISCOVERY,
            agent=AgentType.ARCH,
            task_type="analysis",
            description="Analyze requirements and discover scope",
            next_states=[GraphState.PLANNING],
        )
        
        # Planning → Executing
        self.nodes[GraphState.PLANNING] = GraphNode(
            state=GraphState.PLANNING,
            agent=AgentType.ARCH,
            task_type="design",
            description="Create implementation plan",
            next_states=[GraphState.EXECUTING],
        )
        
        # Executing → Implementation
        self.nodes[GraphState.EXECUTING] = GraphNode(
            state=GraphState.EXECUTING,
            agent=AgentType.BYTE,
            task_type="coding",
            description="Execute implementation tasks",
            next_states=[GraphState.IMPLEMENTATION],
        )
        
        # Implementation → Review
        self.nodes[GraphState.IMPLEMENTATION] = GraphNode(
            state=GraphState.IMPLEMENTATION,
            agent=AgentType.BYTE,
            task_type="coding",
            description="Implement features and fixes",
            next_states=[GraphState.REVIEW],
        )
        
        # Review → Completed
        self.nodes[GraphState.REVIEW] = GraphNode(
            state=GraphState.REVIEW,
            agent=AgentType.PIXEL,
            task_type="review",
            description="Review implementation for quality",
            next_states=[GraphState.COMPLETED],
        )
    
    def get_intent_for_state(
        self,
        state: GraphState,
        context: Optional[Dict[str, Any]] = None
    ) -> Optional[TaskIntent]:
        """
        Get task intent for a given state.
        
        Args:
            state: Current graph state
            context: Additional context
        
        Returns:
            TaskIntent or None if state not in graph
        """
        node = self.nodes.get(state)
        if node:
            return node.generate_intent(context)
        return None
    
    def get_next_states(self, state: GraphState) -> List[GraphState]:
        """Get possible next states from current state."""
        node = self.nodes.get(state)
        if node:
            return node.next_states
        return []


# Global task graph instance
task_graph = TaskGraph()


__all__ = [
    "GraphNode",
    "TaskGraph",
    "task_graph",
]
