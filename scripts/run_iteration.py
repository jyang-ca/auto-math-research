from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.claim_templates import infer_story_id
from scripts.common import STATE_DIR, append_jsonl, read_json, read_text_if_exists, run_checked, run_checked_input, write_text
from scripts.promote_lemma import parse_active_metadata, promote_active_theorem
from scripts.score_iteration import keep_candidate, score_tuple

ACTIVE_RELATIVE = "Formal/Active.lean"
ATTEMPT_OUTPUT_KEYS = ("metrics.json", "current_report.md", "falsifier_current.json", "falsifier_results.json")


@dataclass
class AgentRunResult:
    returncode: int
    stdout: str
    stderr: str
    last_message: str


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


def changed_paths_after_agent(root: Path = ROOT) -> list[str]:
    return git_status_paths(root)


def unauthorized_changes(paths: list[str]) -> list[str]:
    return [path for path in paths if path != ACTIVE_RELATIVE]


def active_theorem_fully_proved(root: Path = ROOT) -> bool:
    text = active_file(root).read_text()
    metadata = parse_active_metadata(text)
    theorem_name = metadata.get("theorem_name")
    claim_id = metadata.get("claim_id")
    if not theorem_name or not claim_id or claim_id == "NONE":
        return False
    return "sorry" not in text and re.search(rf"(?m)^\s*theorem\s+{re.escape(theorem_name)}\b", text) is not None


def tracked_paths_for_commit(root: Path = ROOT) -> list[str]:
    candidate_paths = [
        "Formal/Active.lean",
        "Formal/GeneratedLemmas.lean",
        "claims/claims.jsonl",
        "claims/candidates.jsonl",
        "state/progress.json",
        "state/metrics.json",
        "state/current_report.md",
    ]
    return [path for path in candidate_paths if (root / path).exists()]


def git_commit(message: str, *, root: Path = ROOT) -> str:
    paths = tracked_paths_for_commit(root)
    add = run_checked(["git", "add", *paths], cwd=root)
    if add.returncode != 0:
        raise RuntimeError(add.stderr or add.stdout or "git add failed")
    commit = run_checked(["git", "commit", "-m", message], cwd=root)
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr or commit.stdout or "git commit failed")
    rev = run_checked(["git", "rev-parse", "HEAD"], cwd=root)
    if rev.returncode != 0:
        raise RuntimeError(rev.stderr or rev.stdout or "git rev-parse failed")
    return rev.stdout.strip()


def append_history(
    *,
    prompt_summary_text: str,
    changed_claim_id: str | None,
    changed_theorem_name: str | None,
    before_metrics: dict,
    after_metrics: dict,
    status: str,
    commit_hash: str | None,
    agent_message: str,
    attempt_number: int,
    root: Path = ROOT,
) -> None:
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "attempt_number": attempt_number,
        "prompt_summary": prompt_summary_text,
        "changed_claim_id": changed_claim_id,
        "changed_theorem_name": changed_theorem_name,
        "score_before": list(score_tuple(before_metrics)),
        "score_after": list(score_tuple(after_metrics)),
        "status": status,
        "commit_hash": commit_hash,
        "agent_message": agent_message.strip(),
    }
    append_jsonl(history_path(root), payload)


def maybe_promote_and_reseed(root: Path = ROOT) -> dict[str, str] | None:
    if not active_theorem_fully_proved(root):
        return None
    result = promote_active_theorem(root=root)
    return asdict(result)


def iteration_claim_and_theorem(root: Path = ROOT) -> tuple[str | None, str | None]:
    metadata = parse_active_metadata(active_file(root).read_text())
    return metadata.get("claim_id"), metadata.get("theorem_name")


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


