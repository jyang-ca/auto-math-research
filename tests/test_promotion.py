from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.claim_templates import active_template_for_claim
from scripts.promote_lemma import promote_active_theorem


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


class PromotionTests(unittest.TestCase):
    def test_promote_active_theorem_moves_theorem_and_reseeds_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            write(root / "Formal" / "GeneratedLemmas.lean", "import Formal.Known\n\nnamespace Formal\n\nend Formal\n")
            write(
                root / "Formal" / "Active.lean",
                active_template_for_claim("DTREE_ERR_001").replace(
                    "  sorry\n",
                    "  simpa [uniformError] using (uniformErrorFn_self (f := eval t))\n",
                ),
            )
            claim_rows = [
                {
                    "claim_id": "DTREE_ERR_001",
                    "title": "Uniform error of identical trees is zero",
                    "status": "active",
                    "source": {"paper_id": "seed", "section": "Defs", "page_hint": "2"},
                    "claim_type": "theorem",
                    "priority": 5,
                    "difficulty": 1,
                    "small_check": True,
                    "depends_on": ["DEF_UNIFORM_ERROR"],
                    "nl_statement": "A decision tree has zero uniform error against itself.",
                    "lean_name": "active_uniformError_self_zero",
                    "lean_status": "statement_compiles",
                    "falsifier_status": "survives_small_n",
                    "notes": "seed",
                },
                {
                    "claim_id": "DTREE_ERR_002",
                    "title": "Uniform error is symmetric",
                    "status": "candidate",
                    "source": {"paper_id": "seed", "section": "Defs", "page_hint": "2"},
                    "claim_type": "theorem",
                    "priority": 4,
                    "difficulty": 1,
                    "small_check": True,
                    "depends_on": ["DEF_UNIFORM_ERROR"],
                    "nl_statement": "Uniform disagreement is symmetric.",
                    "lean_name": "uniformError_symm",
                    "lean_status": "not_started",
                    "falsifier_status": "unknown",
                    "notes": "seed",
                },
            ]
            write(
                root / "claims" / "claims.jsonl",
                "\n".join(json.dumps(row, sort_keys=True) for row in claim_rows) + "\n",
            )
            write(
                root / "claims" / "candidates.jsonl",
                "\n".join(json.dumps(row, sort_keys=True) for row in claim_rows) + "\n",
            )
            write(
                root / "state" / "progress.json",
                json.dumps(
                    {
                        "project_id": "test",
                        "problem_focus": "test",
                        "active_story_id": "ST-06",
                        "active_claim_id": "DTREE_ERR_001",
                        "stories": [
                            {"story_id": "ST-06", "title": "Uniform error", "status": "active", "acceptance": [], "evidence": []}
                        ],
                        "claims": [
                            {
                                "claim_id": "DTREE_ERR_001",
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

            result = promote_active_theorem(root=root)

            self.assertEqual(result.promoted_claim_id, "DTREE_ERR_001")
            self.assertEqual(result.next_claim_id, "DTREE_ERR_002")
            generated = (root / "Formal" / "GeneratedLemmas.lean").read_text()
            self.assertIn("active_uniformError_self_zero", generated)
            active_text = (root / "Formal" / "Active.lean").read_text()
            self.assertIn("claim_id: DTREE_ERR_002", active_text)
            self.assertIn("theorem active_uniformError_symm", active_text)
            claims = read_jsonl(root / "claims" / "claims.jsonl")
            self.assertEqual(claims[0]["status"], "proved")
            self.assertEqual(claims[1]["status"], "active")
            progress = json.loads((root / "state" / "progress.json").read_text())
            self.assertEqual(progress["active_claim_id"], "DTREE_ERR_002")


if __name__ == "__main__":
    unittest.main()
