---
name: deploy-preview
description: Use when a project needs a shared preview or manual deploy flow for Node, Express, React, Laravel, Vue, Vanilla, or Next apps using the shared deploy hosts.
---

# Deploy Preview

Use this skill when the task is about publishing a preview, running a manual deploy, or wiring a shared deploy host for a web stack.

## Core Rule

- `preview.deploymatrix.com` is the shared frontend preview host.
- `preview-backend.deploymatrix.com` is the shared backend/API preview host.
- These hosts are shared ingress points. They are not tied to a single project.
- Choose the host on demand based on the current task and stack.
- BYTE is responsible for starting and stopping the preview process.
- ARCH is responsible for announcing the URL after JUDGE approves.

## Stack Selection

Identify the stack first, then pick the deploy path:

- `Vanilla`, `React`, `Vue` -> static frontend build plus shared frontend preview host
- `Next` -> build then `next start` or equivalent production start plus shared frontend preview host
- `Node`, `Express` -> app start or API service plus shared backend preview host
- `Laravel` -> PHP app start or local web server plus shared backend preview host

If the stack is mixed, split the deploy target:

- frontend surface -> `preview.deploymatrix.com`
- API/backend surface -> `preview-backend.deploymatrix.com`

## Manual Deploy Flow

1. Detect the stack from the brief or repo.
2. Build the project with the stack-appropriate command.
3. Start the runtime or preview server on a local port.
4. Point the shared host at that local target or publish the resulting URL.
5. Write the URL to `MEMORY.json.preview_url`.
6. Set `MEMORY.json.preview_status` to `running`.
7. After human confirmation, stop the server or tunnel and set `preview_status` to `stopped`.

## Stack Playbooks

### Vanilla / React / Vue

- Build: `npm run build`
- Preview server: `npx serve -s dist` or `npx serve -s build`
- Dev fallback: `npm run dev`

### Next

- Build: `npm run build`
- Start: `npm run start`
- Dev fallback: `npm run dev`

### Node / Express

- Install: `npm ci`
- Start: `npm start` or `npm run start`
- If the app exposes a frontend bundle, serve that bundle with the shared frontend host.

### Laravel

- Install: `composer install`
- Start: `php artisan serve --host 127.0.0.1 --port 8000`
- When explicitly requested, apply deploy-safe commands such as `php artisan migrate --force` and `php artisan optimize:clear`.

## Output Contract

- Do not mark the task as delivered unless the deployed files exist in the repo and the preview URL is reachable.
- Do not keep a preview running after ARCH confirms closure.
- If preview creation fails, report the blocker and do not retry aggressively.

