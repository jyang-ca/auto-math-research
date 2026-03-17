import Formal.Conjectures

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
  simpa [uniformError] using (uniformErrorFn_self (f := eval t))

end Formal
