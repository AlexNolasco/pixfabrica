# Project skills

The four skills under `.agents/skills/` are locally adapted from [mattpocock/skills](https://github.com/mattpocock/skills).
They are development guidance, with no application runtime dependencies.
Use the repository copies to keep the team's workflows reviewable alongside the code.

## Shared context

Read [AGENTS.md](../../AGENTS.md) for project rules and required validation.
Read the relevant package README before making package-specific decisions.
[Architecture](../ARCHITECTURE.md) remains the source for domain terminology, timeline behavior, rendering constraints, and plugin contracts.
Use existing glossary or ADR files if present; creating them is not a prerequisite for these skills.

Work in the current checkout and selected branch.
Do not create or switch worktrees unless the user explicitly requests it.
Delegated work, when requested, stays in that checkout with non-overlapping responsibilities.
Surveying architecture does not itself authorize refactoring or publishing issues.

## Choosing a workflow

| Example request | Skill |
|-----------------|-------|
| Diagnose why a clip disappears from preview | `$diagnosing-bugs` |
| Add composition validation with a failing behavior test first | `$tdd` |
| Simplify the renderer's resource ownership interface | `$codebase-design` |
| Survey the API preview pipeline for architecture improvements | `$improve-codebase-architecture` |

The architecture survey preserves upstream's explicit invocation policy through `agents/openai.yaml`.
It produces an offline visual report and explores the candidate the user selects.
It uses the local design skill and self-contained discussion steps, so no separate interview, domain-modeling, tracker, or setup skills are required.

## Test interfaces and checks

Choose the existing public interface closest to the behavior under test.
State coverage limits when a fake or isolated test omits an important integration.

| Area | Useful observable behavior |
|------|----------------------------|
| `core/` | Composition validation, serialization, stable wire identifiers |
| `api/` | HTTP requests and responses, job and preview behavior |
| `cli/` | Commands, generated plugin files, exit status |
| `renderer/` | Rendered pixels, compositing order, resource lifecycle |
| `plugins/` | Discovery, schema contracts, defaults, rendered output |
| `web/` | Timeline interactions, preview, selection, undo/redo |

Follow the Python, standard-plugin, and web verification commands in AGENTS.md.
Root pytest discovery does not include `plugins/std/tests/`, so standard-clip changes need that explicit suite.
The web package currently has no test script; inspect available tooling rather than assuming a frontend runner exists.
A production build checks compilation but does not replace user-facing verification.
Run real GPU or FFmpeg scenarios when required to establish the behavior being changed, and disclose environmental limits.

## Provenance and updates

The [manifest](../../.agents/upstream/mattpocock-skills/provenance.json) records the exact upstream commit, source paths, and intentional adaptations.
The original [MIT license](../../.agents/upstream/mattpocock-skills/LICENSE) is retained.

To update, compare the recorded revision with a chosen upstream revision and review changes to each selected skill and its supporting files.
Reapply the documented local adaptations, check every relative reference and skill dependency, and update the manifest in the same change.
Preserve the architecture skill's invocation policy when changing its metadata.
Avoid installing a second global or plugin copy of these same skills for this project.

Validate each skill's YAML frontmatter and linked resources, then review realistic requests against the workflow.
In particular, check that debugging starts with E2E evidence, TDD uses existing interfaces without unnecessary gates, and an architecture survey does not silently begin implementation.
