---
name: improve-codebase-architecture
description: Survey Pixfabrica for architectural friction, present evidenced improvement candidates in a visual HTML report, and explore the candidate the user selects.
---

# Improve Codebase Architecture

Read [AGENTS.md](../../../AGENTS.md) and [project skill guidance](../../../docs/agents/skills.md) before applying this workflow.

Use [codebase-design](../codebase-design/SKILL.md) for the design vocabulary and principles.
This workflow surveys and discusses architecture.
Implement a candidate only when implementation is within the user's requested scope.

## Explore the relevant area

Honor the user's named subsystem or pain point.
Otherwise inspect recent Git history to identify areas that repeatedly change, then trace their callers and tests.
Read the relevant package README and architecture sections.
Use a glossary or ADRs if they already exist; their absence does not block the survey.

Look for concrete friction:
- Understanding one operation requires navigating many thin forwarding modules.
- Callers must coordinate details that belong behind one interface.
- Tests isolate helpers while missing failures in their actual calling sequence.
- Composition, ordering, resource ownership, or plugin contracts leak across packages.
- An important behavior is difficult to verify through its existing interface.

Trace each candidate through real callers before recommending consolidation.
Apply the deletion test: distinguish wrappers whose removal eliminates complexity from abstractions whose removal spreads complexity across callers.
Small files, few tests, or many packages alone are not evidence of a problem.
Preserve GPU resource and performance constraints, stable wire IDs, and timeline behavior.
Surface conflicts with documented decisions explicitly.

Explore directly by default.
If the user requests delegation, keep agents in this checkout, assign non-overlapping read-only investigations, and do not create worktrees.

## Present a visual report

Follow [HTML-REPORT.md](HTML-REPORT.md).
Write a uniquely named report under the OS temporary directory or an approved artifact directory.
Use inline CSS and SVG so it works without a network connection.
Open it using the available preview tool and provide its absolute path.

For each candidate include:
- Exact files and caller evidence.
- The observed problem and proposed responsibility change.
- Before and after diagrams.
- Benefits to callers and behavior tests.
- Compatibility, GPU/resource, and migration risks where relevant.
- Recommendation strength: Strong, Worth exploring, or Speculative.

End with the strongest recommendation and its evidence.
Separate observations from hypotheses.
Do not invent candidates to fill a quota; a report can conclude that no worthwhile change was established.

## Explore the selected candidate

If the user has not already selected a candidate, ask which one to explore.
Resolve meaningful uncertainty about constraints, callers, dependencies, errors, and observable behavior.
Ask focused questions only when repository evidence and existing user direction do not settle them.

Use [DESIGN-IT-TWICE.md](../codebase-design/DESIGN-IT-TWICE.md) when competing interfaces warrant comparison.
Describe the proposed interface, what it hides, what tests survive, and the migration path.
Use existing terminology from the architecture documentation.
Propose documentation changes for new concepts or durable decisions; do not create a competing glossary merely to satisfy the upstream convention.
Continue into implementation only within the user's authorized scope.
