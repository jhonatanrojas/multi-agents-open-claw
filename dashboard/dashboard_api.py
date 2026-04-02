"""
Dashboard API - Human Intervention Endpoints

This module defines three endpoints that give the human operator
active intervention controls over the Dev Squad multi-agent system.
The frontend components are built by PIXEL; this file documents
the API contracts.

Location: dev-squad/dashboard/dashboard_api.py
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime
import json
import os

router = APIRouter()

# ============================================================================
# Shared paths
# ============================================================================
MEMORY_JSON_PATH = "../shared/MEMORY.json"
CONTEXT_MD_PATH = "../shared/CONTEXT.md"


# ============================================================================
# Request/Response Models
# ============================================================================

class SteerRequest(BaseModel):
    """Request model for steering an active agent."""
    message: str
    """The steer message to send to the agent."""

class SteerResponse(BaseModel):
    """Response model for steer endpoint."""
    success: bool
    """Whether the steer message was sent successfully."""
    agent_id: str
    """The agent that received the message."""
    timestamp: str
    """ISO-8601 timestamp of the operation."""

class PauseRequest(BaseModel):
    """Request model for pausing/resuming a task."""
    reason: Optional[str] = None
    """Optional reason for pausing the task."""

class PauseResponse(BaseModel):
    """Response model for pause endpoint."""
    success: bool
    """Whether the task was paused/resumed successfully."""
    task_id: str
    """The task that was affected."""
    new_status: str
    """The new status of the task."""
    timestamp: str
    """ISO-8601 timestamp of the operation."""

class ContextUpdateRequest(BaseModel):
    """Request model for updating CONTEXT.md."""
    section: str
    """The section to update (e.g., 'Architecture', 'Tech Stack')."""
    content: str
    """The new content for the section."""
    reason: str
    """Reason for the change, logged in plan_history."""

class ContextUpdateResponse(BaseModel):
    """Response model for context update endpoint."""
    success: bool
    """Whether the context was updated successfully."""
    section: str
    """The section that was updated."""
    plan_version: int
    """The new plan version after the update."""
    timestamp: str
    """ISO-8601 timestamp of the operation."""


# ============================================================================
# Endpoint 1: POST /api/agents/{agent_id}/steer
# ============================================================================

@router.post("/api/agents/{agent_id}/steer", response_model=SteerResponse)
async def steer_agent(agent_id: str, request: SteerRequest):
    """
    Send a steer message to an active sub-agent session.
    
    ## Purpose
    Allows the human operator to provide guidance, corrections, or
    clarifications to an agent that is currently executing a task.
    This is useful when:
    
    - The agent is stuck or confused
    - The human wants to correct a misunderstanding
    - Additional context is needed mid-execution
    
    ## Implementation Notes
    
    1. **Validate agent exists and is active**
       - Check if `agent_id` corresponds to a spawned session
       - Agent must have status `in_progress` in its current task
       - Return 404 if agent not found, 400 if agent is idle
    
    2. **Send steer message via OpenClaw**
       - Use `sessions_send` tool or equivalent
       - Message is prefixed with `[STEER]` to distinguish from
         normal agent-to-agent communication
       - ARCH detects and processes steer messages on heartbeat
    
    3. **Log the steer event**
       - Append to MEMORY.json under `messages[]`:
         ```json
         {
           "type": "steer",
           "from": "human",
           "to": "<agent_id>",
           "message": "<request.message>",
           "timestamp": "<ISO-8601>"
         }
         ```
    
    ## Frontend Component
    
    PIXEL builds a steer input field alongside each active agent card:
    - Shows when agent status is `in_progress`
    - Input field with placeholder: "Send guidance to {agent_name}..."
    - Send button that calls this endpoint
    - Loading state while request is in flight
    - Error state with retry option if request fails
    
    ## Example Request
    
    ```json
    {
      "message": "Use the existing Button component instead of creating a new one."
    }
    ```
    
    ## Example Response
    
    ```json
    {
      "success": true,
      "agent_id": "byte-session-001",
      "timestamp": "2026-03-28T06:00:00Z"
    }
    ```
    """
    # TODO: Implement actual steer logic via OpenClaw sessions_send
    # For now, return a mock successful response
    return SteerResponse(
        success=True,
        agent_id=agent_id,
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# ============================================================================
# Endpoint 2: POST /api/tasks/{task_id}/pause
# ============================================================================

@router.post("/api/tasks/{task_id}/pause", response_model=PauseResponse)
async def pause_task(task_id: str, request: PauseRequest):
    """
    Flag a task as paused in MEMORY.json for ARCH to detect.
    
    ## Purpose
    Allows the human operator to pause a task that is in progress.
    ARCH detects paused tasks on its next heartbeat cycle and:
    
    - Does NOT spawn new tasks dependent on the paused task
    - Does NOT kill the agent working on the task (that's a separate action)
    - Logs the pause reason in MEMORY.json
    
    This is useful when:
    
    - The human needs time to review progress so far
    - External blockers need to be resolved
    - The task needs to be re-evaluated
    
    ## Implementation Notes
    
    1. **Read MEMORY.json**
       - Find the task with matching `task_id`
       - Task must have status `in_progress`
       - Return 404 if task not found, 400 if task not in progress
    
    2. **Update task status**
       - Change status to `paused`
       - Set `last_updated` to current UTC timestamp
       - Add `pause_reason` field with the provided reason
    
    3. **Log the pause event**
       - Append to MEMORY.json `messages[]`:
         ```json
         {
           "type": "task_paused",
           "task_id": "<task_id>",
           "reason": "<request.reason>",
           "paused_by": "human",
           "timestamp": "<ISO-8601>"
         }
         ```
    
    4. **ARCH heartbeat detection**
       - ARCH checks for paused tasks each heartbeat
       - ARCH holds dependent tasks in `pending`
       - ARCH does not kill the agent; human must explicitly resume
    
    ## Frontend Component
    
    PIXEL builds a pause/resume toggle on each in_progress task row:
    - Toggle button (pause icon when running, play icon when paused)
    - On pause: show reason input modal
    - Calls POST /api/tasks/{task_id}/pause
    - On resume: calls POST /api/tasks/{task_id}/resume (separate endpoint)
    - Loading state while request is in flight
    
    ## Example Request
    
    ```json
    {
      "reason": "Waiting for external API credentials to be provisioned."
    }
    ```
    
    ## Example Response
    
    ```json
    {
      "success": true,
      "task_id": "T-003",
      "new_status": "paused",
      "timestamp": "2026-03-28T06:05:00Z"
    }
    ```
    """
    # TODO: Implement actual pause logic with MEMORY.json update
    # For now, return a mock successful response
    return PauseResponse(
        success=True,
        task_id=task_id,
        new_status="paused",
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# ============================================================================
# Endpoint 3: PATCH /api/context
# ============================================================================

@router.patch("/api/context", response_model=ContextUpdateResponse)
async def update_context(request: ContextUpdateRequest):
    """
    Update a specific section of CONTEXT.md and log the change.
    
    ## Purpose
    Allows the human operator to modify the shared context that all
    agents read. Changes are versioned in plan_history to maintain
    audit trail.
    
    This is useful when:
    
    - New architectural decisions are made mid-project
    - Tech stack changes need to be communicated to all agents
    - Constraints are discovered that affect all tasks
    
    ## Implementation Notes
    
    1. **Read current CONTEXT.md**
       - Parse the markdown to find the requested section
       - Section header must match exactly (case-sensitive)
       - Return 404 if section not found
    
    2. **Update the section**
       - Replace the section content with the new content
       - Preserve section header format
       - Maintain valid markdown structure
    
    3. **Update MEMORY.json**
       - Increment `plan_version`
       - Append to `plan_history[]`:
         ```json
         {
           "version": <new_version>,
           "timestamp": "<ISO-8601>",
           "changed_tasks": [],
           "reason": "<request.reason>",
           "context_change": {
             "section": "<request.section>",
             "change_type": "context_update"
           }
         }
         ```
    
    4. **Notify agents**
       - ARCH detects context changes on next heartbeat
       - ARCH re-reads CONTEXT.md before spawning new tasks
       - Agents already running receive a context update message
    
    ## Frontend Component
    
    PIXEL builds an inline CONTEXT.md editor:
    - Read-only view of CONTEXT.md with edit buttons per section
    - Edit mode shows textarea with current section content
    - Save button calls PATCH /api/context
    - Cancel button reverts to original content
    - Reason input required before save
    - Loading state while request is in flight
    - Success/error toast notifications
    
    ## Example Request
    
    ```json
    {
      "section": "Architecture",
      "content": "This project follows a modular monolith architecture...",
      "reason": "Clarified architecture after team discussion."
    }
    ```
    
    ## Example Response
    
    ```json
    {
      "success": true,
      "section": "Architecture",
      "plan_version": 3,
      "timestamp": "2026-03-28T06:10:00Z"
    }
    ```
    """
    # TODO: Implement actual context update logic
    # For now, return a mock successful response
    return ContextUpdateResponse(
        success=True,
        section=request.section,
        plan_version=2,  # Would be incremented from MEMORY.json
        timestamp=datetime.utcnow().isoformat() + "Z"
    )


# ============================================================================
# Health Check
# ============================================================================

@router.get("/api/health")
async def health_check():
    """Health check endpoint for the dashboard API."""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat() + "Z"}
