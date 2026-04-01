#!/usr/bin/env python3
"""
action_envelope.py - Output canonicalization and action repair (F1.8)

Normalizes and repairs agent output to ensure valid ActionEnvelope format.

Usage:
    from action_envelope import canonicalize_output, parse_action
    
    # Canonicalize raw agent output
    output = canonicalize_output(raw_text)
    
    # Parse into ActionEnvelope
    action = parse_action(output)
"""

import json
import re
from dataclasses import dataclass
from typing import Optional, Dict, Any, Union
from enum import Enum


class ActionType(str, Enum):
    """Valid action types."""
    CREATE_FILE = "create_file"
    EDIT_FILE = "edit_file"
    RUN_COMMAND = "run_command"
    ASK_USER = "ask_user"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ActionEnvelope:
    """
    Canonical action envelope format.
    
    All agent outputs are normalized to this structure.
    """
    action: ActionType
    payload: Dict[str, Any]
    reasoning: Optional[str] = None
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value if isinstance(self.action, ActionType) else self.action,
            "payload": self.payload,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ActionEnvelope":
        action_str = data.get("action", "error")
        try:
            action = ActionType(action_str)
        except ValueError:
            action = ActionType.ERROR
        
        return cls(
            action=action,
            payload=data.get("payload", {}),
            reasoning=data.get("reasoning"),
            confidence=data.get("confidence", 1.0),
        )


def canonicalize_output(text: str) -> str:
    """
    Canonicalize raw agent output.
    
    Steps:
    1. Strip whitespace
    2. Remove markdown code block wrappers if present
    3. Normalize line endings
    4. Fix common formatting issues
    
    Args:
        text: Raw agent output
    
    Returns:
        Canonicalized text
    """
    if not text:
        return ""
    
    # Strip whitespace
    text = text.strip()
    
    # Remove markdown code blocks
    # ```json ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    
    return text


def repair_json(text: str) -> Optional[str]:
    """
    Attempt to repair malformed JSON.
    
    Common issues fixed:
    - Trailing commas
    - Unquoted keys
    - Single quotes instead of double
    - Missing closing braces/brackets
    
    Args:
        text: Potentially malformed JSON
    
    Returns:
        Repaired JSON string or None if unrepairable
    """
    if not text:
        return None
    
    # Try parsing as-is first
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass
    
    # Fix 1: Remove trailing commas before } or ]
    repaired = re.sub(r',(\s*[}\]])', r'\1', text)
    
    # Fix 2: Replace single quotes with double quotes (careful!)
    # Only for JSON keys and string values
    # This is a simplified version
    repaired = re.sub(r"'([^']+)'\s*:", r'"\1":', repaired)  # Keys
    repaired = re.sub(r":\s*'([^']*)'", r': "\1"', repaired)  # String values
    
    # Fix 3: Add missing closing braces
    open_braces = repaired.count("{") - repaired.count("}")
    open_brackets = repaired.count("[") - repaired.count("]")
    
    repaired += "}" * open_braces
    repaired += "]" * open_brackets
    
    # Try parsing again
    try:
        json.loads(repaired)
        return repaired
    except json.JSONDecodeError:
        return None


def extract_json(text: str) -> Optional[str]:
    """
    Extract JSON from text that may contain other content.
    
    Args:
        text: Text that may contain embedded JSON
    
    Returns:
        Extracted JSON string or None
    """
    if not text:
        return None
    
    # Try to find JSON object
    # Look for { ... } with balanced braces
    depth = 0
    start = -1
    
    for i, char in enumerate(text):
        if char == "{":
            if depth == 0:
                start = i
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue
    
    # Try array format [ ... ]
    depth = 0
    start = -1
    
    for i, char in enumerate(text):
        if char == "[":
            if depth == 0:
                start = i
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0 and start != -1:
                candidate = text[start:i+1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    continue
    
    return None


def parse_action(text: str) -> ActionEnvelope:
    """
    Parse text into ActionEnvelope.
    
    Handles:
    - Valid JSON action envelopes
    - Malformed JSON (attempts repair)
    - Raw text (wraps in envelope)
    - Embedded JSON in text
    
    Args:
        text: Raw agent output
    
    Returns:
        ActionEnvelope (never raises, always returns valid envelope)
    """
    # Canonicalize first
    text = canonicalize_output(text)
    
    if not text:
        return ActionEnvelope(
            action=ActionType.ERROR,
            payload={"error": "Empty output", "raw": text},
            reasoning="Agent returned empty output",
            confidence=0.0,
        )
    
    # Try to extract JSON
    json_str = extract_json(text)
    
    if json_str:
        # Try to parse as JSON
        try:
            data = json.loads(json_str)
            return ActionEnvelope.from_dict(data)
        except json.JSONDecodeError:
            # Try repair
            repaired = repair_json(json_str)
            if repaired:
                try:
                    data = json.loads(repaired)
                    return ActionEnvelope.from_dict(data)
                except json.JSONDecodeError:
                    pass
    
    # Try to parse entire text as JSON
    try:
        data = json.loads(text)
        return ActionEnvelope.from_dict(data)
    except json.JSONDecodeError:
        # Try repair
        repaired = repair_json(text)
        if repaired:
            try:
                data = json.loads(repaired)
                return ActionEnvelope.from_dict(data)
            except json.JSONDecodeError:
                pass
    
    # If all else fails, wrap raw text as ask_user action
    return ActionEnvelope(
        action=ActionType.ASK_USER,
        payload={"message": text[:1000]},  # Truncate long text
        reasoning="Could not parse agent output as action, treating as user question",
        confidence=0.5,
    )


def validate_action(envelope: ActionEnvelope) -> tuple[bool, Optional[str]]:
    """
    Validate an action envelope.
    
    Args:
        envelope: Action envelope to validate
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check action type
    if not isinstance(envelope.action, ActionType):
        return False, f"Invalid action type: {envelope.action}"
    
    # Check payload based on action type
    if envelope.action == ActionType.CREATE_FILE:
        if "path" not in envelope.payload:
            return False, "CREATE_FILE action missing 'path' in payload"
        if "content" not in envelope.payload:
            return False, "CREATE_FILE action missing 'content' in payload"
    
    elif envelope.action == ActionType.EDIT_FILE:
        if "path" not in envelope.payload:
            return False, "EDIT_FILE action missing 'path' in payload"
    
    elif envelope.action == ActionType.RUN_COMMAND:
        if "command" not in envelope.payload:
            return False, "RUN_COMMAND action missing 'command' in payload"
    
    elif envelope.action == ActionType.ASK_USER:
        if "message" not in envelope.payload:
            return False, "ASK_USER action missing 'message' in payload"
    
    return True, None


__all__ = [
    "ActionType",
    "ActionEnvelope",
    "canonicalize_output",
    "repair_json",
    "extract_json",
    "parse_action",
    "validate_action",
]
