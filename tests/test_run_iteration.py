from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.claim_templates import active_template_for_claim
from scripts.run_iteration import AgentRunResult, history_path, run_iteration


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def git(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)


def metric(score_sorries: int) -> dict:
    return {
        "build_ok": True,
        "stable_file_sorry_free": True,
        "num_promoted_lemmas": 0,
        "num_story_done": 0,
        "num_active_claims_surviving_small_n": 1,
        "num_total_sorries": score_sorries,
        "num_blocked_claims": 0,
        "eval_runtime_sec": 1.0,
        "score": [1, 1, 0, 0, 1, -score_sorries, 0, -1.0],
    }


class RunIterationRollbackTests(unittest.TestCase):
    def test_discarded_attempt_restores_active_and_unauthorized_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write(root / ".gitignore", "state/history.jsonl\nstate/llm_last_message.md\n")
            baseline_active = active_template_for_claim("DTREE_ERR_002")
            write(root / "Formal" / "Active.lean", baseline_active)
            write(root / "README.md", "baseline\n")
            write(root / "problem.md", "# Problem\n")
            write(root / "program.md", "# Program\n")
            write(
                root / "claims" / "claims.jsonl",
                json.dumps(
                    {
                        "claim_id": "DTREE_ERR_002",
                        "title": "Uniform error is symmetric",
                        "status": "active",
                        "source": {"paper_id": "seed", "section": "Defs", "page_hint": "2"},
                        "claim_type": "theorem",
                        "priority": 4,
                        "difficulty": 1,
                        "small_check": True,
                        "depends_on": ["DEF_UNIFORM_ERROR"],
                        "nl_statement": "Uniform disagreement is symmetric.",
                        "lean_name": "uniformError_symm",
                        "lean_status": "statement_compiles",
                        "falsifier_status": "survives_small_n",
                        "notes": "seed",
                    },
                    sort_keys=True,
                )
                + "\n",
            )
            write(root / "claims" / "candidates.jsonl", (root / "claims" / "claims.jsonl").read_text())
            write(
                root / "state" / "progress.json",
                json.dumps(
                    {
                        "project_id": "test",
                        "problem_focus": "test",
                        "active_story_id": "ST-06",
                        "active_claim_id": "DTREE_ERR_002",
                        "stories": [],
                        "claims": [
                            {
                                "claim_id": "DTREE_ERR_002",
                                "status": "active",
                                "lean_status": "statement_compiles",
                                "falsifier_status": "survives_small_n",
                            }
                        ],
                        "latest_kept_commit": None,
                        "baseline_metrics_file": "state/metrics.json",
                    },
                    indent=2,
                )
                + "\n",
            )
            write(root / "state" / "metrics.json", json.dumps(metric(1), indent=2) + "\n")
            write(root / "state" / "current_report.md", "# Report\n")

            git(["git", "init"], root)
            git(["git", "config", "user.email", "test@example.com"], root)
            git(["git", "config", "user.name", "Test User"], root)
            git(["git", "add", "."], root)
            git(["git", "commit", "-m", "baseline"], root)

            def fake_codex(_prompt: str) -> AgentRunResult:
                write(
                    root / "Formal" / "Active.lean",
                    baseline_active.replace("  sorry\n", "  simpa [uniformError] using (uniformErrorFn_symm (f := eval t) (g := eval u))\n"),
                )
                write(root / "README.md", "unauthorized\n")
                return AgentRunResult(returncode=0, stdout="", stderr="", last_message="Attempted a proof and touched another file.")

            baseline_metrics = metric(1)
            trial_metrics = metric(0)

            with patch(
                "scripts.run_iteration.evaluate_candidate_patch",
                side_effect=[
                    (baseline_metrics, {}),
                    (trial_metrics, {"build_stdout": "", "build_stderr": "", "falsifier_stdout": "", "falsifier_stderr": "", "eval_stdout": "", "eval_stderr": ""}),
                    (baseline_metrics, {}),
                ],
            ):
                result = run_iteration(root=root, codex_runner=fake_codex, max_attempts=1)

            self.assertEqual(result["status"], "discarded")
            self.assertEqual((root / "Formal" / "Active.lean").read_text(), baseline_active)
            self.assertEqual((root / "README.md").read_text(), "baseline\n")
            status = subprocess.run(
                ["git", "status", "--short"],
                cwd=root,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(status.stdout.strip(), "")
            history_lines = history_path(root).read_text().splitlines()
            self.assertEqual(len(history_lines), 1)
            self.assertEqual(json.loads(history_lines[0])["status"], "discarded")


if __name__ == "__main__":
    unittest.main()
