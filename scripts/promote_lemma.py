from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.claim_templates import active_template_for_claim, infer_story_id
from scripts.common import CLAIMS_DIR, ROOT as PROJECT_ROOT, STATE_DIR, load_jsonl, write_jsonl, write_text

ACTIVE = PROJECT_ROOT / "Formal" / "Active.lean"
GENERATED = PROJECT_ROOT / "Formal" / "GeneratedLemmas.lean"


@dataclass
class PromotionResult:
    promoted_claim_id: str
    theorem_name: str
    next_claim_id: str | None
    next_story_id: str | None
    updated_files: list[str]


def parse_active_metadata(text: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for key, value in re.findall(r"(?m)^([A-Za-z0-9_]+):\s*(.+)$", text):
        metadata[key] = value.strip()
    return metadata


def extract_theorem_block(text: str, theorem_name: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\s*(theorem|lemma)\s+{re.escape(theorem_name)}\b.*?(?=^end Formal\s*$)"
    )
    match = pattern.search(text)
    if match is None:
        raise ValueError(f"Could not find theorem block for {theorem_name}.")
    return match.group(0).strip()


def theorem_already_promoted(generated_text: str, theorem_name: str) -> bool:
    return re.search(rf"(?m)^\s*(theorem|lemma)\s+{re.escape(theorem_name)}\b", generated_text) is not None


def theorem_declared(root: Path, theorem_name: str) -> bool:
    theorem_pattern = rf"(?m)^\s*(theorem|lemma)\s+{re.escape(theorem_name)}\b"
    for relative in ("Formal/Known.lean", "Formal/GeneratedLemmas.lean"):
        path = root / relative
        if path.exists() and re.search(theorem_pattern, path.read_text()):
            return True
    return False


def choose_next_claim(current_claim_id: str, claims_rows: list[dict], *, root: Path) -> str | None:
    for claim in claims_rows:
        if claim["claim_id"] == current_claim_id:
            continue
        if claim["status"] not in {"candidate", "active"}:
            continue
        if claim.get("lean_status") == "proved":
            continue
        if claim.get("falsifier_status") == "falsified_small_n":
            continue
        if theorem_declared(root, claim["lean_name"]):
            continue
        return claim["claim_id"]
    return None


def update_claim_rows(claim_rows: list[dict], current_claim_id: str, next_claim_id: str | None) -> list[dict]:
    updated: list[dict] = []
    for row in claim_rows:
        row = dict(row)
        if row["claim_id"] == current_claim_id:
            row["status"] = "proved"
            row["lean_status"] = "proved"
            row["falsifier_status"] = row.get("falsifier_status", "survives_small_n")
        elif next_claim_id is not None and row["claim_id"] == next_claim_id:
            row["status"] = "active"
        updated.append(row)
    return updated


def update_progress(progress: dict, current_claim_id: str, next_claim_id: str | None) -> dict:
    progress = json.loads(json.dumps(progress))
    progress["active_claim_id"] = next_claim_id or current_claim_id
    progress["active_story_id"] = infer_story_id(next_claim_id)
    for claim in progress["claims"]:
        if claim["claim_id"] == current_claim_id:
            claim["status"] = "proved"
            claim["lean_status"] = "proved"
            claim["falsifier_status"] = "survives_small_n"
    if next_claim_id is not None and all(claim["claim_id"] != next_claim_id for claim in progress["claims"]):
        progress["claims"].append(
            {
                "claim_id": next_claim_id,
                "status": "active",
                "lean_status": "statement_compiles",
                "falsifier_status": "unknown",
            }
        )
    elif next_claim_id is not None:
        for claim in progress["claims"]:
            if claim["claim_id"] == next_claim_id:
                claim["status"] = "active"
    for story in progress["stories"]:
        if story["story_id"] == infer_story_id(next_claim_id) and story["status"] == "pending":
            story["status"] = "active"
    return progress


def append_to_generated(generated_path: Path, theorem_block: str, claim_id: str) -> None:
    generated_text = generated_path.read_text()
    theorem_name_match = re.search(r"(?m)^\s*(?:theorem|lemma)\s+([A-Za-z0-9_']+)\b", theorem_block)
    if theorem_name_match is None:
        raise ValueError("Could not parse theorem name from theorem block.")
    theorem_name = theorem_name_match.group(1)
    if theorem_already_promoted(generated_text, theorem_name):
        return
    insertion = f"\n\n/-- Auto-promoted from claim {claim_id}. -/\n{theorem_block}\n"
    generated_path.write_text(generated_text.replace("\nend Formal\n", f"{insertion}\nend Formal\n"))


def promote_active_theorem(
    *,
    root: Path = PROJECT_ROOT,
    claim_id: str | None = None,
    theorem_name: str | None = None,
) -> PromotionResult:
    active_path = root / "Formal" / "Active.lean"
    generated_path = root / "Formal" / "GeneratedLemmas.lean"
    claims_path = root / "claims" / "claims.jsonl"
    candidates_path = root / "claims" / "candidates.jsonl"
    progress_path = root / "state" / "progress.json"

    active_text = active_path.read_text()
    metadata = parse_active_metadata(active_text)
    promoted_claim_id = claim_id or metadata.get("claim_id")
    promoted_theorem_name = theorem_name or metadata.get("theorem_name")
    if not promoted_claim_id or not promoted_theorem_name:
        raise ValueError("Active metadata is missing claim_id or theorem_name.")
    theorem_block = extract_theorem_block(active_text, promoted_theorem_name)
    if re.search(r"\bsorry\b", theorem_block):
        raise ValueError("Active theorem still contains sorry; refusing to promote.")

    claim_rows = load_jsonl(claims_path)
    next_claim_id = choose_next_claim(promoted_claim_id, claim_rows, root=root)
    next_story_id = infer_story_id(next_claim_id)

    append_to_generated(generated_path, theorem_block, promoted_claim_id)
    write_text(active_path, active_template_for_claim(next_claim_id))

    updated_claim_rows = update_claim_rows(claim_rows, promoted_claim_id, next_claim_id)
    write_jsonl(claims_path, updated_claim_rows)
    write_jsonl(candidates_path, update_claim_rows(load_jsonl(candidates_path), promoted_claim_id, next_claim_id))

    progress = json.loads(progress_path.read_text())
    progress_path.write_text(json.dumps(update_progress(progress, promoted_claim_id, next_claim_id), indent=2) + "\n")

    return PromotionResult(
        promoted_claim_id=promoted_claim_id,
        theorem_name=promoted_theorem_name,
        next_claim_id=next_claim_id,
        next_story_id=next_story_id,
        updated_files=[
            str(active_path.relative_to(root)),
            str(generated_path.relative_to(root)),
            str(claims_path.relative_to(root)),
            str(candidates_path.relative_to(root)),
            str(progress_path.relative_to(root)),
        ],
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-id")
    parser.add_argument("--theorem-name")
    args = parser.parse_args()

    try:
        result = promote_active_theorem(claim_id=args.claim_id, theorem_name=args.theorem_name)
    except ValueError as exc:
        print(str(exc))
        return 1

    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
