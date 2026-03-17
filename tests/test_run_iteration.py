from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.claim_templates import active_template_for_claim
from scripts.run_iteration import AgentRunResult, history_path, prepare_frontier, replay_history_entry, run_iteration


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def git(cmd: list[str], cwd: Path) -> str:
    process = subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return process.stdout.strip()


def metric(score_sorries: int, *, promoted: int = 0) -> dict:
    return {
        "build_ok": True,
        "stable_file_sorry_free": True,
        "num_promoted_lemmas": promoted,
        "num_story_done": 0,
        "num_active_claims_surviving_small_n": 1,
        "num_total_sorries": score_sorries,
        "num_blocked_claims": 0,
        "eval_runtime_sec": 1.0,
        "score": [1, 1, promoted, 0, 1, -score_sorries, 0, -1.0],
    }


def write_metrics(root: Path, metrics: dict) -> None:
    write(root / "state" / "metrics.json", json.dumps(metrics, indent=2) + "\n")
    write(root / "state" / "current_report.md", "# Report\n")


def claim_row(claim_id: str, *, status: str, lean_name: str, lean_status: str, falsifier_status: str = "survives_small_n") -> dict:
    return {
        "claim_id": claim_id,
        "title": claim_id,
        "status": status,
        "source": {"paper_id": "seed", "section": "Tests", "page_hint": "1"},
        "claim_type": "theorem",
        "priority": 4,
        "difficulty": 1,
        "small_check": True,
        "depends_on": [],
        "nl_statement": claim_id,
        "lean_name": lean_name,
        "lean_status": lean_status,
        "falsifier_status": falsifier_status,
        "notes": "seed",
    }


