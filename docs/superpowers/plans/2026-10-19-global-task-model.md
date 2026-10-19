# Task and cover follow the current system model

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Switching the active model in settings changes the next ordinary task or cover text request, including resumed tasks with old profile snapshots.

**Architecture:** Ordinary task paths resolve without a pinned profile. Globally resolved settings carry a runtime binding, refreshed once at the actual HTTP request boundary. Explicit standalone workbench and connection tests retain explicit model semantics. Existing artifacts and provider receipts are untouched. Task/cover controls describe the system binding and link to settings rather than offer an ignored override.

**Tech Stack:** Python backend, vanilla JavaScript, unittest, Node test runner, guarded compiled-runtime deployment.

**Spec:** `docs/audit/2026-10-19-story-global-model-switch.md`; user explicitly confirmed that cover text also follows system selection on 2026-10-19.

## Constraints

- Offline Story evidence only; never launch Story or installers.
- No real provider calls, new generation, task invalidation, key output, or forced application exit.
- Preserve historical configuration and successful outputs; only future text requests change binding.
- Existing dirty workspace is the authoritative source baseline; capture exact deltas and transplant only verified functions/assets into the installed runtime.

## Steps

- [x] Capture source baseline; reproduce stale text/cover profile selection using local fixtures.
- [x] Refresh global settings at request boundary; route ordinary task/cover paths through global resolution; preserve explicit standalone calls.
- [x] Show the actual system model in task/cover controls and creation view, with a settings link.
- [x] Run focused Python/Node regressions and independent read-only review.
- [x] Prepare candidate runtime, validate actual isolated desktop entry and UI, then update safely when 074 is closed; verify manifest and business-data hashes.
- [x] Record exact source delta, evidence, commit task-owned files, and report the verified scope and remaining upstream uncertainty.
