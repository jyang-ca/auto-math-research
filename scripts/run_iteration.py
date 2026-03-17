from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.claim_templates import (
    canary_claim_id,
    canary_claim_index,
    canary_claim_row,
    infer_story_id,
    is_canary_claim_id,
)
from scripts.common import load_jsonl, read_json, read_text_if_exists, run_checked, run_checked_input, write_json, write_jsonl, write_text
from scripts.promote_lemma import parse_active_metadata, promote_active_theorem
from scripts.score_iteration import keep_candidate, score_tuple

ACTIVE_RELATIVE = "Formal/Active.lean"
ALLOWED_KEEP_PATHS = {
    "Formal/Active.lean",
    "Formal/GeneratedLemmas.lean",
    "claims/claims.jsonl",
    "claims/candidates.jsonl",
    "state/progress.json",
    "state/metrics.json",
    "state/current_report.md",
}
CANARY_REQUIRED_KEEPS = 3
CANARY_RESUME_CLAIM_ID = "DTREE_INF_003"
REPLAY_STATE_FILES = (
    "Formal/Active.lean",
    "claims/claims.jsonl",
    "claims/candidates.jsonl",
    "state/progress.json",
    "state/metrics.json",
    "state/current_report.md",
)


@dataclass
class AgentRunResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str


@dataclass
class StageFailure(Exception):
    stage: str
    invariant: str
    reason: str


def active_file(root: Path = ROOT) -> Path:
    return root / ACTIVE_RELATIVE


def history_path(root: Path = ROOT) -> Path:
    return root / "state" / "history.jsonl"


def last_message_path(root: Path = ROOT) -> Path:
    return root / "state" / "llm_last_message.md"


def git_status_paths(root: Path = ROOT) -> list[str]:
    process = run_checked(["git", "status", "--porcelain"], cwd=root)
    paths: list[str] = []
    for line in process.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", maxsplit=1)[1]
        paths.append(path)
    return paths


def git_head(root: Path = ROOT) -> str:
    return run_checked(["git", "rev-parse", "HEAD"], cwd=root).stdout.strip()


def ensure_git_identity(root: Path = ROOT) -> None:
    email = run_checked(["git", "config", "user.email"], cwd=root).stdout.strip()
    name = run_checked(["git", "config", "user.name"], cwd=root).stdout.strip()
    if not email:
        run_checked(["git", "config", "user.email", "autoresearch@example.com"], cwd=root)
    if not name:
        run_checked(["git", "config", "user.name", "AutoResearch"], cwd=root)


def require_clean_worktree(root: Path = ROOT) -> None:
    dirty = git_status_paths(root)
    if dirty:
        raise RuntimeError(
            "run_iteration.py requires a clean git worktree before starting. Dirty paths: "
            + ", ".join(dirty)
        )


def snapshot_repo(root: Path = ROOT) -> dict[str, str]:
    snapshot: dict[str, str] = {}
    tracked = run_checked(["git", "ls-files"], cwd=root)
    for relative in tracked.stdout.splitlines():
        if not relative or relative == "state/history.jsonl":
            continue
        snapshot[relative] = (root / relative).read_text()
    return snapshot


def restore_snapshot(snapshot: dict[str, str], *, root: Path = ROOT) -> None:
    for relative, content in snapshot.items():
        write_text(root / relative, content)
    for relative in git_status_paths(root):
        if relative in {"state/history.jsonl", "state/llm_last_message.md"}:
            continue
        if relative in snapshot:
            write_text(root / relative, snapshot[relative])
            continue
        path = root / relative
        if path.exists():
            path.unlink()


def load_agent_context(root: Path = ROOT) -> dict[str, str]:
    required_files = [
        "problem.md",
        "program.md",
        "state/progress.json",
        "claims/claims.jsonl",
        "Formal/Defs.lean",
        "Formal/Known.lean",
        "Formal/Conjectures.lean",
        "Formal/Active.lean",
        "state/metrics.json",
        "state/current_report.md",
        "state/falsifier_current.json",
        "state/falsifier_results.json",
    ]
    context: dict[str, str] = {}
    for relative in required_files:
        context[relative] = read_text_if_exists(root / relative)
    return context


def prompt_summary(root: Path = ROOT) -> str:
    metadata = parse_active_metadata(active_file(root).read_text())
    claim_id = metadata.get("claim_id", "UNKNOWN")
    theorem_name = metadata.get("theorem_name", "UNKNOWN")
    return f"Attempt proof improvement for claim {claim_id} and theorem {theorem_name} by editing only {ACTIVE_RELATIVE}."


