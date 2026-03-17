from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import FORMAL_DIR, STATE_DIR, count_regex_matches, monotonic_time, read_json, run_checked, write_json
from scripts.render_report import render
from scripts.score_iteration import score_tuple


def file_has_forbidden_axioms(path: Path) -> bool:
    text = path.read_text()
    return bool(re.search(r"(^|\n)\s*(axiom|admit)\b", text))


def count_total_sorries() -> int:
    return sum(count_regex_matches(path, r"\bsorry\b") for path in FORMAL_DIR.glob("*.lean"))


def stable_files_sorry_free() -> bool:
    stable_files = [
        FORMAL_DIR / "Defs.lean",
        FORMAL_DIR / "Known.lean",
        FORMAL_DIR / "Conjectures.lean",
        FORMAL_DIR / "Scratch.lean",
    ]
    return all("sorry" not in path.read_text() for path in stable_files)


def count_promoted_lemmas() -> int:
    return count_regex_matches(FORMAL_DIR / "Known.lean", r"^\s*theorem\s+")


def theorem_sanity_check() -> subprocess.CompletedProcess[str]:
    return run_checked(["lake", "env", "lean", "Formal/Scratch.lean"])


def falsify_current_claim() -> dict:
    output = STATE_DIR / "falsifier_current.json"
    process = run_checked(
        [
            "python3",
            "scripts/falsify_small.py",
            "--current-claim-only",
            "--write",
            str(output),
        ]
    )
    if process.returncode != 0:
        return {"result": "error", "stdout": process.stdout, "stderr": process.stderr}
    return json.loads(output.read_text())


def evaluate_repo() -> dict:
    start = monotonic_time()
    build = run_checked(["lake", "build"])
    sanity = theorem_sanity_check()
    falsifier = falsify_current_claim()
    progress = read_json(STATE_DIR / "progress.json")

    forbidden_axioms = any(file_has_forbidden_axioms(path) for path in FORMAL_DIR.glob("*.lean"))
    stable_sorry_free = stable_files_sorry_free()
    total_sorries = count_total_sorries()
    stories_done = sum(1 for story in progress["stories"] if story["status"] == "done")
    blocked_claims = sum(1 for claim in progress["claims"] if claim["status"] == "blocked")
    active_survives = 1 if falsifier.get("result") == "survives_small_n" else 0
    elapsed = round(monotonic_time() - start, 4)

    metrics = {
        "build_ok": build.returncode == 0 and not forbidden_axioms,
        "build_stdout": build.stdout,
        "build_stderr": build.stderr,
        "theorem_sanity_ok": sanity.returncode == 0,
        "theorem_sanity_stdout": sanity.stdout,
        "theorem_sanity_stderr": sanity.stderr,
        "stable_file_sorry_free": stable_sorry_free,
        "num_promoted_lemmas": count_promoted_lemmas(),
        "num_story_done": stories_done,
        "num_active_claims_surviving_small_n": active_survives,
        "num_total_sorries": total_sorries,
        "num_blocked_claims": blocked_claims,
        "eval_runtime_sec": elapsed,
        "active_claim_result": falsifier.get("result", "error"),
        "active_claim_counterexample": falsifier.get("counterexample"),
        "forbidden_axioms_found": forbidden_axioms,
    }
    metrics["score"] = list(score_tuple(metrics))
    return metrics


def main() -> int:
    metrics = evaluate_repo()
    write_json(STATE_DIR / "metrics.json", metrics)
    (STATE_DIR / "current_report.md").write_text(render(metrics))
    print(json.dumps(metrics, indent=2))
    return 0 if metrics["build_ok"] and metrics["theorem_sanity_ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
