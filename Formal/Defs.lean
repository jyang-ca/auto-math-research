import Mathlib

namespace Formal

abbrev Var (n : Nat) := Fin n
abbrev Assignment (n : Nat) := Var n → Bool

inductive DTree (n : Nat) where
  | leaf : Bool → DTree n
  | node : Var n → DTree n → DTree n → DTree n
  deriving DecidableEq, Repr

def eval : DTree n → Assignment n → Bool
  | .leaf b, _ => b
  | .node v left right, a => if a v then eval right a else eval left a

@[simp] theorem eval_leaf (b : Bool) (a : Assignment n) :
    eval (DTree.leaf b) a = b := rfl

@[simp] theorem eval_node (v : Var n) (left right : DTree n) (a : Assignment n) :
    eval (DTree.node v left right) a =
      if a v then eval right a else eval left a := rfl

def numInternal : DTree n → Nat
  | .leaf _ => 0
  | .node _ left right => 1 + numInternal left + numInternal right

def numLeaves : DTree n → Nat
  | .leaf _ => 1
  | .node _ left right => numLeaves left + numLeaves right

def depth : DTree n → Nat
  | .leaf _ => 0
  | .node _ left right => 1 + max (depth left) (depth right)

def varsUsed : DTree n → Finset (Var n)
  | .leaf _ => ∅
  | .node v left right => insert v (varsUsed left ∪ varsUsed right)

abbrev modelSize : DTree n → Nat := numLeaves

@[simp] theorem numInternal_leaf (b : Bool) :
    numInternal (DTree.leaf (n := n) b) = 0 := rfl

@[simp] theorem numInternal_node (v : Var n) (left right : DTree n) :
    numInternal (DTree.node v left right) =
      1 + numInternal left + numInternal right := rfl

@[simp] theorem numLeaves_leaf (b : Bool) :
    numLeaves (DTree.leaf (n := n) b) = 1 := rfl

@[simp] theorem numLeaves_node (v : Var n) (left right : DTree n) :
    numLeaves (DTree.node v left right) = numLeaves left + numLeaves right := rfl

@[simp] theorem depth_leaf (b : Bool) :
    depth (DTree.leaf (n := n) b) = 0 := rfl

@[simp] theorem depth_node (v : Var n) (left right : DTree n) :
    depth (DTree.node v left right) = 1 + max (depth left) (depth right) := rfl

@[simp] theorem varsUsed_leaf (b : Bool) :
    varsUsed (DTree.leaf (n := n) b) = ∅ := rfl

@[simp] theorem varsUsed_node (v : Var n) (left right : DTree n) :
    varsUsed (DTree.node v left right) = insert v (varsUsed left ∪ varsUsed right) := rfl

def assignmentLE (a b : Assignment n) : Prop :=
  ∀ v, a v = true → b v = true

scoped infix:50 " ≤ₐ " => assignmentLE

def isMonotoneFn (f : Assignment n → Bool) : Prop :=
  ∀ ⦃a b⦄, a ≤ₐ b → f a = true → f b = true

def treeComputesMonotone (t : DTree n) : Prop :=
  isMonotoneFn (eval t)

structure Restriction (n : Nat) where
  dom : Finset (Var n)
  val : Var n → Bool

def applyRestrictionToAssignment (ρ : Restriction n) (a : Assignment n) : Assignment n :=
  fun v => if v ∈ ρ.dom then ρ.val v else a v

def restrictFn (ρ : Restriction n) (f : Assignment n → Bool) : Assignment n → Bool :=
  fun a => f (applyRestrictionToAssignment ρ a)

def restrictTree (ρ : Restriction n) : DTree n → DTree n
  | .leaf b => .leaf b
  | .node v left right =>
      if _h : v ∈ ρ.dom then
        if ρ.val v then
          restrictTree ρ right
        else
          restrictTree ρ left
      else
        .node v (restrictTree ρ left) (restrictTree ρ right)

@[simp] theorem applyRestrictionToAssignment_of_mem
    (ρ : Restriction n) (a : Assignment n) {v : Var n} (h : v ∈ ρ.dom) :
    applyRestrictionToAssignment ρ a v = ρ.val v := by
  simp [applyRestrictionToAssignment, h]

@[simp] theorem applyRestrictionToAssignment_of_not_mem
    (ρ : Restriction n) (a : Assignment n) {v : Var n} (h : v ∉ ρ.dom) :
    applyRestrictionToAssignment ρ a v = a v := by
  simp [applyRestrictionToAssignment, h]

theorem applyRestrictionToAssignment_monotone (ρ : Restriction n)
    {a b : Assignment n} (hab : a ≤ₐ b) :
    applyRestrictionToAssignment ρ a ≤ₐ applyRestrictionToAssignment ρ b := by
  intro v hv
  by_cases h : v ∈ ρ.dom
  · simpa [applyRestrictionToAssignment, h] using hv
  · have hv' : a v = true := by
      simpa [applyRestrictionToAssignment, h] using hv
    simpa [applyRestrictionToAssignment, h] using hab v hv'

@[simp] theorem restrictTree_eval (ρ : Restriction n) (t : DTree n) (a : Assignment n) :
    eval (restrictTree ρ t) a = restrictFn ρ (eval t) a := by
  induction t with
  | leaf b =>
      rfl
  | node v left right ihLeft ihRight =>
      by_cases h : v ∈ ρ.dom
      · by_cases hv : ρ.val v
        · simp [restrictTree, h, hv, restrictFn, applyRestrictionToAssignment, ihRight]
        · simp [restrictTree, h, hv, restrictFn, applyRestrictionToAssignment, ihLeft]
      · simp [restrictTree, h, restrictFn, applyRestrictionToAssignment, ihLeft, ihRight]

theorem restrictFn_preserves_monotonicity (ρ : Restriction n)
    {f : Assignment n → Bool} (hf : isMonotoneFn f) :
    isMonotoneFn (restrictFn ρ f) := by
  intro a b hab hfa
  exact hf (applyRestrictionToAssignment_monotone ρ hab) hfa

def disagreementCountFn (f g : Assignment n → Bool) : Nat :=
  (Finset.univ.filter fun a => f a ≠ g a).card

def cubeCard (n : Nat) : Nat :=
  Fintype.card (Assignment n)

def uniformErrorFn (f g : Assignment n → Bool) : Rat :=
  disagreementCountFn f g / cubeCard n

def uniformError (t u : DTree n) : Rat :=
  uniformErrorFn (eval t) (eval u)

def flipBit (a : Assignment n) (i : Var n) : Assignment n :=
  fun j => if _h : j = i then !(a i) else a j

@[simp] theorem flipBit_same (a : Assignment n) (i : Var n) :
    flipBit a i i = !(a i) := by
  simp [flipBit]

@[simp] theorem flipBit_ne (a : Assignment n) {i j : Var n} (h : j ≠ i) :
    flipBit a i j = a j := by
  simp [flipBit, h]

def influence (f : Assignment n → Bool) (i : Var n) : Rat :=
  uniformErrorFn f (fun a => f (flipBit a i))

end Formal
