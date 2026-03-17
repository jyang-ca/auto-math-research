import Formal.Conjectures

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
