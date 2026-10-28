---
name: diagnosing-bugs
description: Diagnose reproducible bugs and performance regressions in Pixfabrica's editor, API, CLI, plugins, or renderer, then verify a focused fix.
---

# Diagnosing Bugs

Read [AGENTS.md](../../../AGENTS.md) and [project skill guidance](../../../docs/agents/skills.md) before applying this workflow.

## Reproduce the user's failure

Start with an E2E reproduction as close as possible to the user's actual workflow.
For an editor bug, exercise the timeline and preview through the running UI.
For a render or CLI bug, use the real composition input and render or command path.
Record the exact symptom, environment, input, and observed result before proposing a cause.
Redact credentials from commands, logs, and captured requests.

Build a repeatable pass/fail signal that catches this specific symptom.
Use browser interaction, an HTTP request, a CLI fixture, or an automated E2E test as appropriate.
Do not substitute a passing isolated helper test for the original failure.
If reproduction is blocked, explain what was tried and what access or input is missing; do not claim a verified fix.

## Minimise and investigate

Reduce inputs and configuration one change at a time while preserving the failure.
Keep the original reproduction for final verification.
Pin time, randomness, and relevant environment details where possible.
For flaky failures, measure the reproduction rate and use repeated trials instead of claiming determinism.
For performance problems, establish a measurement before changing code.

State plausible, ranked causes and the observation that would distinguish each one.
Test one prediction at a time using targeted inspection or uniquely tagged temporary logs.
Prefer a short feedback loop, but retain the real GPU, encoding, or caller interaction when it is necessary to reproduce the bug.
Do not switch branches, bisect the active checkout, or create worktrees without the user's explicit request.

## Fix and verify

Turn the minimised reproduction into a regression test through the real calling interface when a meaningful test is possible.
Read [tdd](../tdd/SKILL.md) for test design.
Observe the test fail for the reported reason before applying a focused fix.
If available test interfaces cannot capture the bug, document that limitation instead of adding a misleading test.

Re-run the original E2E scenario after the regression passes.
Inspect visible UI and rendered pixels when the failure is visual.
Run the applicable project checks described in AGENTS.md.
Remove only temporary artifacts and instrumentation created for this investigation.
Report the cause, changed behavior, verification evidence, and any remaining limits.
