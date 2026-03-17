import Formal.Conjectures

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
