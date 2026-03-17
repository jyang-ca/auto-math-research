from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_iteration import replay_history_entry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration-id")
    parser.add_argument("--index", type=int)
    args = parser.parse_args()

    try:
        payload = replay_history_entry(iteration_id=args.iteration_id, index=args.index)
    except RuntimeError as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}, indent=2))
        return 1

    matches = (
        payload["expected_failure_stage"] == payload["replayed_failure_stage"]
        and payload["expected_failure_invariant"] == payload["replayed_failure_invariant"]
        and payload["expected_status"] == payload["replayed_status"]
    )
    return 0 if matches else 1


if __name__ == "__main__":
    sys.exit(main())
