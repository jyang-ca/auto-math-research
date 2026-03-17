from __future__ import annotations

from pathlib import Path


CANARY_PREFIX = "CANARY_KEEP_"
CANARY_STORY_ID = "ST-11"


PLACEHOLDER_ACTIVE = """import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: NONE
story_id: ST-11
objective: statement_only
task: idle
theorem_name: none
allow_sorry: false
-/

-- No active theorem is currently seeded. Promotion completed successfully,
-- but the next claim still needs a Lean theorem shell.

end Formal
"""


CLAIM_TEMPLATES = {
    "DTREE_ERR_001": """import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: DTREE_ERR_001
story_id: ST-06
objective: prove_theorem
task: theorem_proof
theorem_name: active_uniformError_self_zero
allow_sorry: true
-/

theorem active_uniformError_self_zero (t : DTree n) :
    uniformError t t = 0 := by
  sorry

end Formal
""",
    "DTREE_ERR_002": """import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: DTREE_ERR_002
story_id: ST-06
objective: prove_theorem
task: theorem_proof
theorem_name: active_uniformError_symm
allow_sorry: true
-/

theorem active_uniformError_symm (t u : DTree n) :
    uniformError t u = uniformError u t := by
  sorry

end Formal
""",
    "DTREE_INF_003": """import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: DTREE_INF_003
story_id: ST-07
objective: prove_theorem
task: theorem_proof
theorem_name: influence_unused_variable_zero
allow_sorry: true
-/

theorem influence_unused_variable_zero (t : DTree n) {i : Var n}
    (h : i ∉ varsUsed t) :
    influence (eval t) i = 0 := by
  sorry

end Formal
""",
    "DTREE_VARS_001": """import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: DTREE_VARS_001
story_id: ST-11
objective: prove_theorem
task: theorem_proof
theorem_name: restrictTree_varsUsed_subset
allow_sorry: true
-/

theorem restrictTree_varsUsed_subset (ρ : Restriction n) (t : DTree n) :
    varsUsed (restrictTree ρ t) ⊆ varsUsed t := by
  sorry

end Formal
""",
}


def is_canary_claim_id(claim_id: str | None) -> bool:
    return claim_id is not None and claim_id.startswith(CANARY_PREFIX)


def canary_claim_index(claim_id: str) -> int:
    if not is_canary_claim_id(claim_id):
        raise ValueError(f"{claim_id} is not a canary claim id.")
    return int(claim_id.removeprefix(CANARY_PREFIX))


def canary_claim_id(index: int) -> str:
    return f"{CANARY_PREFIX}{index:03d}"


def canary_theorem_name(index: int) -> str:
    return f"canary_uniformError_self_zero_{index:03d}"


def canary_claim_row(index: int, *, status: str = "candidate", lean_status: str = "not_started") -> dict:
    claim_id = canary_claim_id(index)
    theorem_name = canary_theorem_name(index)
    return {
        "claim_id": claim_id,
        "title": f"Canary uniform-error self test #{index}",
        "status": status,
        "source": {
            "paper_id": "canary_mode",
            "section": "Loop verification",
            "page_hint": f"synthetic-{index}",
        },
        "claim_type": "lemma",
        "priority": 5,
        "difficulty": 1,
        "small_check": True,
        "depends_on": ["DEF_UNIFORM_ERROR"],
        "nl_statement": "A trivial wrapper around uniform-error reflexivity used to verify the keep/promotion/commit path.",
        "lean_name": theorem_name,
        "lean_status": lean_status,
        "falsifier_status": "survives_small_n",
        "notes": "Synthetic canary claim for the atomic iteration harness.",
    }


def canary_template(index: int) -> str:
    claim_id = canary_claim_id(index)
    theorem_name = canary_theorem_name(index)
    return f"""import Formal.Conjectures

namespace Formal

/- ACTIVE_METADATA
claim_id: {claim_id}
story_id: {CANARY_STORY_ID}
objective: prove_theorem
task: theorem_proof
theorem_name: {theorem_name}
allow_sorry: true
-/

theorem {theorem_name} (t : DTree n) :
    uniformError t t = 0 := by
  sorry

end Formal
"""


def infer_story_id(claim_id: str | None) -> str:
    if claim_id is None:
        return "ST-11"
    if is_canary_claim_id(claim_id):
        return CANARY_STORY_ID
    if "_ERR_" in claim_id:
        return "ST-06"
    if "_INF_" in claim_id:
        return "ST-07"
    if "_MONO_" in claim_id or "_RES_" in claim_id:
        return "ST-05"
    return "ST-11"


def active_template_for_claim(claim_id: str | None) -> str:
    if claim_id is None:
        return PLACEHOLDER_ACTIVE
    if is_canary_claim_id(claim_id):
        return canary_template(canary_claim_index(claim_id))
    return CLAIM_TEMPLATES.get(claim_id, PLACEHOLDER_ACTIVE)


def active_file_path(root: Path) -> Path:
    return root / "Formal" / "Active.lean"