def run_iteration(
    *,
    root: Path = ROOT,
    codex_runner: Callable[[str], AgentRunResult] | None = None,
    max_attempts: int | None = None,
) -> dict[str, object]:
    require_clean_worktree(root)
    codex_runner = codex_runner or (lambda prompt: run_codex_agent(prompt, root=root))
    max_attempts = max_attempts or int(os.environ.get("AUTORESEARCH_MAX_ATTEMPTS", "2"))

    baseline_metrics, _ = evaluate_candidate_patch(root)
    prompt_summary_text = prompt_summary(root)
    baseline_snapshot = snapshot_repo(root)
    previous_feedback: str | None = None

    if active_theorem_fully_proved(root):
        claim_id, theorem_name = iteration_claim_and_theorem(root)
        promotion = maybe_promote_and_reseed(root)
        final_metrics, outputs = evaluate_candidate_patch(root)
        keep, reason = keep_candidate(final_metrics, baseline_metrics)
        if keep:
            commit_hash = git_commit("codex: promote proved active theorem", root=root)
            append_history(
                prompt_summary_text="Promote already-proved active theorem",
                changed_claim_id=claim_id,
                changed_theorem_name=theorem_name,
                before_metrics=baseline_metrics,
                after_metrics=final_metrics,
                status="kept",
                commit_hash=commit_hash,
                agent_message=json.dumps(promotion, sort_keys=True),
                attempt_number=0,
                root=root,
            )
            return {"status": "kept", "commit": commit_hash, "reason": reason, "promotion": promotion}
        restore_snapshot(baseline_snapshot, root=root)
        append_history(
            prompt_summary_text="Promote already-proved active theorem",
            changed_claim_id=claim_id,
            changed_theorem_name=theorem_name,
            before_metrics=baseline_metrics,
            after_metrics=final_metrics,
            status="discarded",
            commit_hash=None,
            agent_message=format_feedback(reason, outputs, changed_paths_after_agent(root)),
            attempt_number=0,
            root=root,
        )
        return {"status": "discarded", "reason": reason}

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
        agent_result = codex_runner(prompt)
        trial_metrics, outputs = evaluate_candidate_patch(root)
        changed_files = changed_paths_after_agent(root)
        bad_files = unauthorized_changes(changed_files)
        keep, reason = keep_candidate(trial_metrics, baseline_metrics)
        if bad_files:
            keep = False
            reason = f"unauthorized_file_changes:{', '.join(bad_files)}"

        if keep:
            promotion = maybe_promote_and_reseed(root)
            final_metrics, _ = evaluate_candidate_patch(root)
            final_keep, final_reason = keep_candidate(final_metrics, baseline_metrics)
            if not final_keep:
                previous_feedback = f"Promotion changed the final state without objective improvement: {final_reason}"
                restore_snapshot(baseline_snapshot, root=root)
                append_history(
                    prompt_summary_text=prompt_summary_text,
                    changed_claim_id=claim_id,
                    changed_theorem_name=theorem_name,
                    before_metrics=baseline_metrics,
                    after_metrics=final_metrics,
                    status="discarded",
                    commit_hash=None,
                    agent_message=agent_result.last_message or previous_feedback,
                    attempt_number=attempt_number,
                    root=root,
                )
                continue
            commit_hash = git_commit(
                f"codex: keep iteration for {claim_id or 'unknown-claim'}",
                root=root,
            )
            append_history(
                prompt_summary_text=prompt_summary_text,
                changed_claim_id=claim_id,
                changed_theorem_name=theorem_name,
                before_metrics=baseline_metrics,
                after_metrics=final_metrics,
                status="kept",
                commit_hash=commit_hash,
                agent_message=agent_result.last_message,
                attempt_number=attempt_number,
                root=root,
            )
            return {
                "status": "kept",
                "commit": commit_hash,
                "reason": final_reason,
                "promotion": promotion,
                "agent_message": agent_result.last_message,
            }

        previous_feedback = format_feedback(reason, outputs, changed_files)
        restore_snapshot(baseline_snapshot, root=root)
        append_history(
            prompt_summary_text=prompt_summary_text,
            changed_claim_id=claim_id,
            changed_theorem_name=theorem_name,
            before_metrics=baseline_metrics,
            after_metrics=trial_metrics,
            status="discarded",
            commit_hash=None,
            agent_message=agent_result.last_message or previous_feedback,
            attempt_number=attempt_number,
            root=root,
        )

    final_metrics, _ = evaluate_candidate_patch(root)
    return {"status": "discarded", "reason": "max_attempts_exhausted", "score": final_metrics["score"]}


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
