import Formal.Defs

namespace Formal

def allFalseAssignment (n : Nat) : Assignment n := fun _ => false
def allTrueAssignment (n : Nat) : Assignment n := fun _ => true

theorem allFalse_le_allTrue (n : Nat) :
    allFalseAssignment n ≤ₐ allTrueAssignment n := by
  intro v hv
  simp [allTrueAssignment]

theorem monotone_const_false : isMonotoneFn (fun _ : Assignment n => false) := by
  intro a b hab hfa
  simp at hfa

theorem monotone_const_true : isMonotoneFn (fun _ : Assignment n => true) := by
  intro a b hab hfa
  simp

theorem monotone_projection (i : Var n) : isMonotoneFn (fun a : Assignment n => a i) := by
  intro a b hab hai
  exact hab i hai

theorem leaf_computes_monotone (b : Bool) :
    treeComputesMonotone (DTree.leaf (n := n) b) := by
  cases b
  · simpa [treeComputesMonotone] using (monotone_const_false (n := n))
  · simpa [treeComputesMonotone] using (monotone_const_true (n := n))

theorem restriction_preserves_monotonicity (ρ : Restriction n)
    {f : Assignment n → Bool} (hf : isMonotoneFn f) :
    isMonotoneFn (restrictFn ρ f) :=
  restrictFn_preserves_monotonicity ρ hf

theorem restricted_tree_computes_monotone (ρ : Restriction n) {t : DTree n}
    (ht : treeComputesMonotone t) :
    treeComputesMonotone (restrictTree ρ t) := by
  intro a b hab hEval
  rw [restrictTree_eval] at hEval ⊢
  exact restriction_preserves_monotonicity ρ ht hab hEval

theorem disagreementCountFn_symm (f g : Assignment n → Bool) :
    disagreementCountFn f g = disagreementCountFn g f := by
  unfold disagreementCountFn
  congr
  ext a
  simp [ne_comm]

theorem disagreementCountFn_self (f : Assignment n → Bool) :
    disagreementCountFn f f = 0 := by
  unfold disagreementCountFn
  simp

theorem uniformErrorFn_symm (f g : Assignment n → Bool) :
    uniformErrorFn f g = uniformErrorFn g f := by
  simp [uniformErrorFn, disagreementCountFn_symm]

theorem uniformErrorFn_self (f : Assignment n → Bool) :
    uniformErrorFn f f = 0 := by
  simp [uniformErrorFn, disagreementCountFn_self]

theorem uniformError_symm (t u : DTree n) :
    uniformError t u = uniformError u t := by
  exact uniformErrorFn_symm (eval t) (eval u)

theorem influence_const_false_zero (i : Var n) :
    influence (fun _ : Assignment n => false) i = 0 := by
  simp [influence, uniformErrorFn_self]

theorem influence_const_true_zero (i : Var n) :
    influence (fun _ : Assignment n => true) i = 0 := by
  simp [influence, uniformErrorFn_self]

theorem not_monotone_neg_projection_one :
    ¬ isMonotoneFn (fun a : Assignment 1 => !(a ⟨0, by decide⟩)) := by
  intro hmono
  let a : Assignment 1 := allFalseAssignment 1
  let b : Assignment 1 := allTrueAssignment 1
  have hab : a ≤ₐ b := allFalse_le_allTrue 1
  have hstart : (fun x : Assignment 1 => !(x ⟨0, by decide⟩)) a = true := by
    simp [a, allFalseAssignment]
  have hend := hmono hab hstart
  simp [b, allTrueAssignment] at hend

theorem not_monotone_neg_projection_two :
    ¬ isMonotoneFn (fun a : Assignment 2 => !(a ⟨0, by decide⟩)) := by
  intro hmono
  let a : Assignment 2 := allFalseAssignment 2
  let b : Assignment 2 := allTrueAssignment 2
  have hab : a ≤ₐ b := allFalse_le_allTrue 2
  have hstart : (fun x : Assignment 2 => !(x ⟨0, by decide⟩)) a = true := by
    simp [a, allFalseAssignment]
  have hend := hmono hab hstart
  simp [b, allTrueAssignment] at hend

end Formal
