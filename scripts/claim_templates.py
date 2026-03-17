from __future__ import annotations

from pathlib import Path


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


def infer_story_id(claim_id: str | None) -> str:
    if claim_id is None:
        return "ST-11"
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
    return CLAIM_TEMPLATES.get(claim_id, PLACEHOLDER_ACTIVE)


def active_file_path(root: Path) -> Path:
    return root / "Formal" / "Active.lean"
