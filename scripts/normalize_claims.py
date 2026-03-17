from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import CLAIMS_DIR, load_jsonl

REQUIRED_KEYS = {
    "claim_id",
    "title",
    "status",
    "source",
    "claim_type",
    "priority",
    "difficulty",
    "small_check",
    "depends_on",
    "nl_statement",
    "lean_name",
    "lean_status",
    "falsifier_status",
    "notes",
}


def main() -> int:
    claims = load_jsonl(CLAIMS_DIR / "claims.jsonl")
    invalid = [claim["claim_id"] for claim in claims if set(claim.keys()) != REQUIRED_KEYS]
    print(json.dumps({"claims": len(claims), "invalid": invalid}, indent=2))
    return 0 if not invalid else 1


if __name__ == "__main__":
    sys.exit(main())
