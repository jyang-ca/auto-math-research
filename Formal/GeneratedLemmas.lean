import Formal.Known

namespace Formal

-- Auto-promoted lemmas are appended here by scripts/promote_lemma.py.


/-- Auto-promoted from claim DTREE_ERR_001. -/
theorem active_uniformError_self_zero (t : DTree n) :
    uniformError t t = 0 := by
  simpa [uniformError] using (uniformErrorFn_self (f := eval t))


/-- Auto-promoted from claim CANARY_KEEP_001. -/
theorem canary_uniformError_self_zero_001 (t : DTree n) :
    uniformError t t = 0 := by
  simpa [uniformError] using (uniformErrorFn_self (f := eval t))


/-- Auto-promoted from claim CANARY_KEEP_002. -/
theorem canary_uniformError_self_zero_002 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using active_uniformError_self_zero (t := t)


/-- Auto-promoted from claim CANARY_KEEP_003. -/
theorem canary_uniformError_self_zero_003 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using canary_uniformError_self_zero_002 (t := t)


/-- Auto-promoted from claim CANARY_KEEP_004. -/
theorem canary_uniformError_self_zero_004 (t : DTree n) :
    uniformError t t = 0 := by
  simpa [uniformError] using (uniformErrorFn_self (f := eval t))


/-- Auto-promoted from claim CANARY_KEEP_005. -/
theorem canary_uniformError_self_zero_005 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using canary_uniformError_self_zero_004 (t := t)


/-- Auto-promoted from claim CANARY_KEEP_006. -/
theorem canary_uniformError_self_zero_006 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using canary_uniformError_self_zero_005 (t := t)


/-- Auto-promoted from claim DTREE_INF_003. -/
theorem influence_unused_variable_zero (t : DTree n) {i : Var n}
    (h : i ∉ varsUsed t) :
    influence (eval t) i = 0 := by
  have hflip_eval :
      ∀ t : DTree n, i ∉ varsUsed t → ∀ a : Assignment n, eval t (flipBit a i) = eval t a := by
    intro t
    induction t with
    | leaf b =>
        intro _ a
        simp
    | node v left right ihLeft ihRight =>
        intro h a
        have hiv : i ≠ v := by
          intro hEq
          apply h
          simp [varsUsed, hEq]
        have hvi : v ≠ i := by
          intro hEq
          exact hiv hEq.symm
        have hleft : i ∉ varsUsed left := by
          intro hi
          apply h
          simp [varsUsed, hi]
        have hright : i ∉ varsUsed right := by
          intro hi
          apply h
          simp [varsUsed, hi]
        simp [flipBit_ne (a := a) (i := i) (j := v) hvi, ihLeft hleft a, ihRight hright a]
  unfold influence
  have hfun : (fun a => eval t (flipBit a i)) = eval t := by
    funext a
    exact hflip_eval t h a
  rw [hfun]
  exact uniformErrorFn_self (f := eval t)


/-- Auto-promoted from claim CANARY_KEEP_007. -/
theorem canary_uniformError_self_zero_007 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using active_uniformError_self_zero (t := t)


/-- Auto-promoted from claim CANARY_KEEP_008. -/
theorem canary_uniformError_self_zero_008 (t : DTree n) :
    uniformError t t = 0 := by
  simpa using active_uniformError_self_zero (t := t)

end Formal
