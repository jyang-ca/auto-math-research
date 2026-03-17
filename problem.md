# Problem
Formalize the SolveAll problem on properly learning decision trees in polynomial time under the uniform distribution with membership queries.

# Current MVP Scope
We are not solving the full open problem.
We are building formal infrastructure and targeting the monotone-target intermediate milestone plus adjacent structural lemmas.

# Stable Definitions Required
- decision tree
- assignment on {0,1}^n
- restriction
- monotonicity
- uniform error
- influence

# Current Active Frontier
- formalize theorem statements for the open problem and the monotone-target milestone
- prove restriction and monotonicity interaction lemmas
- search executable candidate lemmas around influence and splitting

# What Counts as Progress
- a new promoted lemma
- a current theorem proved without sorry
- a claim falsified and rewritten into a sharper claim
- a new theorem statement compiled with correct dependencies

# What Does Not Count as Progress
- adding comments only
- expanding scope without proving anything
- replacing proofs with assumptions
- editing stable files directly

# Seed Papers
- open problem note
- almost-polynomial-time algorithm paper
- query-learning hardness papers

# Preferred Research Order
1. definitions
2. semantic lemmas
3. monotonicity + restriction
4. uniform error + influence
5. conjecture extraction
6. bounded falsification
7. active proof search