def build_agent_prompt(
    *,
    baseline_metrics: dict,
    context: dict[str, str],
    feedback: str | None,
    attempt_number: int,
) -> str:
    sections: list[str] = [
        "You are running one iteration of the decision-tree Lean autoresearch loop.",
        f"This is attempt {attempt_number}.",
        "You must read the provided context and you may modify only Formal/Active.lean.",
        "Do not edit any other file.",
        "Do not run lake build or any python evaluation scripts; the outer harness will do that.",
        "Prefer the smallest proof or theorem refinement that improves the objective score.",
        "Avoid axioms, admit, and sorry unless a sorry already exists in the active shell.",
        "",
        f"Current baseline score: {score_tuple(baseline_metrics)}",
    ]
    if feedback:
        sections.extend(["", "Feedback from the previous discarded attempt:", feedback])
    sections.extend(["", "Context follows."])
    for relative, content in context.items():
        sections.extend(
            [
                "",
                f"=== BEGIN {relative} ===",
                content.rstrip(),
                f"=== END {relative} ===",
            ]
        )
    sections.extend(
        [
            "",
            "Make the edit directly in Formal/Active.lean and then respond with a brief summary of the attempted change.",
        ]
    )
    return "\n".join(sections) + "\n"


def run_codex_agent(prompt: str, *, root: Path = ROOT) -> AgentRunResult:
    cmd = [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "--full-auto",
        "--ephemeral",
        "--color",
        "never",
        "--output-last-message",
        str(last_message_path(root)),
        "-",
    ]
    model = os.environ.get("AUTORESEARCH_MODEL")
    if model:
        cmd[2:2] = ["-m", model]
    process = run_checked_input(cmd, cwd=root, input_text=prompt)
    return AgentRunResult(
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
        last_message=read_text_if_exists(last_message_path(root)),
    )


def evaluate_candidate_patch(root: Path = ROOT) -> tuple[dict, dict[str, str]]:
    build = run_checked(["lake", "build"], cwd=root)
    falsifier = run_checked(["python3", "scripts/falsify_small.py"], cwd=root)
    evaluation = run_checked(["python3", "scripts/eval_iteration.py"], cwd=root)
    metrics = read_json(root / "state" / "metrics.json")
    outputs = {
        "build_stdout": build.stdout,
        "build_stderr": build.stderr,
        "falsifier_stdout": falsifier.stdout,
        "falsifier_stderr": falsifier.stderr,
        "eval_stdout": evaluation.stdout,
        "eval_stderr": evaluation.stderr,
    }
    return metrics, outputs


def evaluate_post_keep_state(root: Path = ROOT) -> tuple[dict, dict[str, str]]:
    build = run_checked(["lake", "build"], cwd=root)
    evaluation = run_checked(["python3", "scripts/eval_iteration.py"], cwd=root)
    metrics = read_json(root / "state" / "metrics.json")
    outputs = {
        "build_stdout": build.stdout,
        "build_stderr": build.stderr,
        "eval_stdout": evaluation.stdout,
        "eval_stderr": evaluation.stderr,
    }
    return metrics, outputs


def changed_paths_after_agent(root: Path = ROOT) -> list[str]:
    return git_status_paths(root)


def changed_paths_since_snapshot(snapshot: dict[str, str], *, root: Path = ROOT) -> list[str]:
    changed: set[str] = set()
    for relative, content in snapshot.items():
        path = root / relative
        if not path.exists() or path.read_text() != content:
            changed.add(relative)
    for relative in git_status_paths(root):
        if relative not in snapshot:
            changed.add(relative)
    return sorted(changed)


def unauthorized_changes(paths: list[str]) -> list[str]:
    return [path for path in paths if path != ACTIVE_RELATIVE]


def active_theorem_fully_proved(root: Path = ROOT) -> bool:
    text = active_file(root).read_text()
    metadata = parse_active_metadata(text)
    theorem_name = metadata.get("theorem_name")
    claim_id = metadata.get("claim_id")
    if not theorem_name or not claim_id or claim_id == "NONE":
        return False
    has_sorry = re.search(r"\bsorry\b", text) is not None
    return not has_sorry and re.search(rf"(?m)^\s*theorem\s+{re.escape(theorem_name)}\b", text) is not None


def tracked_paths_for_commit(root: Path = ROOT) -> list[str]:
    return [path for path in sorted(ALLOWED_KEEP_PATHS) if (root / path).exists()]


