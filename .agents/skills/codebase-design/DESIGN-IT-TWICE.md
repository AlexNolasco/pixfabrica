# Design It Twice

Use this when comparing interfaces for a selected architecture candidate.
Read [SKILL.md](SKILL.md) for vocabulary and [DEEPENING.md](DEEPENING.md) for dependency tradeoffs.

State the callers, invariants, ordering, error behavior, and dependencies that every design must satisfy.
Develop two or more materially different designs, such as:
- A small interface that hides coordination.
- An interface optimized for the most common caller.
- An extensible interface where real plugin variation requires it.

For each design show a usage example, hidden implementation responsibilities, dependency strategy, test interface, and tradeoffs.
Compare caller complexity, locality, compatibility, and resource lifetime.
Recommend the strongest design or a justified combination.

Work directly unless the user requests parallel agents.
With delegation, give each agent a distinct design constraint and a read-only brief in the existing checkout.
Respect available agent capacity and never create a worktree without explicit user authorization.
