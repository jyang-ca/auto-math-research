from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import CLAIMS_DIR, load_jsonl


def main() -> int:
    claims = load_jsonl(CLAIMS_DIR / "claims.jsonl")
    payload = {
        "claim_count": len(claims),
        "candidate_count": sum(1 for claim in claims if claim["status"] in {"candidate", "active"}),
    }
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
