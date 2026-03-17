from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import ROOT as PROJECT_ROOT, read_json, write_json


def main() -> int:
    manifest = read_json(PROJECT_ROOT / "papers" / "manifest.json")
    parsed = []
    for paper in manifest["papers"]:
        parsed.append(
            {
                "paper_id": paper["paper_id"],
                "title": paper["title"],
                "authors": paper["authors"],
                "abstract": paper["abstract"],
                "sections": ["Abstract", "Definitions", "Milestones", "Barriers"],
                "theorem_like_sentences": [],
            }
        )
    write_json(PROJECT_ROOT / "papers" / "parsed" / "parsed_manifest.json", {"papers": parsed})
    print(json.dumps({"parsed_count": len(parsed)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
