"""
Compatibility package that re-exports the implementation from ``openclaw_sdk.py``.

The repository contains both a package directory and a top-level module with the
same base name. Python resolves ``import openclaw_sdk`` to this package first,
so we load the sibling module explicitly and expose its public API here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

_IMPL_PATH = Path(__file__).resolve().parent.parent / "openclaw_sdk.py"
_SPEC = importlib.util.spec_from_file_location("_openclaw_sdk_impl", _IMPL_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise ImportError(f"Unable to load OpenClaw SDK implementation from {_IMPL_PATH}")

_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE
_SPEC.loader.exec_module(_MODULE)


def _export(name: str) -> Any:
    value = getattr(_MODULE, name)
    globals()[name] = value
    return value


Agent = _export("Agent")
AgentResult = _export("AgentResult")
FailureKind = _export("FailureKind")
OpenClawClient = _export("OpenClawClient")
ProgressCallback = _export("ProgressCallback")
classify_progress = _export("classify_progress")
get_agent_models = _export("get_agent_models")
get_available_models = _export("get_available_models")
load_openclaw_config = _export("load_openclaw_config")
save_openclaw_config = _export("save_openclaw_config")
set_agent_model = _export("set_agent_model")
set_default_model = _export("set_default_model")
_infer_failure_kind = _export("_infer_failure_kind")
parse_json_content = _export("parse_json_content")
make_session_id = _export("make_session_id")
is_valid_session_id = _export("is_valid_session_id")
truncate_prompt = _export("truncate_prompt")

__all__ = [
    "Agent",
    "AgentResult",
    "FailureKind",
    "OpenClawClient",
    "ProgressCallback",
    "classify_progress",
    "get_agent_models",
    "get_available_models",
    "load_openclaw_config",
    "save_openclaw_config",
    "set_agent_model",
    "set_default_model",
    "_infer_failure_kind",
    "parse_json_content",
    "make_session_id",
    "is_valid_session_id",
    "truncate_prompt",
]
