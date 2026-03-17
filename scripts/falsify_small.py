from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import product
from pathlib import Path
from typing import Callable, Iterable

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.common import BENCH_DIR, CLAIMS_DIR, STATE_DIR, load_jsonl, read_json, write_json


Assignment = tuple[bool, ...]


@dataclass(frozen=True)
class Tree:
    kind: str
    value: bool | None = None
    var: int | None = None
    left: "Tree | None" = None
    right: "Tree | None" = None

    @staticmethod
    def leaf(value: bool) -> "Tree":
        return Tree(kind="leaf", value=value)

    @staticmethod
    def node(var: int, left: "Tree", right: "Tree") -> "Tree":
        return Tree(kind="node", var=var, left=left, right=right)


def all_assignments(n: int) -> list[Assignment]:
    return [tuple(bits) for bits in product([False, True], repeat=n)]


def eval_tree(tree: Tree, assignment: Assignment) -> bool:
    if tree.kind == "leaf":
        return bool(tree.value)
    assert tree.var is not None and tree.left is not None and tree.right is not None
    return eval_tree(tree.right if assignment[tree.var] else tree.left, assignment)


def vars_used(tree: Tree) -> set[int]:
    if tree.kind == "leaf":
        return set()
    assert tree.var is not None and tree.left is not None and tree.right is not None
    return {tree.var} | vars_used(tree.left) | vars_used(tree.right)


def apply_restriction(assignment: Assignment, restriction: dict[int, bool], n: int) -> Assignment:
    return tuple(restriction.get(i, assignment[i]) for i in range(n))


def restrict_tree(tree: Tree, restriction: dict[int, bool]) -> Tree:
    if tree.kind == "leaf":
        return tree
    assert tree.var is not None and tree.left is not None and tree.right is not None
    if tree.var in restriction:
        branch = tree.right if restriction[tree.var] else tree.left
        return restrict_tree(branch, restriction)
    return Tree.node(tree.var, restrict_tree(tree.left, restriction), restrict_tree(tree.right, restriction))


def is_monotone_fn(n: int, fn: Callable[[Assignment], bool]) -> bool:
    assignments = all_assignments(n)
    for a in assignments:
        for b in assignments:
            if all((not a[i]) or b[i] for i in range(n)) and fn(a) and not fn(b):
                return False
    return True


def uniform_error(n: int, left: Callable[[Assignment], bool], right: Callable[[Assignment], bool]) -> Fraction:
    assignments = all_assignments(n)
    disagree = sum(1 for assignment in assignments if left(assignment) != right(assignment))
    return Fraction(disagree, max(1, len(assignments)))


def flip_bit(assignment: Assignment, index: int) -> Assignment:
    flipped = list(assignment)
    flipped[index] = not flipped[index]
    return tuple(flipped)


def influence(n: int, fn: Callable[[Assignment], bool], index: int) -> Fraction:
    return uniform_error(n, fn, lambda assignment: fn(flip_bit(assignment, index)))


@lru_cache(maxsize=None)
def exhaustive_trees(n: int, internal_nodes: int) -> tuple[Tree, ...]:
    if internal_nodes == 0:
        return (Tree.leaf(False), Tree.leaf(True))
    if n == 0:
        return ()
    trees: list[Tree] = []
    for var in range(n):
        for left_nodes in range(internal_nodes):
            right_nodes = internal_nodes - 1 - left_nodes
            for left in exhaustive_trees(n, left_nodes):
                for right in exhaustive_trees(n, right_nodes):
                    trees.append(Tree.node(var, left, right))
    return tuple(trees)


def random_tree(n: int, internal_budget: int, rng: random.Random) -> Tree:
    if internal_budget == 0 or n == 0 or rng.random() < 0.35:
        return Tree.leaf(rng.choice([False, True]))
    left_budget = rng.randint(0, internal_budget - 1)
    right_budget = internal_budget - 1 - left_budget
    return Tree.node(
        rng.randrange(n),
        random_tree(n, left_budget, rng),
        random_tree(n, right_budget, rng),
    )


def iter_test_trees(n: int, bounds: dict[str, int]) -> Iterable[Tree]:
    max_internal = bounds["max_internal_nodes"]
    max_examples = bounds["max_examples"]
    produced = 0
    for internal_nodes in range(min(max_internal, 2) + 1):
        for tree in exhaustive_trees(n, internal_nodes):
            yield tree
            produced += 1
            if produced >= max_examples:
                return
    rng = random.Random(bounds["random_seed"] + n)
    for _ in range(bounds["random_trees_per_n"]):
        yield random_tree(n, min(max_internal, 3), rng)


def iter_restrictions(n: int) -> Iterable[dict[int, bool]]:
    vars_ = range(n)
    for mask in range(1 << n):
        domain = [index for index in vars_ if mask & (1 << index)]
        for values in product([False, True], repeat=len(domain)):
            yield dict(zip(domain, values))


def classify_survival(
    claim_id: str,
    checker: Callable[[dict[str, int]], tuple[str, dict | None]],
    bounds: dict[str, int],
) -> dict:
    start = time.perf_counter()
    result, counterexample = checker(bounds)
    return {
        "claim_id": claim_id,
        "result": result,
        "searched": {
            "n_max": bounds["n_max"],
            "max_internal_nodes": bounds["max_internal_nodes"],
            "max_examples": bounds["max_examples"],
        },
        "counterexample": counterexample,
        "runtime_sec": round(time.perf_counter() - start, 4),
    }


