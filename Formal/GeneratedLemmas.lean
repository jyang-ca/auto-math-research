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


/-- Auto-promoted from claim DTREE_VARS_001. -/
theorem restrictTree_varsUsed_subset (ρ : Restriction n) (t : DTree n) :
    varsUsed (restrictTree ρ t) ⊆ varsUsed t := by
  induction t with
  | leaf b =>
      simp [restrictTree]
  | node v left right ihLeft ihRight =>
      by_cases h : v ∈ ρ.dom
      · by_cases hv : ρ.val v
        · simpa [restrictTree, h, hv] using
            (show varsUsed (restrictTree ρ right) ⊆ insert v (varsUsed left ∪ varsUsed right) from
              calc
                varsUsed (restrictTree ρ right) ⊆ varsUsed right := ihRight
                _ ⊆ varsUsed left ∪ varsUsed right := Finset.subset_union_right
                _ ⊆ insert v (varsUsed left ∪ varsUsed right) := Finset.subset_insert _ _)
        · simpa [restrictTree, h, hv] using
            (show varsUsed (restrictTree ρ left) ⊆ insert v (varsUsed left ∪ varsUsed right) from
              calc
                varsUsed (restrictTree ρ left) ⊆ varsUsed left := ihLeft
                _ ⊆ varsUsed left ∪ varsUsed right := Finset.subset_union_left
                _ ⊆ insert v (varsUsed left ∪ varsUsed right) := Finset.subset_insert _ _)
      · simpa [restrictTree, h] using
          (Finset.insert_subset_insert v (Finset.union_subset_union ihLeft ihRight))

end Formal
