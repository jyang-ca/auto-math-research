import Formal.GeneratedLemmas

namespace Formal

abbrev ProperUniformLearner (n : Nat) :=
  (Assignment n → Bool) → DTree n

def uniformProperLearningOpenProblemStatement : Prop :=
  ∀ n _s : Nat, ∀ ε δ : Rat, 0 < ε → 0 < δ →
    ∃ _learner : ProperUniformLearner n, True

def monotoneTargetMilestoneStatement : Prop :=
  ∀ n _s : Nat, ∀ ε δ : Rat, 0 < ε → 0 < δ →
    ∃ _learner : ProperUniformLearner n,
      ∀ target : DTree n, treeComputesMonotone target → True

end Formal