def check_restriction_semantics(bounds: dict[str, int]) -> tuple[str, dict | None]:
    for n in range(bounds["n_max"] + 1):
        assignments = all_assignments(n)
        for tree in iter_test_trees(n, bounds):
            for restriction in iter_restrictions(n):
                restricted = restrict_tree(tree, restriction)
                for assignment in assignments:
                    left = eval_tree(restricted, assignment)
                    right = eval_tree(tree, apply_restriction(assignment, restriction, n))
                    if left != right:
                        return "falsified_small_n", {
                            "n": n,
                            "restriction": restriction,
                            "assignment": assignment,
                        }
    return "survives_small_n", None


def check_restriction_preserves_monotonicity(bounds: dict[str, int]) -> tuple[str, dict | None]:
    for n in range(bounds["n_max"] + 1):
        for tree in iter_test_trees(n, bounds):
            fn = lambda assignment, tree=tree: eval_tree(tree, assignment)
            if not is_monotone_fn(n, fn):
                continue
            for restriction in iter_restrictions(n):
                restricted_fn = lambda assignment, restriction=restriction, fn=fn: fn(
                    apply_restriction(assignment, restriction, n)
                )
                if not is_monotone_fn(n, restricted_fn):
                    return "falsified_small_n", {"n": n, "restriction": restriction}
    return "survives_small_n", None


def check_uniform_error_self(bounds: dict[str, int]) -> tuple[str, dict | None]:
    for n in range(bounds["n_max"] + 1):
        for tree in iter_test_trees(n, bounds):
            fn = lambda assignment, tree=tree: eval_tree(tree, assignment)
            if uniform_error(n, fn, fn) != 0:
                return "falsified_small_n", {"n": n}
    return "survives_small_n", None


def check_uniform_error_symmetry(bounds: dict[str, int]) -> tuple[str, dict | None]:
    for n in range(bounds["n_max"] + 1):
        trees = list(iter_test_trees(n, bounds))
        for left in trees:
            for right in trees[: min(len(trees), 12)]:
                left_fn = lambda assignment, left=left: eval_tree(left, assignment)
                right_fn = lambda assignment, right=right: eval_tree(right, assignment)
                if uniform_error(n, left_fn, right_fn) != uniform_error(n, right_fn, left_fn):
                    return "falsified_small_n", {"n": n}
    return "survives_small_n", None


def check_influence_const(bounds: dict[str, int], value: bool) -> tuple[str, dict | None]:
    for n in range(1, bounds["n_max"] + 1):
        fn = lambda assignment, value=value: value
        for index in range(n):
            if influence(n, fn, index) != 0:
                return "falsified_small_n", {"n": n, "index": index}
    return "survives_small_n", None


def check_influence_unused_var(bounds: dict[str, int]) -> tuple[str, dict | None]:
    for n in range(1, bounds["n_max"] + 1):
        for tree in iter_test_trees(n, bounds):
            used = vars_used(tree)
            fn = lambda assignment, tree=tree: eval_tree(tree, assignment)
            for index in range(n):
                if index not in used and influence(n, fn, index) != 0:
                    return "falsified_small_n", {"n": n, "index": index, "used": sorted(used)}
    return "survives_small_n", None


CLAIM_CHECKERS: dict[str, Callable[[dict[str, int]], tuple[str, dict | None]]] = {
    "BLANC22_MONO_001": check_restriction_preserves_monotonicity,
    "DTREE_RES_001": check_restriction_semantics,
    "DTREE_ERR_001": check_uniform_error_self,
    "DTREE_ERR_002": check_uniform_error_symmetry,
    "DTREE_INF_001": lambda bounds: check_influence_const(bounds, False),
    "DTREE_INF_002": lambda bounds: check_influence_const(bounds, True),
    "DTREE_INF_003": check_influence_unused_var,
}


def load_candidates() -> list[dict]:
    return load_jsonl(CLAIMS_DIR / "candidates.jsonl")


def resolve_claim_ids(args: argparse.Namespace) -> list[str]:
    if args.claim_id:
        return [args.claim_id]
    if args.current_claim_only:
        progress = read_json(STATE_DIR / "progress.json")
        return [progress["active_claim_id"]]
    return [claim["claim_id"] for claim in load_candidates() if claim.get("small_check")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claim-id")
    parser.add_argument("--current-claim-only", action="store_true")
    parser.add_argument("--write")
    args = parser.parse_args()

    bounds = read_json(BENCH_DIR / "falsifier_config.json")
    results: list[dict] = []
    for claim_id in resolve_claim_ids(args):
        checker = CLAIM_CHECKERS.get(claim_id)
        if checker is None:
            results.append(
                {
                    "claim_id": claim_id,
                    "result": "not_executable",
                    "searched": {
                        "n_max": bounds["n_max"],
                        "max_internal_nodes": bounds["max_internal_nodes"],
                        "max_examples": bounds["max_examples"],
                    },
                    "counterexample": None,
                    "runtime_sec": 0.0,
                }
            )
            continue
        results.append(classify_survival(claim_id, checker, bounds))

    output: dict[str, object]
    if len(results) == 1:
        output = results[0]
    else:
        output = {"results": results}

    if args.write:
        write_json(Path(args.write), output)
    else:
        default_path = STATE_DIR / "falsifier_results.json"
        write_json(default_path, output)
    print(json.dumps(output, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
