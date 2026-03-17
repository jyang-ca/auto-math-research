import Formal.Known

namespace Formal

-- Auto-promoted lemmas are appended here by scripts/promote_lemma.py.


/-- Auto-promoted from claim DTREE_ERR_001. -/
theorem active_uniformError_self_zero (t : DTree n) :
    uniformError t t = 0 := by
  simpa [uniformError] using (uniformErrorFn_self (f := eval t))

end Formal