def git_commit(message: str, *, root: Path = ROOT) -> str:
    paths = tracked_paths_for_commit(root)
    add = run_checked(["git", "add", *paths], cwd=root)
    if add.returncode != 0:
        raise RuntimeError(add.stderr or add.stdout or "git add failed")
    commit = run_checked(["git", "commit", "-m", message], cwd=root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")
    return git_head(root)


def update_progress_latest_kept_commit(commit_hash: str, *, root: Path = ROOT) -> None:
    progress_path = root / "state" / "progress.json"
    progress = read_json(progress_path)
    progress["latest_kept_commit"] = commit_hash
    write_json(progress_path, progress)


def git_commit_paths(message: str, paths: list[str], *, root: Path = ROOT) -> str:
    add = run_checked(["git", "add", *paths], cwd=root)
    if add.returncode != 0:
        raise RuntimeError(add.stderr or add.stdout or "git add failed")
    commit = run_checked(["git", "commit", "-m", message], cwd=root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")
    return git_head(root)


def record_latest_kept_commit(commit_hash: str, *, root: Path = ROOT) -> str:
    progress_path = root / "state" / "progress.json"
    committed_progress = progress_path.read_text()
    update_progress_latest_kept_commit(commit_hash, root=root)
    try:
        return git_commit_paths(
            f"codex: record latest kept commit {commit_hash[:12]}",
            ["state/progress.json"],
            root=root,
        )
    except RuntimeError as exc:
        write_text(progress_path, committed_progress)
        raise RuntimeError(f"record_latest_kept_commit_failed: {exc}") from exc


def load_history(root: Path = ROOT) -> list[dict]:
    return load_jsonl(history_path(root))


def write_history(rows: list[dict], *, root: Path = ROOT) -> None:
    write_jsonl(history_path(root), rows)


def append_history(payload: dict, *, root: Path = ROOT) -> None:
    rows = load_history(root)
    rows.append(payload)
    write_history(rows, root=root)


def update_history_entry(iteration_id: str, updates: dict[str, object], *, root: Path = ROOT) -> None:
    rows = load_history(root)
    for row in reversed(rows):
        if row.get("iteration_id") == iteration_id:
            row.update(updates)
            write_history(rows, root=root)
            return
    raise ValueError(f"Missing history entry for iteration_id={iteration_id}.")


def iteration_claim_and_theorem(root: Path = ROOT) -> tuple[str | None, str | None]:
    metadata = parse_active_metadata(active_file(root).read_text())
    return metadata.get("claim_id"), metadata.get("theorem_name")


def collect_frontier(root: Path = ROOT) -> dict[str, str | None]:
    metadata = parse_active_metadata(active_file(root).read_text())
    progress = read_json(root / "state" / "progress.json")
    return {
        "active_claim_id": progress.get("active_claim_id"),
        "active_story_id": progress.get("active_story_id"),
        "metadata_claim_id": metadata.get("claim_id"),
        "metadata_story_id": metadata.get("story_id"),
        "theorem_name": metadata.get("theorem_name"),
    }


def capture_replay_state(root: Path = ROOT) -> dict[str, str]:
    return {relative: (root / relative).read_text() for relative in REPLAY_STATE_FILES if (root / relative).exists()}


def restore_replay_state(state: dict[str, str], *, root: Path = ROOT) -> None:
    for relative, content in state.items():
        write_text(root / relative, content)


def next_iteration_id(claim_id: str | None, attempt_number: int, *, root: Path = ROOT) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    claim = (claim_id or "unknown").lower()
    return f"{stamp}-{claim}-a{attempt_number:02d}-{len(load_history(root)) + 1:04d}"


def is_canary_mode_enabled(root: Path = ROOT) -> bool:
    return os.environ.get("AUTORESEARCH_DISABLE_CANARY", "0") != "1"


def consecutive_canary_keeps(root: Path = ROOT) -> int:
    streak = 0
    for entry in reversed(load_history(root)):
        if not entry.get("canary_mode"):
            if streak:
                break
            return 0
        if entry.get("status") == "kept":
            streak += 1
            continue
        return 0
    return streak


def promoted_canary_count(root: Path = ROOT) -> int:
    return sum(1 for row in load_jsonl(root / "claims" / "claims.jsonl") if is_canary_claim_id(row["claim_id"]) and row["status"] == "proved")


def ensure_claim_rows(root: Path, claim_id: str, *, status: str, lean_status: str) -> None:
    if not is_canary_claim_id(claim_id):
        return
    index = canary_claim_index(claim_id)
    for relative in ("claims/claims.jsonl", "claims/candidates.jsonl"):
        path = root / relative
        rows = load_jsonl(path)
        if any(row["claim_id"] == claim_id for row in rows):
            continue
        rows.append(canary_claim_row(index, status=status, lean_status=lean_status))
        write_jsonl(path, rows)


def activate_claim(root: Path, claim_id: str) -> None:
    ensure_claim_rows(root, claim_id, status="active", lean_status="statement_compiles")
    for relative in ("claims/claims.jsonl", "claims/candidates.jsonl"):
        path = root / relative
        rows = load_jsonl(path)
        updated: list[dict] = []
        found = False
        for row in rows:
            row = dict(row)
            if row["claim_id"] == claim_id:
                row["status"] = "active"
                if row.get("lean_status") == "not_started":
                    row["lean_status"] = "statement_compiles"
                found = True
            elif row.get("status") == "active":
                row["status"] = "candidate"
            updated.append(row)
        if not found and is_canary_claim_id(claim_id):
            updated.append(canary_claim_row(canary_claim_index(claim_id), status="active", lean_status="statement_compiles"))
        write_jsonl(path, updated)

    progress = read_json(root / "state" / "progress.json")
    progress["active_claim_id"] = claim_id
    progress["active_story_id"] = infer_story_id(claim_id)
    found_progress_claim = False
    for claim in progress.get("claims", []):
        if claim.get("status") == "active" and claim.get("claim_id") != claim_id:
            claim["status"] = "candidate"
        if claim.get("claim_id") == claim_id:
            claim["status"] = "active"
            if claim.get("lean_status") == "not_started":
                claim["lean_status"] = "statement_compiles"
            found_progress_claim = True
    if not found_progress_claim:
        progress.setdefault("claims", []).append(
            {
                "claim_id": claim_id,
                "status": "active",
                "lean_status": "statement_compiles",
                "falsifier_status": "survives_small_n",
            }
        )
    write_json(root / "state" / "progress.json", progress)
    from scripts.claim_templates import active_template_for_claim

    write_text(active_file(root), active_template_for_claim(claim_id))


def prepare_frontier(root: Path = ROOT) -> dict[str, object]:
    progress = read_json(root / "state" / "progress.json")
    current_claim_id = progress.get("active_claim_id")
    streak = consecutive_canary_keeps(root)
    if streak >= CANARY_REQUIRED_KEEPS and is_canary_claim_id(current_claim_id):
        activate_claim(root, CANARY_RESUME_CLAIM_ID)
        return {
            "canary_mode": False,
            "canary_streak": streak,
            "active_claim_id": CANARY_RESUME_CLAIM_ID,
        }
    if not is_canary_mode_enabled(root) or streak >= CANARY_REQUIRED_KEEPS:
        return {
            "canary_mode": False,
            "canary_streak": streak,
            "active_claim_id": current_claim_id,
        }
    if is_canary_claim_id(current_claim_id):
        activate_claim(root, current_claim_id)
        return {
            "canary_mode": True,
            "canary_streak": streak,
            "active_claim_id": current_claim_id,
        }
    next_canary_claim_id = canary_claim_id(promoted_canary_count(root) + 1)
    activate_claim(root, next_canary_claim_id)
    return {
        "canary_mode": True,
        "canary_streak": streak,
        "active_claim_id": next_canary_claim_id,
    }


def next_claim_after_promotion(promoted_claim_id: str | None, *, canary_mode: bool, canary_streak: int) -> str | None:
    if not canary_mode or promoted_claim_id is None or not is_canary_claim_id(promoted_claim_id):
        return None
    if canary_streak + 1 >= CANARY_REQUIRED_KEEPS:
        return CANARY_RESUME_CLAIM_ID
    return canary_claim_id(canary_claim_index(promoted_claim_id) + 1)


def sync_iteration_metadata(
    *,
    root: Path,
    iteration_id: str,
    status: str,
    changed_claim_ids: list[str],
    changed_theorem_names: list[str],
    keep_reason: str,
    canary_mode: bool,
) -> None:
    metrics = read_json(root / "state" / "metrics.json")
    metrics["iteration_id"] = iteration_id
    metrics["iteration_status"] = status
    metrics["changed_claim_ids"] = changed_claim_ids
    metrics["changed_theorem_names"] = changed_theorem_names
    metrics["keep_reason"] = keep_reason
    metrics["canary_mode"] = canary_mode
    write_json(root / "state" / "metrics.json", metrics)

    progress = read_json(root / "state" / "progress.json")
    progress["last_iteration_id"] = iteration_id
    progress["last_iteration_status"] = status
    progress["last_keep_reason"] = keep_reason
    progress["last_iteration_canary_mode"] = canary_mode
    write_json(root / "state" / "progress.json", progress)

    def update_claim_file(path: Path) -> None:
        rows = load_jsonl(path)
        updated: list[dict] = []
        for row in rows:
            row = dict(row)
            if row["claim_id"] in changed_claim_ids or row["claim_id"] == progress.get("active_claim_id"):
                row["last_iteration_id"] = iteration_id
                row["last_iteration_status"] = status
            updated.append(row)
        write_jsonl(path, updated)

    update_claim_file(root / "claims" / "claims.jsonl")
    update_claim_file(root / "claims" / "candidates.jsonl")


def history_agrees(
    *,
    root: Path,
    iteration_id: str,
    status: str,
    changed_claim_ids: list[str],
) -> tuple[bool, str]:
    metrics = read_json(root / "state" / "metrics.json")
    progress = read_json(root / "state" / "progress.json")
    history_entries = load_history(root)
    entry = next((row for row in reversed(history_entries) if row.get("iteration_id") == iteration_id), None)
    if metrics.get("iteration_id") != iteration_id or metrics.get("iteration_status") != status:
        return False, "metrics_iteration_mismatch"
    if progress.get("last_iteration_id") != iteration_id or progress.get("last_iteration_status") != status:
        return False, "progress_iteration_mismatch"
    if entry is None or entry.get("status") != status:
        return False, "history_iteration_mismatch"
    claims_rows = load_jsonl(root / "claims" / "claims.jsonl")
    for claim_id in changed_claim_ids:
        row = next((candidate for candidate in claims_rows if candidate["claim_id"] == claim_id), None)
        if row is None:
            return False, f"claim_missing:{claim_id}"
        if row.get("last_iteration_id") != iteration_id or row.get("last_iteration_status") != status:
            return False, f"claim_iteration_mismatch:{claim_id}"
    return True, "ok"


def promoted_lemma_visible(theorem_name: str, *, root: Path = ROOT) -> bool:
    with tempfile.NamedTemporaryFile("w", suffix=".lean", delete=False) as handle:
        handle.write(f"import Formal.GeneratedLemmas\n\nopen Formal\n\n#check {theorem_name}\n")
        temp_path = Path(handle.name)
    try:
        process = run_checked(["lake", "env", "lean", str(temp_path)], cwd=root)
        return process.returncode == 0
    finally:
        temp_path.unlink(missing_ok=True)


def run_post_keep_invariants(
    *,
    root: Path,
    iteration_id: str,
    changed_claim_ids: list[str],
    promotion: dict | None,
) -> tuple[bool, str]:
    changed_paths = set(git_status_paths(root))
    if not changed_paths.issubset(ALLOWED_KEEP_PATHS):
        extras = ", ".join(sorted(changed_paths - ALLOWED_KEEP_PATHS))
        return False, f"only_allowed_files_changed:{extras}"

    build = run_checked(["lake", "build"], cwd=root)
    if build.returncode != 0:
        return False, "post_promotion_build_failed"

    if promotion is not None:
        theorem_name = promotion["theorem_name"]
        if theorem_name in active_file(root).read_text():
            return False, "promoted_theorem_still_in_active"
        generated_text = (root / "Formal" / "GeneratedLemmas.lean").read_text()
        if theorem_name not in generated_text:
            return False, "promoted_theorem_missing_from_generated"
        if not promoted_lemma_visible(theorem_name, root=root):
            return False, "promoted_lemma_not_visible"

    history_ok, history_reason = history_agrees(
        root=root,
        iteration_id=iteration_id,
        status="kept",
        changed_claim_ids=changed_claim_ids,
    )
    if not history_ok:
        return False, history_reason

    return True, "ok"


def format_feedback(reason: str, attempt_outputs: dict[str, str], changed_files: list[str]) -> str:
    lines = [
        f"Decision reason: {reason}",
        f"Changed files after agent edit: {changed_files}",
    ]
    for key in ("build_stderr", "falsifier_stderr", "eval_stderr"):
        value = attempt_outputs.get(key, "").strip()
        if value:
            lines.extend([f"{key}:", value[-2000:]])
    for key in ("build_stdout", "falsifier_stdout", "eval_stdout"):
        value = attempt_outputs.get(key, "").strip()
        if value:
            lines.extend([f"{key}:", value[-2000:]])
    return "\n".join(lines)


def build_history_payload(
    *,
    iteration_id: str,
    attempt_number: int,
    prompt_summary_text: str,
    changed_claim_ids: list[str],
    changed_theorem_names: list[str],
    before_metrics: dict,
    after_metrics: dict,
    status: str,
    commit_hash: str | None,
    keep_reason: str,
    failure_stage: str | None,
    failure_invariant: str | None,
    agent_message: str,
    base_commit: str,
    baseline_state: dict[str, str],
    candidate_active_text: str,
    frontier_before: dict[str, str | None],
    frontier_after: dict[str, str | None],
    agent_changed_files: list[str],
    promotion: dict | None,
    canary_mode: bool,
) -> dict:
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iteration_id": iteration_id,
        "attempt_number": attempt_number,
        "prompt_summary": prompt_summary_text,
        "changed_claim_ids": changed_claim_ids,
        "changed_theorem_names": changed_theorem_names,
        "changed_claim_id": changed_claim_ids[0] if changed_claim_ids else None,
        "changed_theorem_name": changed_theorem_names[0] if changed_theorem_names else None,
        "score_before": list(score_tuple(before_metrics)),
        "score_after": list(score_tuple(after_metrics)),
        "status": status,
        "commit_hash": commit_hash,
        "keep_reason": keep_reason,
        "failure_stage": failure_stage,
        "failure_invariant": failure_invariant,
        "agent_message": agent_message.strip(),
        "base_commit": base_commit,
        "baseline_state": baseline_state,
        "candidate_active_text": candidate_active_text,
        "frontier_before": frontier_before,
        "frontier_after": frontier_after,
        "agent_changed_files": agent_changed_files,
        "promotion": promotion,
        "canary_mode": canary_mode,
    }


def maybe_promote_and_reseed(*, root: Path, next_claim_id: str | None) -> dict[str, object] | None:
    if not active_theorem_fully_proved(root):
        return None
    if next_claim_id is not None:
        ensure_claim_rows(root, next_claim_id, status="candidate", lean_status="not_started")
    result = promote_active_theorem(root=root, next_claim_id=next_claim_id)
    return asdict(result)


def make_replay_runner(candidate_active_text: str, agent_message: str, *, root: Path) -> Callable[[str], AgentRunResult]:
    def replay_runner(_prompt: str) -> AgentRunResult:
        write_text(active_file(root), candidate_active_text)
        return AgentRunResult(returncode=0, stdout="", stderr="", last_message=agent_message)

    return replay_runner


def run_iteration(
    *,
    root: Path = ROOT,
    codex_runner: Callable[[str], AgentRunResult] | None = None,
    max_attempts: int | None = None,
) -> dict[str, object]:
    require_clean_worktree(root)
    ensure_git_identity(root)
    codex_runner = codex_runner or (lambda prompt: run_codex_agent(prompt, root=root))
    max_attempts = max_attempts or int(os.environ.get("AUTORESEARCH_MAX_ATTEMPTS", "2"))

    pristine_snapshot = snapshot_repo(root)
    base_commit = git_head(root)
    frontier_mode = prepare_frontier(root)

    baseline_metrics, baseline_outputs = evaluate_candidate_patch(root)
    baseline_snapshot = snapshot_repo(root)
    baseline_state = capture_replay_state(root)
    prompt_summary_text = prompt_summary(root)
    previous_feedback: str | None = None

    for attempt_number in range(1, max_attempts + 1):
        restore_snapshot(baseline_snapshot, root=root)
        context = load_agent_context(root)
        prompt = build_agent_prompt(
            baseline_metrics=baseline_metrics,
            context=context,
            feedback=previous_feedback,
            attempt_number=attempt_number,
        )
        claim_id, theorem_name = iteration_claim_and_theorem(root)
        iteration_id = next_iteration_id(claim_id, attempt_number, root=root)
        frontier_before = collect_frontier(root)

        agent_result = codex_runner(prompt)
        agent_changed_files = changed_paths_since_snapshot(baseline_snapshot, root=root)
        candidate_active_text = active_file(root).read_text()

        if agent_result.returncode != 0:
            restore_snapshot(baseline_snapshot, root=root)
            payload = build_history_payload(
                iteration_id=iteration_id,
                attempt_number=attempt_number,
                prompt_summary_text=prompt_summary_text,
                changed_claim_ids=[claim_id] if claim_id else [],
                changed_theorem_names=[theorem_name] if theorem_name else [],
                before_metrics=baseline_metrics,
                after_metrics=baseline_metrics,
                status="discarded",
                commit_hash=None,
                keep_reason="agent_returncode_nonzero",
                failure_stage="agent_edit",
                failure_invariant="codex_runner_failed",
                agent_message=agent_result.last_message or agent_result.stderr or agent_result.stdout,
                base_commit=base_commit,
                baseline_state=baseline_state,
                candidate_active_text=candidate_active_text,
                frontier_before=frontier_before,
                frontier_after=frontier_before,
                agent_changed_files=agent_changed_files,
                promotion=None,
                canary_mode=bool(frontier_mode["canary_mode"]),
            )
            append_history(payload, root=root)
            previous_feedback = "The previous edit attempt failed before evaluation."
            continue

        bad_files = unauthorized_changes(agent_changed_files)
        if bad_files:
            restore_snapshot(baseline_snapshot, root=root)
            payload = build_history_payload(
                iteration_id=iteration_id,
                attempt_number=attempt_number,
                prompt_summary_text=prompt_summary_text,
                changed_claim_ids=[claim_id] if claim_id else [],
                changed_theorem_names=[theorem_name] if theorem_name else [],
                before_metrics=baseline_metrics,
                after_metrics=baseline_metrics,
                status="discarded",
                commit_hash=None,
                keep_reason=f"unauthorized_file_changes:{', '.join(bad_files)}",
                failure_stage="agent_edit",
                failure_invariant="only_formal_active_changed",
                agent_message=agent_result.last_message,
                base_commit=base_commit,
                baseline_state=baseline_state,
                candidate_active_text=candidate_active_text,
                frontier_before=frontier_before,
                frontier_after=frontier_before,
                agent_changed_files=agent_changed_files,
                promotion=None,
                canary_mode=bool(frontier_mode["canary_mode"]),
            )
            append_history(payload, root=root)
            previous_feedback = format_feedback(payload["keep_reason"], baseline_outputs, agent_changed_files)
            continue

        trial_metrics, outputs = evaluate_candidate_patch(root)
        keep, reason = keep_candidate(trial_metrics, baseline_metrics)
        if not keep:
            frontier_after = collect_frontier(root)
            restore_snapshot(baseline_snapshot, root=root)
            payload = build_history_payload(
                iteration_id=iteration_id,
                attempt_number=attempt_number,
                prompt_summary_text=prompt_summary_text,
                changed_claim_ids=[claim_id] if claim_id else [],
                changed_theorem_names=[theorem_name] if theorem_name else [],
                before_metrics=baseline_metrics,
                after_metrics=trial_metrics,
                status="discarded",
                commit_hash=None,
                keep_reason=reason,
                failure_stage="keep_decision",
                failure_invariant="objective_score_not_improved",
                agent_message=agent_result.last_message or format_feedback(reason, outputs, agent_changed_files),
                base_commit=base_commit,
                baseline_state=baseline_state,
                candidate_active_text=candidate_active_text,
                frontier_before=frontier_before,
                frontier_after=frontier_after,
                agent_changed_files=agent_changed_files,
                promotion=None,
                canary_mode=bool(frontier_mode["canary_mode"]),
            )
            append_history(payload, root=root)
            previous_feedback = format_feedback(reason, outputs, agent_changed_files)
            continue

        promotion: dict[str, object] | None = None
        changed_claim_ids = [claim_id] if claim_id else []
        changed_theorem_names = [theorem_name] if theorem_name else []

        try:
            next_claim_id = next_claim_after_promotion(
                claim_id,
                canary_mode=bool(frontier_mode["canary_mode"]),
                canary_streak=int(frontier_mode["canary_streak"]),
            )
            promotion = maybe_promote_and_reseed(root=root, next_claim_id=next_claim_id)
            if promotion is not None:
                changed_claim_ids = [promotion["promoted_claim_id"]]
                if promotion.get("next_claim_id"):
                    changed_claim_ids.append(str(promotion["next_claim_id"]))
                changed_theorem_names = [str(promotion["theorem_name"])]
                new_active_meta = parse_active_metadata(active_file(root).read_text())
                next_theorem_name = new_active_meta.get("theorem_name")
                if next_theorem_name and next_theorem_name != theorem_name:
                    changed_theorem_names.append(next_theorem_name)

            final_metrics, final_outputs = evaluate_post_keep_state(root)
            final_keep, final_reason = keep_candidate(final_metrics, baseline_metrics)
            if not final_keep:
                raise StageFailure("post_keep_eval", "objective_score_after_promotion", final_reason)

            sync_iteration_metadata(
                root=root,
                iteration_id=iteration_id,
                status="kept",
                changed_claim_ids=changed_claim_ids,
                changed_theorem_names=changed_theorem_names,
                keep_reason=final_reason,
                canary_mode=bool(frontier_mode["canary_mode"]),
            )

            frontier_after = collect_frontier(root)
            history_payload = build_history_payload(
                iteration_id=iteration_id,
                attempt_number=attempt_number,
                prompt_summary_text=prompt_summary_text,
                changed_claim_ids=changed_claim_ids,
                changed_theorem_names=changed_theorem_names,
                before_metrics=baseline_metrics,
                after_metrics=final_metrics,
                status="kept",
                commit_hash=None,
                keep_reason=final_reason,
                failure_stage=None,
                failure_invariant=None,
                agent_message=agent_result.last_message,
                base_commit=base_commit,
                baseline_state=baseline_state,
                candidate_active_text=candidate_active_text,
                frontier_before=frontier_before,
                frontier_after=frontier_after,
                agent_changed_files=agent_changed_files,
                promotion=promotion,
                canary_mode=bool(frontier_mode["canary_mode"]),
            )
            append_history(history_payload, root=root)

            invariants_ok, invariant_reason = run_post_keep_invariants(
                root=root,
                iteration_id=iteration_id,
                changed_claim_ids=changed_claim_ids,
                promotion=promotion,
            )
            if not invariants_ok:
                raise StageFailure("invariants", invariant_reason, invariant_reason)

            commit_hash = git_commit(f"codex: keep iteration {iteration_id}", root=root)
            metadata_commit_hash = record_latest_kept_commit(commit_hash, root=root)
            update_history_entry(
                iteration_id,
                {
                    "commit_hash": commit_hash,
                    "progress_commit_hash": metadata_commit_hash,
                },
                root=root,
            )
            if git_status_paths(root):
                raise StageFailure("commit", "clean_committed_state", "git worktree is not clean after commit")

            return {
                "status": "kept",
                "commit": commit_hash,
                "progress_commit": metadata_commit_hash,
                "reason": final_reason,
                "promotion": promotion,
                "agent_message": agent_result.last_message,
                "iteration_id": iteration_id,
                "canary_mode": frontier_mode["canary_mode"],
            }
        except StageFailure as failure:
            restore_snapshot(baseline_snapshot, root=root)
            frontier_after = collect_frontier(root)
            try:
                update_history_entry(
                    iteration_id,
                    {
                        "status": "discarded",
                        "commit_hash": None,
                        "failure_stage": failure.stage,
                        "failure_invariant": failure.invariant,
                        "keep_reason": failure.reason,
                        "frontier_after": frontier_after,
                    },
                    root=root,
                )
            except ValueError:
                payload = build_history_payload(
                    iteration_id=iteration_id,
                    attempt_number=attempt_number,
                    prompt_summary_text=prompt_summary_text,
                    changed_claim_ids=changed_claim_ids,
                    changed_theorem_names=changed_theorem_names,
                    before_metrics=baseline_metrics,
                    after_metrics=trial_metrics,
                    status="discarded",
                    commit_hash=None,
                    keep_reason=failure.reason,
                    failure_stage=failure.stage,
                    failure_invariant=failure.invariant,
                    agent_message=agent_result.last_message,
                    base_commit=base_commit,
                    baseline_state=baseline_state,
                    candidate_active_text=candidate_active_text,
                    frontier_before=frontier_before,
                    frontier_after=frontier_after,
                    agent_changed_files=agent_changed_files,
                    promotion=promotion,
                    canary_mode=bool(frontier_mode["canary_mode"]),
                )
                append_history(payload, root=root)
            previous_feedback = format_feedback(failure.reason, outputs | final_outputs, agent_changed_files)
            continue
        except RuntimeError as failure:
            restore_snapshot(baseline_snapshot, root=root)
            frontier_after = collect_frontier(root)
            try:
                update_history_entry(
                    iteration_id,
                    {
                        "status": "discarded",
                        "commit_hash": None,
                        "failure_stage": "commit",
                        "failure_invariant": "git_commit_failed",
                        "keep_reason": str(failure),
                        "frontier_after": frontier_after,
                    },
                    root=root,
                )
            except ValueError:
                payload = build_history_payload(
                    iteration_id=iteration_id,
                    attempt_number=attempt_number,
                    prompt_summary_text=prompt_summary_text,
                    changed_claim_ids=changed_claim_ids,
                    changed_theorem_names=changed_theorem_names,
                    before_metrics=baseline_metrics,
                    after_metrics=trial_metrics,
                    status="discarded",
                    commit_hash=None,
                    keep_reason=str(failure),
                    failure_stage="commit",
                    failure_invariant="git_commit_failed",
                    agent_message=agent_result.last_message,
                    base_commit=base_commit,
                    baseline_state=baseline_state,
                    candidate_active_text=candidate_active_text,
                    frontier_before=frontier_before,
                    frontier_after=frontier_after,
                    agent_changed_files=agent_changed_files,
                    promotion=promotion,
                    canary_mode=bool(frontier_mode["canary_mode"]),
                )
                append_history(payload, root=root)
            previous_feedback = str(failure)
            continue
        except ValueError as failure:
            restore_snapshot(baseline_snapshot, root=root)
            frontier_after = collect_frontier(root)
            try:
                update_history_entry(
                    iteration_id,
                    {
                        "status": "discarded",
                        "commit_hash": None,
                        "failure_stage": "promotion",
                        "failure_invariant": "promotion_failed",
                        "keep_reason": str(failure),
                        "frontier_after": frontier_after,
                    },
                    root=root,
                )
            except ValueError:
                payload = build_history_payload(
                    iteration_id=iteration_id,
                    attempt_number=attempt_number,
                    prompt_summary_text=prompt_summary_text,
                    changed_claim_ids=changed_claim_ids,
                    changed_theorem_names=changed_theorem_names,
                    before_metrics=baseline_metrics,
                    after_metrics=trial_metrics,
                    status="discarded",
                    commit_hash=None,
                    keep_reason=str(failure),
                    failure_stage="promotion",
                    failure_invariant="promotion_failed",
                    agent_message=agent_result.last_message,
                    base_commit=base_commit,
                    baseline_state=baseline_state,
                    candidate_active_text=candidate_active_text,
                    frontier_before=frontier_before,
                    frontier_after=frontier_after,
                    agent_changed_files=agent_changed_files,
                    promotion=promotion,
                    canary_mode=bool(frontier_mode["canary_mode"]),
                )
                append_history(payload, root=root)
            previous_feedback = str(failure)
            continue

    restore_snapshot(pristine_snapshot, root=root)
    return {"status": "discarded", "reason": "max_attempts_exhausted", "score": baseline_metrics["score"]}


def replay_history_entry(
    *,
    root: Path = ROOT,
    iteration_id: str | None = None,
    index: int | None = None,
) -> dict[str, object]:
    entries = load_history(root)
    if not entries:
        raise RuntimeError("state/history.jsonl is empty.")
    if iteration_id is not None:
        entry = next((row for row in entries if row.get("iteration_id") == iteration_id), None)
        if entry is None:
            raise RuntimeError(f"No history entry found for iteration_id={iteration_id}.")
    else:
        if index is None:
            index = -1
        entry = entries[index]

    required = {"base_commit", "baseline_state", "candidate_active_text", "score_before"}
    missing = sorted(field for field in required if field not in entry)
    if missing:
        raise RuntimeError(
            "Selected history entry is missing replay data. Found fields are insufficient for deterministic replay: "
            + ", ".join(missing)
        )

    with tempfile.TemporaryDirectory(prefix="autoresearch-replay-") as tmpdir:
        replay_root = Path(tmpdir) / "repo"
        clone = run_checked(["git", "clone", str(root), str(replay_root)], cwd=root)
        if clone.returncode != 0:
            raise RuntimeError(clone.stderr or clone.stdout or "git clone failed")
        checkout = run_checked(["git", "checkout", entry["base_commit"]], cwd=replay_root)
        if checkout.returncode != 0:
            raise RuntimeError(checkout.stderr or checkout.stdout or "git checkout failed")
        ensure_git_identity(replay_root)
        restore_replay_state(entry["baseline_state"], root=replay_root)
        result = run_iteration(
            root=replay_root,
            codex_runner=make_replay_runner(
                entry["candidate_active_text"],
                entry.get("agent_message", "Replayed candidate patch."),
                root=replay_root,
            ),
            max_attempts=1,
        )
        actual_entry = load_history(replay_root)[-1]
        payload = {
            "selected_iteration_id": entry.get("iteration_id"),
            "expected_status": entry.get("status"),
            "expected_failure_stage": entry.get("failure_stage"),
            "expected_failure_invariant": entry.get("failure_invariant"),
            "replayed_status": result.get("status"),
            "replayed_failure_stage": actual_entry.get("failure_stage"),
            "replayed_failure_invariant": actual_entry.get("failure_invariant"),
            "replayed_iteration_id": actual_entry.get("iteration_id"),
        }
        print(json.dumps(payload, indent=2))
        return payload


def main() -> int:
    try:
        result = run_iteration()
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        return 1
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "kept" else 1


if __name__ == "__main__":
    sys.exit(main())
