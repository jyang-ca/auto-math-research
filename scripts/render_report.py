from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import STATE_DIR
from scripts.score_iteration import score_tuple


def render(metrics: dict) -> str:
    score = score_tuple(metrics)
    return "\n".join(
        [
            "# Current Report",
            "",
            f"- build_ok: `{metrics['build_ok']}`",
            f"- stable_file_sorry_free: `{metrics['stable_file_sorry_free']}`",
            f"- num_promoted_lemmas: `{metrics['num_promoted_lemmas']}`",
            f"- num_story_done: `{metrics['num_story_done']}`",
            f"- num_active_claims_surviving_small_n: `{metrics['num_active_claims_surviving_small_n']}`",
            f"- num_total_sorries: `{metrics['num_total_sorries']}`",
            f"- num_blocked_claims: `{metrics['num_blocked_claims']}`",
            f"- eval_runtime_sec: `{metrics['eval_runtime_sec']}`",
            f"- score: `{score}`",
            "",
            "## Notes",
            "",
            f"- theorem_sanity_ok: `{metrics['theorem_sanity_ok']}`",
            f"- active_claim_result: `{metrics['active_claim_result']}`",
        ]
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--metrics", default=str(STATE_DIR / "metrics.json"))
    parser.add_argument("--output", default=str(STATE_DIR / "current_report.md"))
    args = parser.parse_args()

    metrics = json.loads(Path(args.metrics).read_text())
    Path(args.output).write_text(render(metrics))
    print(Path(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
