# autoresearch

Formal autoresearch MVP for the SolveAll decision-tree learning problem.

## What is here

- Lean 4 + mathlib project rooted at `Formal/`
- stable definitions and promoted lemmas in `Formal/Defs.lean` and `Formal/Known.lean`
- one mutable active theorem file in `Formal/Active.lean`
- Python evaluation, falsification, and iteration scripts in `scripts/`
- machine-readable state in `state/`, `claims/`, and `bench/`

## Core commands

```bash
export PATH="$HOME/.elan/bin:$PATH"
lake build
python3 scripts/eval_iteration.py
python3 scripts/run_iteration.py
```

## MVP policy

- autonomous iterations edit only `Formal/Active.lean`
- all keep/discard decisions go through the same evaluation harness
- small-instance falsification runs before a trial edit is kept
- progress is logged to files, not hidden model memory
