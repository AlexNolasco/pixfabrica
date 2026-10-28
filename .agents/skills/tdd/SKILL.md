---
name: tdd
description: Build features and regression tests through observable public behavior using a test-first loop in Pixfabrica.
---

# Test-Driven Development

Read [AGENTS.md](../../../AGENTS.md) and [project skill guidance](../../../docs/agents/skills.md) before applying this workflow.

For bug fixes, first follow the E2E reproduction step in [diagnosing-bugs](../diagnosing-bugs/SKILL.md).
Choose a test interface that exercises the behavior callers actually depend on.
State what the test catches and what it cannot establish.
Use existing project interfaces without asking for repeated approval; clarify only when intended behavior or a new contract is unresolved.

## Test behavior

Use public composition validation and serialization, HTTP routes, CLI commands, plugin discovery, or actual rendered output as appropriate.
Follow nearby fixtures and package conventions.
Read [tests.md](tests.md) for good and bad examples and [mocking.md](mocking.md) when isolating dependencies.
The TypeScript examples illustrate test design, not a requirement to install Jest or another runner.

Expected values must come from the contract, an independently worked example, or a reviewed fixture.
Do not derive expected output using the same algorithm as the implementation.
Avoid private-method tests and mocks of the internal call chain responsible for the bug.
For interface design decisions, consult [codebase-design](../codebase-design/SKILL.md).

## One behavior at a time

1. Write one meaningful failing test for an observable behavior.
2. Run it and verify that the failure comes from the missing behavior, not broken setup.
3. Implement the smallest coherent change that satisfies the contract.
4. Run the test, then repeat for the next behavior.
5. Review duplication and design with tests green, preserving observable behavior.

Do not write a whole speculative suite before implementing the first behavior.
Do not add tests that mirror trivial implementation details or merely assert documentation wording.
Keep relevant existing regression coverage when restructuring code.
Run focused checks during iteration and the required package checks before finishing.