def seed_repo(root: Path, *, active_claim_id: str) -> None:
    write(root / ".gitignore", "state/history.jsonl\nstate/llm_last_message.md\n")
    write(root / "problem.md", "# Problem\n")
    write(root / "program.md", "# Program\n")
    write(root / "README.md", "baseline\n")
    write(root / "Formal" / "Defs.lean", "namespace Formal\n\nend Formal\n")
    write(root / "Formal" / "Known.lean", "namespace Formal\n\nend Formal\n")
    write(root / "Formal" / "GeneratedLemmas.lean", "import Formal.Known\n\nnamespace Formal\n\nend Formal\n")
    write(root / "Formal" / "Conjectures.lean", "import Formal.GeneratedLemmas\n\nnamespace Formal\n\nend Formal\n")
    write(root / "Formal" / "Active.lean", active_template_for_claim(active_claim_id))

    claims = [
        claim_row(
            "DTREE_ERR_001",
            status="active" if active_claim_id == "DTREE_ERR_001" else "candidate",
            lean_name="active_uniformError_self_zero",
            lean_status="statement_compiles" if active_claim_id == "DTREE_ERR_001" else "not_started",
        ),
        claim_row(
            "DTREE_ERR_002",
            status="active" if active_claim_id == "DTREE_ERR_002" else "candidate",
            lean_name="uniformError_symm",
            lean_status="statement_compiles" if active_claim_id == "DTREE_ERR_002" else "not_started",
        ),
        claim_row(
            "DTREE_INF_003",
            status="active" if active_claim_id == "DTREE_INF_003" else "candidate",
            lean_name="influence_unused_variable_zero",
            lean_status="statement_compiles" if active_claim_id == "DTREE_INF_003" else "not_started",
            falsifier_status="unknown",
        ),
    ]
    write(root / "claims" / "claims.jsonl", "\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
    write(root / "claims" / "candidates.jsonl", "\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
    progress_claims = [
        {
            "claim_id": row["claim_id"],
            "status": row["status"],
            "lean_status": row["lean_status"],
            "falsifier_status": row["falsifier_status"],
        }
        for row in claims
    ]
    write(
        root / "state" / "progress.json",
        json.dumps(
            {
                "project_id": "test",
                "problem_focus": "test",
                "active_story_id": "ST-07" if active_claim_id == "DTREE_INF_003" else "ST-06",
                "active_claim_id": active_claim_id,
                "stories": [],
                "claims": progress_claims,
                "latest_kept_commit": None,
                "baseline_metrics_file": "state/metrics.json",
            },
            indent=2,
        )
        + "\n",
    )
    write_metrics(root, metric(1))

    git(["git", "init"], root)
    git(["git", "config", "user.email", "test@example.com"], root)
    git(["git", "config", "user.name", "Test User"], root)
    git(["git", "add", "."], root)
    git(["git", "commit", "-m", "baseline"], root)


def prove_self_zero(text: str) -> str:
    return text.replace(
        "  sorry\n",
        "  simpa [uniformError] using (uniformErrorFn_self (f := eval t))\n",
    )


def fake_eval_factory(root: Path):
    def fake_eval(_root: Path = root) -> tuple[dict, dict[str, str]]:
        active_text = (root / "Formal" / "Active.lean").read_text()
        generated_text = (root / "Formal" / "GeneratedLemmas.lean").read_text()
        promoted = len(re.findall(r"(?m)^\s*theorem\s+", generated_text))
        sorries = len(re.findall(r"\bsorry\b", active_text))
        metrics = metric(sorries, promoted=promoted)
        write_metrics(root, metrics)
        return metrics, {
            "build_stdout": "",
            "build_stderr": "",
            "falsifier_stdout": "",
            "falsifier_stderr": "",
            "eval_stdout": "",
            "eval_stderr": "",
        }

    return fake_eval


class RunIterationAtomicTests(unittest.TestCase):
    def test_kept_run_records_latest_kept_commit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_ERR_001")
            baseline_active = (root / "Formal" / "Active.lean").read_text()

            def fake_codex(_prompt: str) -> AgentRunResult:
                write(root / "Formal" / "Active.lean", prove_self_zero(baseline_active))
                return AgentRunResult(returncode=0, stdout="", stderr="", last_message="proved the wrapper")

            with patch.dict(os.environ, {"AUTORESEARCH_DISABLE_CANARY": "1"}):
                with patch(
                    "scripts.run_iteration.evaluate_candidate_patch",
                    side_effect=[
                        (metric(1, promoted=0), {}),
                        (metric(0, promoted=0), {"build_stdout": "", "build_stderr": "", "falsifier_stdout": "", "falsifier_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                    ],
                ), patch(
                    "scripts.run_iteration.evaluate_post_keep_state",
                    return_value=(metric(1, promoted=1), {"build_stdout": "", "build_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                ), patch(
                    "scripts.run_iteration.run_post_keep_invariants",
                    return_value=(True, "ok"),
                ):
                    result = run_iteration(root=root, codex_runner=fake_codex, max_attempts=1)

            self.assertEqual(result["status"], "kept")
            progress = json.loads((root / "state" / "progress.json").read_text())
            self.assertEqual(progress["latest_kept_commit"], result["commit"])
            self.assertIn("progress_commit", result)
            self.assertNotEqual(result["commit"], result["progress_commit"])
            self.assertEqual(git(["git", "status", "--short"], root), "")

    def test_promotion_failure_triggers_full_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_ERR_001")
            baseline_active = (root / "Formal" / "Active.lean").read_text()

            def fake_codex(_prompt: str) -> AgentRunResult:
                write(root / "Formal" / "Active.lean", prove_self_zero(baseline_active))
                return AgentRunResult(returncode=0, stdout="", stderr="", last_message="proved the wrapper")

            with patch.dict(os.environ, {"AUTORESEARCH_DISABLE_CANARY": "1"}):
                with patch(
                    "scripts.run_iteration.evaluate_candidate_patch",
                    side_effect=[
                        (metric(1, promoted=0), {}),
                        (metric(0, promoted=0), {"build_stdout": "", "build_stderr": "", "falsifier_stdout": "", "falsifier_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                    ],
                ), patch(
                    "scripts.run_iteration.promote_active_theorem",
                    side_effect=ValueError("promotion exploded"),
                ):
                    result = run_iteration(root=root, codex_runner=fake_codex, max_attempts=1)

            self.assertEqual(result["status"], "discarded")
            self.assertEqual((root / "Formal" / "Active.lean").read_text(), baseline_active)
            self.assertEqual(git(["git", "status", "--short"], root), "")
            entry = json.loads(history_path(root).read_text().splitlines()[-1])
            self.assertEqual(entry["failure_stage"], "promotion")
            self.assertEqual(entry["status"], "discarded")

    def test_commit_failure_triggers_full_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_ERR_001")
            baseline_active = (root / "Formal" / "Active.lean").read_text()

            def fake_codex(_prompt: str) -> AgentRunResult:
                write(root / "Formal" / "Active.lean", prove_self_zero(baseline_active))
                return AgentRunResult(returncode=0, stdout="", stderr="", last_message="proved the wrapper")

            with patch.dict(os.environ, {"AUTORESEARCH_DISABLE_CANARY": "1"}):
                with patch(
                    "scripts.run_iteration.evaluate_candidate_patch",
                    side_effect=[
                        (metric(1, promoted=0), {}),
                        (metric(0, promoted=0), {"build_stdout": "", "build_stderr": "", "falsifier_stdout": "", "falsifier_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                    ],
                ), patch(
                    "scripts.run_iteration.evaluate_post_keep_state",
                    return_value=(metric(1, promoted=1), {"build_stdout": "", "build_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                ), patch(
                    "scripts.run_iteration.run_post_keep_invariants",
                    return_value=(True, "ok"),
                ), patch(
                    "scripts.run_iteration.git_commit",
                    side_effect=RuntimeError("commit exploded"),
                ):
                    result = run_iteration(root=root, codex_runner=fake_codex, max_attempts=1)

            self.assertEqual(result["status"], "discarded")
            self.assertEqual((root / "Formal" / "Active.lean").read_text(), baseline_active)
            self.assertEqual(git(["git", "status", "--short"], root), "")
            entry = json.loads(history_path(root).read_text().splitlines()[-1])
            self.assertEqual(entry["failure_stage"], "commit")
            self.assertEqual(entry["status"], "discarded")

    def test_replay_harness_reproduces_known_failing_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_ERR_001")
            baseline_state = {
                "Formal/Active.lean": (root / "Formal" / "Active.lean").read_text(),
                "claims/claims.jsonl": (root / "claims" / "claims.jsonl").read_text(),
                "claims/candidates.jsonl": (root / "claims" / "candidates.jsonl").read_text(),
                "state/progress.json": (root / "state" / "progress.json").read_text(),
                "state/metrics.json": (root / "state" / "metrics.json").read_text(),
                "state/current_report.md": (root / "state" / "current_report.md").read_text(),
            }
            candidate_active_text = prove_self_zero(baseline_state["Formal/Active.lean"])
            entry = {
                "iteration_id": "replay-target",
                "attempt_number": 1,
                "prompt_summary": "replay",
                "changed_claim_ids": ["DTREE_ERR_001", "DTREE_ERR_002"],
                "changed_theorem_names": ["active_uniformError_self_zero", "active_uniformError_symm"],
                "score_before": metric(1, promoted=0)["score"],
                "score_after": metric(1, promoted=1)["score"],
                "status": "discarded",
                "commit_hash": None,
                "keep_reason": "commit exploded",
                "failure_stage": "commit",
                "failure_invariant": "git_commit_failed",
                "agent_message": "replay candidate",
                "base_commit": git(["git", "rev-parse", "HEAD"], root),
                "baseline_state": baseline_state,
                "candidate_active_text": candidate_active_text,
                "frontier_before": {"active_claim_id": "DTREE_ERR_001", "theorem_name": "active_uniformError_self_zero"},
                "frontier_after": {"active_claim_id": "DTREE_ERR_001", "theorem_name": "active_uniformError_self_zero"},
                "agent_changed_files": ["Formal/Active.lean"],
                "promotion": None,
                "canary_mode": False,
            }
            write(history_path(root), json.dumps(entry) + "\n")

            with patch.dict(os.environ, {"AUTORESEARCH_DISABLE_CANARY": "1"}):
                with patch("scripts.run_iteration.evaluate_candidate_patch", side_effect=[(metric(1, promoted=0), {}), (metric(0, promoted=0), {})]), patch(
                    "scripts.run_iteration.evaluate_post_keep_state",
                    return_value=(metric(1, promoted=1), {"build_stdout": "", "build_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                ), patch(
                    "scripts.run_iteration.run_post_keep_invariants",
                    return_value=(True, "ok"),
                ), patch(
                    "scripts.run_iteration.git_commit",
                    side_effect=RuntimeError("commit exploded"),
                ):
                    replay = replay_history_entry(root=root, iteration_id="replay-target")

            self.assertEqual(replay["expected_failure_stage"], replay["replayed_failure_stage"])
            self.assertEqual(replay["expected_failure_invariant"], replay["replayed_failure_invariant"])
            self.assertEqual(replay["expected_status"], replay["replayed_status"])

    def test_canary_mode_produces_clean_kept_commits_and_unlocks_frontier(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_INF_003")

            def fake_codex(_prompt: str) -> AgentRunResult:
                text = (root / "Formal" / "Active.lean").read_text()
                write(root / "Formal" / "Active.lean", prove_self_zero(text))
                return AgentRunResult(returncode=0, stdout="", stderr="", last_message="proved canary shell")

            fake_eval = fake_eval_factory(root)

            with patch("scripts.run_iteration.evaluate_candidate_patch", side_effect=fake_eval), patch(
                "scripts.run_iteration.evaluate_post_keep_state",
                side_effect=fake_eval,
            ), patch(
                "scripts.run_iteration.run_post_keep_invariants",
                return_value=(True, "ok"),
            ):
                results = [run_iteration(root=root, codex_runner=fake_codex, max_attempts=1) for _ in range(3)]

            self.assertTrue(all(result["status"] == "kept" for result in results))
            self.assertTrue(all(result["canary_mode"] for result in results))
            self.assertEqual(git(["git", "status", "--short"], root), "")
            progress = json.loads((root / "state" / "progress.json").read_text())
            self.assertEqual(progress["active_claim_id"], "DTREE_INF_003")
            active_text = (root / "Formal" / "Active.lean").read_text()
            self.assertIn("claim_id: DTREE_INF_003", active_text)
            generated = (root / "Formal" / "GeneratedLemmas.lean").read_text()
            self.assertIn("canary_uniformError_self_zero_001", generated)
            self.assertIn("canary_uniformError_self_zero_002", generated)
            self.assertIn("canary_uniformError_self_zero_003", generated)

    def test_prepare_frontier_reactivates_real_frontier_after_canary_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            seed_repo(root, active_claim_id="DTREE_INF_003")
            for i in range(1, 4):
                git(["git", "commit", "--allow-empty", "-m", f"canary-{i}"], root)
                entry = {
                    "iteration_id": f"canary-{i}",
                    "status": "kept",
                    "canary_mode": True,
                    "commit_hash": git(["git", "rev-parse", "HEAD"], root),
                }
                write(history_path(root), ((history_path(root).read_text() if history_path(root).exists() else "") + json.dumps(entry) + "\n"))

            write(root / "Formal" / "Active.lean", active_template_for_claim("CANARY_KEEP_006"))
            claims = [json.loads(line) for line in (root / "claims" / "claims.jsonl").read_text().splitlines() if line.strip()]
            claims.append(claim_row("CANARY_KEEP_006", status="active", lean_name="canary_uniformError_self_zero_006", lean_status="statement_compiles"))
            write(root / "claims" / "claims.jsonl", "\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
            write(root / "claims" / "candidates.jsonl", "\n".join(json.dumps(row, sort_keys=True) for row in claims) + "\n")
            progress = json.loads((root / "state" / "progress.json").read_text())
            progress["active_claim_id"] = "CANARY_KEEP_006"
            progress["active_story_id"] = "ST-11"
            progress["claims"].append(
                {
                    "claim_id": "CANARY_KEEP_006",
                    "status": "active",
                    "lean_status": "statement_compiles",
                    "falsifier_status": "unknown",
                }
            )
            write(root / "state" / "progress.json", json.dumps(progress, indent=2) + "\n")

            frontier = prepare_frontier(root=root)

            self.assertFalse(frontier["canary_mode"])
            self.assertEqual(frontier["active_claim_id"], "DTREE_INF_003")
            repaired_progress = json.loads((root / "state" / "progress.json").read_text())
            self.assertEqual(repaired_progress["active_claim_id"], "DTREE_INF_003")
            self.assertIn("claim_id: DTREE_INF_003", (root / "Formal" / "Active.lean").read_text())


if __name__ == "__main__":
    unittest.main()
