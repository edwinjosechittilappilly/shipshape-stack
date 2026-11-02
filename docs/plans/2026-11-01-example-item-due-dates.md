# Plan: Item due dates (example)

- **Status:** Example (illustrative; not implemented)
- **Author:** maintainers
- **Date:** 2026-11-01
- **Issue:** none (example)

This is a deliberately short, filled-in plan showing the expected level of detail. Delete it in your own project.

## Problem

Items can be created, completed, and deleted, but there is no way to say when something is due. Users track dates outside
the app and the list cannot be sorted by urgency.

## Goals

- An item can optionally have a due date, set on creation and editable later.
- The list shows the due date and marks overdue, not-done items.

## Non-goals

- Reminders or notifications, recurring items, time-of-day or time zones (a date only).

## Options

### Option A: nullable `due_date` column on `items`

Smallest change; one migration; the API gains an optional field. Cannot express recurrence later without more columns.

### Option B: separate `schedules` table

Flexible for recurrence and reminders, but speculative and a join for every list call.

## Decision

Option A. Add `due_date DATE NULL` to `items`; expose optional `due_date` (ISO-8601 date) on `POST` and `PATCH` and in `Item`.
This is backwards compatible within `/api/v1` (new optional field), so no new API version.

## Rollout

1. Migration adds the nullable column (expand step; the previous app release ignores it).
2. Backend release reads and writes it.
3. Frontend release shows and edits it.

Rollback: revert the app releases; the column can stay. Dropping it would be a later contract step.

## Test plan

- Unit: schema accepts a valid date and rejects malformed input; overdue computation in the frontend.
- Integration: create and patch with and without `due_date`; migration applies on a fresh database.
- E2E mocked: overdue item is flagged; due date input has an accessible label.

## Risks and open questions

| Risk or question | Impact | Mitigation or owner |
| --- | --- | --- |
| "Overdue" depends on the user's local date | Wrong flag near midnight | Compare dates in the browser's local date; documented non-goal for time zones |

## PR slicing

1. `feat(backend): add optional due_date to items`: migration, model, schema, API tests (`area: backend`).
2. `feat(frontend): show and edit item due dates`: UI, unit and mocked e2e tests (`area: frontend`).
3. `docs: document due_date in the API section`: only if the docs mention the item shape.
