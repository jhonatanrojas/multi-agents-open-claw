# Stack Router

Use this skill when a project brief needs stack-specific routing for the coding
agents.

## Purpose
- Help ARCH decide which capabilities BYTE and PIXEL should focus on.
- Turn the project brief and task descriptions into stack-aware work context.
- Keep the agent workspaces in sync with the current task and its skill profile.

## Routing Rules
- If the project mentions `Laravel`, route BYTE toward `PHP`, `Laravel`,
  `Artisan`, `Eloquent`, `Composer`, and `migrations`.
- If the project mentions `Node`, `Express`, or `Fastify`, route BYTE toward
  `Node.js`, `Express`, `REST APIs`, `middleware`, and `TypeScript` when
  present.
- If the task is frontend/UI, route PIXEL toward `React`, `TypeScript`,
  accessibility, responsive layout, and component boundaries.
- If the task is DevOps, route BYTE toward `Bash`, `Apache`, `Nginx`, `cron`,
  backups, and health checks.
- If the task is documentation, route BYTE or PIXEL toward `Markdown`,
  information architecture, and installation/user guides.

## Workspace Output
- Write the current task context to `workspaces/<agent>/active_task.md`.
- Write the normalized task payload to `workspaces/<agent>/active_task.json`.
- Write progress snapshots to `workspaces/<agent>/progress/<task_id>.json`.

## Coordination
- Ask ARCH for clarification with `QUESTION:<task_id> <question>`.
- Report blockers with `BLOCKER:<task_id> <issue>`.
- When the stack changes mid-project, refresh the task context files before the
  next task starts.

