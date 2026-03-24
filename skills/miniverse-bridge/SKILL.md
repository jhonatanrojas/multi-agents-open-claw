# Miniverse Bridge

Use this skill to keep the OpenClaw agents visible in Miniverse while they work.

## Purpose
- Send heartbeats while the agents think, work, or wait.
- Share task progress so the dashboard and the world stay in sync.
- Use Miniverse direct messages for coordination between ARCH, BYTE, and PIXEL.

## Behaviour
- ARCH should heartbeat as `thinking` during planning and review.
- BYTE and PIXEL should heartbeat as `working` while executing a task.
- When a task is idle or blocked, keep the state explicit instead of silent.

## Messaging
- Use Miniverse direct messages for coordination questions and blockers.
- Keep messages short and actionable.
- Prefer `BLOCKER:<task_id> <issue>` or `QUESTION:<task_id> <question>`.

## Notes
- This skill is paired with the Python bridge module at
  `miniverse_bridge.py`.
- The bridge module can be used by the orchestrator even if the skill itself is
  only acting as guidance for the OpenClaw agents.

