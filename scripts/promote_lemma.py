from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import ROOT as PROJECT_ROOT

ACTIVE = PROJECT_ROOT / "Formal" / "Active.lean"
KNOWN = PROJECT_ROOT / "Formal" / "Known.lean"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--theorem-name", required=True)
    args = parser.parse_args()

    active_text = ACTIVE.read_text()
    if "sorry" in active_text:
        print("Active theorem still contains sorry; refusing to promote.")
        return 1

    pattern = re.compile(
        rf"(theorem\s+{re.escape(args.theorem_name)}[\s\S]+?:= by[\s\S]+?)(?:\n\nend Formal)",
        re.MULTILINE,
    )
    match = pattern.search(active_text)
    if match is None:
        print(f"Could not find theorem {args.theorem_name} in Active.lean.")
        return 1

    known_text = KNOWN.read_text()
    if args.theorem_name in known_text:
        print(f"{args.theorem_name} already exists in Known.lean.")
        return 1

    updated = known_text.replace("\nend Formal\n", f"\n\n{match.group(1).strip()}\n\nend Formal\n")
    KNOWN.write_text(updated)
    print(f"Promoted {args.theorem_name} to Known.lean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
