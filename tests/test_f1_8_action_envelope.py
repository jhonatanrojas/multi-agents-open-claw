#!/usr/bin/env python3
"""
Tests for F1.8 — Canonicalización de salida y reparación de acciones
"""

import json
import sys
sys.path.insert(0, '/var/www/openclaw-multi-agents')

from action_envelope import (
    ActionType,
    ActionEnvelope,
    canonicalize_output,
    repair_json,
    extract_json,
    parse_action,
    validate_action,
)


def test_canonicalize_output():
    """Test output canonicalization."""
    print("Testing canonicalize_output...")
    
    # Strip whitespace
    assert canonicalize_output("  hello  ") == "hello"
    
    # Remove markdown code blocks
    assert canonicalize_output("```json\n{\"key\": \"value\"}\n```") == '{"key": "value"}'
    
    # Normalize line endings
    assert canonicalize_output("line1\r\nline2\rline3") == "line1\nline2\nline3"
    
    print("  ✓ Canonicalization working")


def test_repair_json():
    """Test JSON repair."""
    print("Testing repair_json...")
    
    # Valid JSON (no repair needed)
    valid = '{"key": "value"}'
    assert repair_json(valid) == valid
    
    # Trailing comma
    repaired = repair_json('{"key": "value",}')
    assert repaired is not None
    assert json.loads(repaired) == {"key": "value"}
    
    # Missing closing brace
    repaired = repair_json('{"key": "value"')
    assert repaired is not None
    assert json.loads(repaired) == {"key": "value"}
    
    print("  ✓ JSON repair working")


def test_extract_json():
    """Test JSON extraction from text."""
    print("Testing extract_json...")
    
    # JSON embedded in text
    text = 'Here is the result: {"action": "complete", "payload": {}} Done!'
    extracted = extract_json(text)
    assert extracted is not None
    assert '"action": "complete"' in extracted
    
    # Pure JSON
    text = '{"key": "value"}'
    extracted = extract_json(text)
    assert extracted == text
    
    print("  ✓ JSON extraction working")


def test_parse_action_valid():
    """Test parsing valid action."""
    print("Testing parse_action with valid JSON...")
    
    valid_json = '{"action": "create_file", "payload": {"path": "/tmp/test.txt", "content": "hello"}}'
    envelope = parse_action(valid_json)
    
    assert envelope.action == ActionType.CREATE_FILE
    assert envelope.payload["path"] == "/tmp/test.txt"
    
    print("  ✓ Valid action parsed")


def test_parse_action_malformed():
    """Test parsing malformed JSON (repair)."""
    print("Testing parse_action with malformed JSON...")
    
    # Trailing comma
    malformed = '{"action": "complete", "payload": {},}'
    envelope = parse_action(malformed)
    
    assert envelope.action == ActionType.COMPLETE
    
    print("  ✓ Malformed JSON repaired and parsed")


def test_parse_action_raw_text():
    """Test parsing raw text (no JSON)."""
    print("Testing parse_action with raw text...")
    
    raw_text = "I need more information about the requirements."
    envelope = parse_action(raw_text)
    
    assert envelope.action == ActionType.ASK_USER
    assert "more information" in envelope.payload["message"]
    
    print("  ✓ Raw text wrapped as ASK_USER")


def test_parse_action_with_markdown():
    """Test parsing JSON inside markdown."""
    print("Testing parse_action with markdown...")
    
    markdown = '''```json
{
    "action": "run_command",
    "payload": {
        "command": "ls -la"
    }
}
```'''
    envelope = parse_action(markdown)
    
    assert envelope.action == ActionType.RUN_COMMAND
    assert envelope.payload["command"] == "ls -la"
    
    print("  ✓ Markdown code block handled")


def test_validate_action():
    """Test action validation."""
    print("Testing validate_action...")
    
    # Valid CREATE_FILE
    envelope = ActionEnvelope(
        action=ActionType.CREATE_FILE,
        payload={"path": "/tmp/test.txt", "content": "hello"},
    )
    valid, error = validate_action(envelope)
    assert valid is True
    assert error is None
    
    # Invalid CREATE_FILE (missing path)
    envelope = ActionEnvelope(
        action=ActionType.CREATE_FILE,
        payload={"content": "hello"},
    )
    valid, error = validate_action(envelope)
    assert valid is False
    assert "missing" in error.lower()
    
    print("  ✓ Action validation working")


def test_action_envelope_roundtrip():
    """Test ActionEnvelope serialization roundtrip."""
    print("Testing ActionEnvelope roundtrip...")
    
    original = ActionEnvelope(
        action=ActionType.EDIT_FILE,
        payload={"path": "/tmp/file.txt", "changes": ["line1"]},
        reasoning="Need to update file",
        confidence=0.95,
    )
    
    # To dict and back
    data = original.to_dict()
    restored = ActionEnvelope.from_dict(data)
    
    assert restored.action == original.action
    assert restored.payload == original.payload
    assert restored.reasoning == original.reasoning
    assert restored.confidence == original.confidence
    
    print("  ✓ Roundtrip successful")


def run_all_tests():
    """Run all F1.8 tests."""
    print("=" * 60)
    print("F1.8 — Canonicalización de salida y reparación de acciones Tests")
    print("=" * 60)
    
    tests = [
        test_canonicalize_output,
        test_repair_json,
        test_extract_json,
        test_parse_action_valid,
        test_parse_action_malformed,
        test_parse_action_raw_text,
        test_parse_action_with_markdown,
        test_validate_action,
        test_action_envelope_roundtrip,
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
        print("\n🎉 F1.8 implementation complete!")
    
    return failed == 0


if __name__ == "__main__":
    import json
    success = run_all_tests()
    sys.exit(0 if success else 1)
