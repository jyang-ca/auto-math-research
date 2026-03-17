from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import STATE_DIR, append_jsonl, read_json, run_checked
from scripts.eval_iteration import evaluate_repo
from scripts.score_iteration import better, score_tuple

ACTIVE_FILE = ROOT / "Formal" / "Active.lean"


PROOF_SNIPPETS = {
    "active_uniformError_self_zero": "  simpa [uniformError] using (uniformErrorFn_self (f := eval t))\n",
    "active_uniformError_symm": "  simpa [uniformError] using (uniformErrorFn_symm (f := eval t) (g := eval u))\n",
}


def load_context() -> dict[str, str]:
    paths = [
        ROOT / "problem.md",
        ROOT / "program.md",
        STATE_DIR / "progress.json",
        STATE_DIR / "current_report.md",
        ACTIVE_FILE,
    ]
    return {str(path.relative_to(ROOT)): path.read_text() for path in paths}


def active_theorem_name(text: str) -> str | None:
    match = re.search(r"theorem_name:\s*([A-Za-z0-9_']+)", text)
    return match.group(1) if match else None


def agent_edit() -> dict[str, str]:
    original = ACTIVE_FILE.read_text()
    theorem_name = active_theorem_name(original)
    if theorem_name is None:
        return {"changed": "false", "reason": "no_active_metadata"}
    snippet = PROOF_SNIPPETS.get(theorem_name)
    if snippet is None:
        return {"changed": "false", "reason": f"no_template_for:{theorem_name}"}
    if "sorry" not in original:
        return {"changed": "false", "reason": "no_sorry_present"}
    updated = original.replace("  sorry\n", snippet, 1)
    ACTIVE_FILE.write_text(updated)
    return {"changed": "true", "reason": f"applied_template:{theorem_name}"}


def git_commit_if_possible(message: str) -> str | None:
    add = run_checked(
        [
            "git",
            "add",
            "Formal/Active.lean",
            "state/metrics.json",
            "state/current_report.md",
        ]
    )
    if add.returncode != 0:
        return None
    commit = run_checked(["git", "commit", "-m", message])
    if commit.returncode != 0:
        return None
    rev = run_checked(["git", "rev-parse", "HEAD"])
    if rev.returncode != 0:
        return None
    return rev.stdout.strip()


def update_progress_after_keep(commit_hash: str | None) -> None:
    progress = read_json(STATE_DIR / "progress.json")
    for claim in progress["claims"]:
        if claim["claim_id"] == progress["active_claim_id"]:
            claim["status"] = "proved"
            claim["lean_status"] = "proved"
    for story in progress["stories"]:
        if story["story_id"] == progress["active_story_id"]:
            story["status"] = "done"
            if commit_hash:
                story["evidence"].append(f"commit:{commit_hash}")
    progress["latest_kept_commit"] = commit_hash
    (STATE_DIR / "progress.json").write_text(json.dumps(progress, indent=2) + "\n")


def log_experiment(
    *,
    status: str,
    baseline: dict,
    trial: dict,
    edit_result: dict[str, str],
    commit_hash: str | None,
) -> None:
    progress = read_json(STATE_DIR / "progress.json")
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "active_claim_id": progress["active_claim_id"],
        "active_story_id": progress["active_story_id"],
        "baseline_score": list(score_tuple(baseline)),
        "trial_score": list(score_tuple(trial)),
        "edit_result": edit_result,
        "commit": commit_hash,
    }
    append_jsonl(STATE_DIR / "experiments.jsonl", payload)


def main() -> int:
    baseline = evaluate_repo()
    original_active = ACTIVE_FILE.read_text()
    _context = load_context()
    edit_result = agent_edit()
    trial = evaluate_repo()

    keep = better(trial, baseline)
    if not keep and trial["build_ok"] and trial["theorem_sanity_ok"]:
        keep = len(ACTIVE_FILE.read_text()) < len(original_active)

    if keep:
        commit_hash = git_commit_if_possible("codex: keep active theorem improvement")
        update_progress_after_keep(commit_hash)
        log_experiment(status="kept", baseline=baseline, trial=trial, edit_result=edit_result, commit_hash=commit_hash)
        print(json.dumps({"status": "kept", "commit": commit_hash, "edit_result": edit_result}, indent=2))
        return 0

    ACTIVE_FILE.write_text(original_active)
    reverted = evaluate_repo()
    log_experiment(status="discarded", baseline=baseline, trial=trial, edit_result=edit_result, commit_hash=None)
    print(json.dumps({"status": "discarded", "edit_result": edit_result, "score": reverted["score"]}, indent=2))
    return 1


if __name__ == "__main__":
    sys.exit(main())
