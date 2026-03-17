# Role
You are running one iteration of an autoresearch-style formalization loop.

# Objective
Improve the formalization frontier for the active decision-tree learning problem.

# Files
Edit only `Formal/Active.lean`.
Treat all other files as read-only context.

# Before editing
1. Read `problem.md`.
2. Read `state/progress.json`.
3. Read `state/current_report.md`.
4. Inspect the active theorem block in `Formal/Active.lean`.

# What to optimize
Prefer, in order:
1. proving the active theorem,
2. reducing the number of `sorry`s,
3. replacing a false conjecture with a weaker true one,
4. extracting a reusable helper lemma within `Formal/Active.lean`.

# Constraints
- No new axioms.
- No direct edits to stable files.
- No scope expansion.
- One theorem family per iteration.

# If you find a likely counterexample
Do not push harder on the proof.
Instead, restate the theorem more narrowly inside `Formal/Active.lean` and make the statement executable for the falsifier.

# Success condition for an iteration
The post-edit evaluation score must improve.

# Failure mode
If build breaks, repair build first.
If no safe improvement is visible, make the smallest statement-cleanup change or do nothing.
