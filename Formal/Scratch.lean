import Formal.Active

namespace Formal

def sampleTree : DTree 2 :=
  DTree.node ⟨0, by decide⟩
    (DTree.leaf false)
    (DTree.node ⟨1, by decide⟩ (DTree.leaf true) (DTree.leaf false))

def a00 : Assignment 2 := fun _ => false

def a10 : Assignment 2 := fun i =>
  i = ⟨0, by decide⟩

def a11 : Assignment 2 := fun _ => true

def sampleRestriction : Restriction 2 where
  dom := {⟨0, by decide⟩}
  val := fun _ => true

#guard eval sampleTree a00 = false
#guard eval sampleTree a10 = true
#guard eval sampleTree a11 = false
#guard numInternal sampleTree = 2
#guard numLeaves sampleTree = 3
#guard depth sampleTree = 2
#guard eval (restrictTree sampleRestriction sampleTree) a00 =
  restrictFn sampleRestriction (eval sampleTree) a00

#print DTree
#check eval
#check uniformErrorFn
#check influence

end Formal
