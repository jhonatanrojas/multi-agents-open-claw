#!/usr/bin/env python3
"""
agent_memory.py - Differentiated memory per agent (F2.7)

Each agent has its own persistent memory file that accumulates
knowledge across projects.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Optional, List

# Workspace directories for each agent
AGENT_WORKSPACES = {
    "arch": Path("/root/.openclaw/workspace/workspaces/coordinator"),
    "byte": Path("/root/.openclaw/workspace/workspaces/programmer"),
    "pixel": Path("/root/.openclaw/workspace/workspaces/designer"),
    "judge": Path("/root/.openclaw/workspace/workspaces/reviewer"),
}

MEMORY_FILENAME = "MEMORY.md"


class AgentMemory:
    """
    Persistent memory for an agent.
    
    Each agent accumulates knowledge in its own MEMORY.md file.
    The supervisor injects this memory into each task as additional context.
    """
    
    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        self.workspace = AGENT_WORKSPACES.get(agent_id)
        
        if self.workspace:
            self.memory_path = self.workspace / MEMORY_FILENAME
            self._ensure_workspace()
        else:
            self.memory_path = None
    
    def _ensure_workspace(self) -> None:
        """Ensure workspace directory exists."""
        if self.workspace:
            self.workspace.mkdir(parents=True, exist_ok=True)
    
    def read(self) -> str:
        """
        Read agent memory.
        
        Returns:
            Memory content or empty string if no memory
        """
        if self.memory_path and self.memory_path.exists():
            return self.memory_path.read_text(encoding="utf-8")
        return ""
    
    def append(self, note: str, max_length: int = 500) -> None:
        """
        Append a note to agent memory.
        
        Args:
            note: Note to append (max 3 sentences as per spec)
            max_length: Maximum length of note
        """
        if not self.memory_path:
            return
        
        # Truncate if too long
        if len(note) > max_length:
            note = note[:max_length-3] + "..."
        
        # Create entry with timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        entry = f"\n- [{timestamp}] {note}\n"
        
        # Append to file
        if self.memory_path.exists():
            current = self.memory_path.read_text(encoding="utf-8")
        else:
            current = f"# {self.agent_id.upper()} Memory\n\n"
        
        self.memory_path.write_text(current + entry, encoding="utf-8")
    
    def get_context_for_task(self) -> str:
        """
        Get memory as context for a task.
        
        Returns:
            Memory formatted as context (not as main prompt)
        """
        memory = self.read()
        if not memory:
            return ""
        
        # Format as additional context
        return f"\n<!-- Agent Memory: {self.agent_id} -->\n{memory}\n<!-- End Memory -->\n"
    
    def clear(self) -> None:
        """Clear agent memory (use with caution)."""
        if self.memory_path and self.memory_path.exists():
            self.memory_path.unlink()


def get_agent_memory(agent_id: str) -> AgentMemory:
    """Get memory manager for an agent."""
    return AgentMemory(agent_id)


def append_to_agent_memory(agent_id: str, note: str) -> None:
    """Convenience function to append note to agent memory."""
    memory = get_agent_memory(agent_id)
    memory.append(note)


def get_all_agent_memories() -> dict:
    """Get all agent memories for context injection."""
    return {
        agent_id: AgentMemory(agent_id).read()
        for agent_id in AGENT_WORKSPACES.keys()
    }


__all__ = [
    "AgentMemory",
    "get_agent_memory",
    "append_to_agent_memory",
    "get_all_agent_memories",
]
