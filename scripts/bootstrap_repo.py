from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_PATHS = [
    ROOT / "Formal" / "Defs.lean",
    ROOT / "Formal" / "Known.lean",
    ROOT / "Formal" / "Conjectures.lean",
    ROOT / "Formal" / "Active.lean",
    ROOT / "scripts" / "run_iteration.py",
    ROOT / "state" / "progress.json",
    ROOT / "claims" / "candidates.jsonl",
    ROOT / "bench" / "falsifier_config.json",
]


def main() -> int:
    missing = [str(path.relative_to(ROOT)) for path in REQUIRED_PATHS if not path.exists()]
    payload = {"root": str(ROOT), "missing": missing, "ok": not missing}
    print(json.dumps(payload, indent=2))
    return 0 if not missing else 1


if __name__ == "__main__":
    sys.exit(main())
