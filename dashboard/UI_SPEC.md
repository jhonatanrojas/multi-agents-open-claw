# Dashboard UI Components Specification

This document specifies the three intervention UI components for the Dev Squad dashboard. These components give the human operator active intervention controls over the multi-agent system.

## Component 1: Steer Input Field

### Location
- Appears alongside each active agent card in the dashboard
- Only visible when agent status is `in_progress`

### Design

```
┌─────────────────────────────────────────────────┐
│  BYTE - Programmer                    [●] Active│
│  Task: T-003 - Build API endpoints              │
│  Status: in_progress (2m 34s)                   │
│                                                 │
│  ┌─────────────────────────────────────────┐   │
│  │ Send guidance to BYTE...                 │   │
│  └─────────────────────────────────────────┘   │
│                                       [Send →]  │
│                                                 │
│  Last activity: Creating UserService.php        │
└─────────────────────────────────────────────────┘
```

### States

| State | UI Behavior |
|-------|-------------|
| Idle | Input placeholder visible, Send button enabled |
| Loading | Spinner on Send button, input disabled |
| Success | Green checkmark flash, input cleared |
| Error | Red error message below input, retry button |

### API Integration

```typescript
async function sendSteer(agentId: string, message: string) {
  const response = await fetch(`/api/agents/${agentId}/steer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message })
  });
  return response.json();
}
```

### Accessibility
- Input has `aria-label="Send guidance to ${agentName}"`
- Send button has `aria-label="Send steer message"`
- Loading announced via `aria-live="polite"`
- Error announced via `aria-live="assertive"`

---

## Component 2: Pause/Resume Toggle

### Location
- Appears on each task row in the task list
- Only visible when task status is `in_progress` or `paused`

### Design

```
┌─────────────────────────────────────────────────────────────┐
│ Tasks                                                        │
│ ┌─────┬──────────────────────────┬─────────┬─────────────┐ │
│ │ ID  │ Description              │ Agent   │ Status      │ │
│ ├─────┼──────────────────────────┼─────────┼─────────────┤ │
│ │T-001│ Design login component   │ PIXEL   │ done     ✓  │ │
│ │T-002│ Build login API          │ BYTE    │ in_progress│ │
│ │     │                          │         │    [⏸]     │ │
│ │T-003│ Integrate auth flow      │ BYTE    │ pending     │ │
│ │T-004│ Write auth tests         │ BYTE    │ pending     │ │
│ └─────┴──────────────────────────┴─────────┴─────────────┘ │
└─────────────────────────────────────────────────────────────┘

When paused:
┌─────┬──────────────────────────┬─────────┬─────────────┐
│T-002│ Build login API          │ BYTE    │ paused      │
│     │ ⚠ Waiting for credentials│         │    [▶]      │
└─────┴──────────────────────────┴─────────┴─────────────┘
```

### Pause Modal

```
┌─────────────────────────────────────────┐
│  Pause Task T-002?                       │
│                                          │
│  Reason (optional):                      │
│  ┌────────────────────────────────────┐ │
│  │ Waiting for API credentials...     │ │
│  └────────────────────────────────────┘ │
│                                          │
│            [Cancel]  [Pause Task]        │
└─────────────────────────────────────────┘
```

### States

| State | Icon | Action |
|-------|------|--------|
| `in_progress` | ⏸ (pause) | Click opens pause modal |
| `paused` | ▶ (play) | Click resumes task |
| Loading | Spinner | Button disabled |
| Error | ⚠ (warning) | Show error tooltip |

### API Integration

```typescript
async function pauseTask(taskId: string, reason?: string) {
  const response = await fetch(`/api/tasks/${taskId}/pause`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason })
  });
  return response.json();
}

async function resumeTask(taskId: string) {
  const response = await fetch(`/api/tasks/${taskId}/resume`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  });
  return response.json();
}
```

### Accessibility
- Pause button: `aria-label="Pause task ${taskId}"`
- Resume button: `aria-label="Resume task ${taskId}"`
- Modal: `aria-modal="true"`, `role="dialog"`
- Focus trapped in modal when open

---

## Component 3: Inline CONTEXT.md Editor

### Location
- Context panel in the dashboard sidebar
- Read-only view with edit buttons per section

### Design

```
┌─────────────────────────────────────────┐
│  Project Context                    [⚙] │
├─────────────────────────────────────────┤
│  Architecture                      [✏️] │
│  ─────────────────────────────────────  │
│  This project follows a modular monolith│
│  architecture with clear separation of  │
│  concerns between modules...            │
│                                          │
│  Tech Stack                        [✏️] │
│  ─────────────────────────────────────  │
│  - Frontend: React 18 + TypeScript      │
│  - Backend: Node.js 20 + Express        │
│  - Database: PostgreSQL 15              │
│                                          │
│  Constraints                       [✏️] │
│  ─────────────────────────────────────  │
│  - No external API calls without cache  │
│  - All UI must be WCAG 2.1 AA           │
└─────────────────────────────────────────┘
```

### Edit Mode

```
┌─────────────────────────────────────────┐
│  Editing: Architecture                   │
├─────────────────────────────────────────┤
│  ┌────────────────────────────────────┐ │
│  │ This project follows a modular     │ │
│  │ monolith architecture with clear   │ │
│  │ separation of concerns between     │ │
│  │ modules. Each module is a bounded  │ │
│  │ context...                         │ │
│  │                                    │ │
│  │ [cursor here]                      │ │
│  └────────────────────────────────────┘ │
│                                          │
│  Reason for change:                      │
│  ┌────────────────────────────────────┐ │
│  │ Clarified bounded context concept. │ │
│  └────────────────────────────────────┘ │
│                                          │
│          [Cancel]        [Save Changes]  │
└─────────────────────────────────────────┘
```

### States

| State | UI Behavior |
|-------|-------------|
| Read | Edit buttons visible, content static |
| Editing | Textarea with current content, reason input |
| Saving | Spinner on Save button, Cancel disabled |
| Success | Green toast: "Context updated to version N" |
| Error | Red toast: "Failed to update context" |

### API Integration

```typescript
async function updateContext(section: string, content: string, reason: string) {
  const response = await fetch('/api/context', {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ section, content, reason })
  });
  return response.json();
}
```

### Accessibility
- Edit button: `aria-label="Edit ${section} section"`
- Textarea: `aria-label="Editing ${section} section"`
- Reason input: `aria-label="Reason for change"`
- Save button: `aria-label="Save changes to ${section}"`

---

## Error Handling

All three components must handle these error scenarios:

| Error Code | User Message | Action |
|------------|--------------|--------|
| 400 | "Invalid request. Please check your input." | Show inline error |
| 404 | "Resource not found. It may have been deleted." | Refresh page |
| 500 | "Server error. Please try again later." | Show retry button |
| Network | "Unable to connect. Check your connection." | Show retry button |

## Loading States

All three components must show loading states:

- Disable interactive elements during request
- Show spinner on the action button
- Announce loading via `aria-live="polite"`

## Testing Checklist

Before deploying:

- [ ] All three components render correctly
- [ ] API integration works with mock backend
- [ ] Loading states display properly
- [ ] Error states display properly
- [ ] Keyboard navigation works (Tab, Enter, Escape)
- [ ] Screen reader announces all states
- [ ] Focus management is correct (modals, edit modes)
- [ ] Responsive design works on mobile
