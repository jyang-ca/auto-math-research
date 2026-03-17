from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def score_tuple(metrics: dict) -> tuple:
    return (
        int(bool(metrics["build_ok"])),
        int(bool(metrics["stable_file_sorry_free"])),
        int(metrics["num_promoted_lemmas"]),
        int(metrics["num_story_done"]),
        int(metrics["num_active_claims_surviving_small_n"]),
        -int(metrics["num_total_sorries"]),
        -int(metrics["num_blocked_claims"]),
        -float(metrics["eval_runtime_sec"]),
    )


def better(trial: dict, baseline: dict) -> bool:
    return score_tuple(trial) > score_tuple(baseline)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("baseline")
    parser.add_argument("trial")
    args = parser.parse_args()

    baseline = json.loads(Path(args.baseline).read_text())
    trial = json.loads(Path(args.trial).read_text())
    payload = {
        "baseline_score": score_tuple(baseline),
        "trial_score": score_tuple(trial),
        "better": better(trial, baseline),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
