"""Completion-graph search for the supported description-logic fragment."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Set, Tuple

from .errors import ReasonerLimitExceeded
from .load import Ontology
from .syntax import (
    BOTTOM,
    TOP,
    Atom,
    Conj,
    Concept,
    Disj,
    Exists,
    Forall,
    Neg,
    Role,
    nnf,
)

MAX_NODES = 256
MAX_DEPTH = 4096


@dataclass
class _State:
    labels: Dict[int, Set[Concept]]
    edges: Set[Tuple[int, Role, int]]
    parent: Dict[int, Optional[int]]
    parent_role: Dict[int, Optional[Role]]
    next_id: int

    def clone(self) -> "_State":
        return _State(
            labels={node: set(concepts) for node, concepts in self.labels.items()},
            edges=set(self.edges),
            parent=dict(self.parent),
            parent_role=dict(self.parent_role),
            next_id=self.next_id,
        )


class Solver:
    """Decide satisfiability for one loaded ontology."""

    def __init__(self, ontology: Ontology) -> None:
        self.ontology = ontology
        self._cache: Dict[Concept, bool] = {}

    def consistent(self) -> bool:
        """Return whether the ontology has a model."""

        return self._search(self._abox_state())

    def concept_satisfiable(self, concept: Concept) -> bool:
        """Return whether a concept is satisfiable in the TBox.

        This ignores the ABox. Callers that need ontology satisfiability check
        ``consistent`` first. Without nominals, a consistent ABox does not
        change class subsumption.
        """

        concept = nnf(concept)
        if concept == BOTTOM:
            return False
        cached = self._cache.get(concept)
        if cached is not None:
            return cached
        root = [] if concept == TOP else [concept]
        result = self._search(self._root_state(root))
        self._cache[concept] = result
        return result

    def _abox_state(self) -> _State:
        if not self.ontology.individuals:
            return self._root_state([])
        labels: Dict[int, Set[Concept]] = {}
        parent: Dict[int, Optional[int]] = {}
        parent_role: Dict[int, Optional[Role]] = {}
        ids = {}
        for index, iri in enumerate(sorted(self.ontology.individuals)):
            ids[iri] = index
            labels[index] = set(self.ontology.individuals[iri])
            parent[index] = None
            parent_role[index] = None
        edges = {
            (ids[source], role, ids[target])
            for source, role, target in self.ontology.assertions
        }
        return _State(labels, edges, parent, parent_role, len(ids))

    def _root_state(self, concepts: Sequence[Concept]) -> _State:
        return _State(
            labels={0: set(concepts)},
            edges=set(),
            parent={0: None},
            parent_role={0: None},
            next_id=1,
        )

    def _search(self, state: _State, depth: int = 0) -> bool:
        if depth > MAX_DEPTH:
            raise ReasonerLimitExceeded("tableau search depth exceeded")
        if not self._saturate(state):
            return False
        choice = self._open_disjunction(state)
        if choice is not None:
            node, operands = choice
            for operand in operands:
                branch = state.clone()
                self._add(branch, node, operand)
                if self._search(branch, depth + 1):
                    return True
            return False
        if self._spawn_one(state):
            return self._search(state, depth + 1)
        return True

    def _saturate(self, state: _State) -> bool:
        changed = True
        while changed:
            changed = False
            for label in state.labels.values():
                if self._clash(label):
                    return False
            for node in list(state.labels):
                if self._close_node(state, node):
                    changed = True
            if self._propagate_edges(state):
                changed = True
        return all(not self._clash(label) for label in state.labels.values())

    def _close_node(self, state: _State, node: int) -> bool:
        changed = False
        for concept in self.ontology.gcis:
            if self._add(state, node, concept):
                changed = True
        for concept in list(state.labels[node]):
            if isinstance(concept, Conj):
                for operand in concept.operands:
                    if self._add(state, node, operand):
                        changed = True
            elif isinstance(concept, Atom):
                for extra in self.ontology.unfold.get(concept.iri, ()):
                    if self._add(state, node, extra):
                        changed = True
            elif isinstance(concept, Forall):
                for neighbor in self._neighbors(state, node, concept.role):
                    if concept.filler != TOP and self._add(
                        state, neighbor, concept.filler
                    ):
                        changed = True
                    if self.ontology.is_transitive(concept.role) and self._add(
                        state, neighbor, concept
                    ):
                        changed = True
        return changed

    def _propagate_edges(self, state: _State) -> bool:
        changed = False
        for source, role, target in list(state.edges):
            for concept in self.ontology.domains.get(role, ()):
                if self._add(state, source, concept):
                    changed = True
            for concept in self.ontology.ranges.get(role, ()):
                if self._add(state, target, concept):
                    changed = True
        return changed

    def _spawn_one(self, state: _State) -> bool:
        blocked: Dict[int, bool] = {}
        for node in sorted(state.labels):
            if self._blocked(state, node, blocked):
                continue
            for concept in sorted(state.labels[node], key=repr):
                if not isinstance(concept, Exists):
                    continue
                if self._exists_satisfied(state, node, concept):
                    continue
                self._create_successor(state, node, concept)
                return True
        return False

    def _exists_satisfied(self, state: _State, node: int, concept: Exists) -> bool:
        neighbors = self._neighbors(state, node, concept.role)
        if concept.filler == TOP:
            return bool(neighbors)
        return any(concept.filler in state.labels[item] for item in neighbors)

    def _create_successor(self, state: _State, node: int, concept: Exists) -> None:
        if len(state.labels) >= MAX_NODES:
            raise ReasonerLimitExceeded(
                "tableau exceeded {} nodes; the fragment search did not "
                "terminate".format(MAX_NODES)
            )
        successor = state.next_id
        state.next_id += 1
        state.labels[successor] = set()
        state.parent[successor] = node
        state.parent_role[successor] = concept.role
        state.edges.add((node, concept.role, successor))
        if concept.filler != TOP:
            self._add(state, successor, concept.filler)

    def _neighbors(self, state: _State, node: int, role: Role) -> List[int]:
        inverse = self.ontology.inverse_role(role)
        found = []
        for source, edge_role, target in state.edges:
            if source == node and edge_role == role:
                found.append(target)
            elif target == node and edge_role == inverse:
                found.append(source)
        return found

    def _blocked(self, state: _State, node: int, memo: Dict[int, bool]) -> bool:
        """Pairwise equality blocking for inverses and transitive roles."""

        if node in memo:
            return memo[node]
        parent = state.parent[node]
        if parent is None:
            memo[node] = False
            return False
        if self._blocked(state, parent, memo):
            memo[node] = True
            return True
        role = state.parent_role[node]
        ancestor = parent
        while state.parent[ancestor] is not None:
            ancestor_parent = state.parent[ancestor]
            if (
                state.labels[node] == state.labels[ancestor]
                and state.labels[parent] == state.labels[ancestor_parent]
                and role == state.parent_role[ancestor]
            ):
                memo[node] = True
                return True
            ancestor = ancestor_parent
        memo[node] = False
        return False

    def _open_disjunction(
        self, state: _State
    ) -> Optional[Tuple[int, tuple]]:
        for node in sorted(state.labels):
            for concept in sorted(state.labels[node], key=repr):
                if isinstance(concept, Disj) and not any(
                    operand in state.labels[node] for operand in concept.operands
                ):
                    return node, concept.operands
        return None

    def _add(self, state: _State, node: int, concept: Concept) -> bool:
        concept = nnf(concept)
        if concept == TOP or concept in state.labels[node]:
            return False
        state.labels[node].add(concept)
        return True

    def _clash(self, label: Set[Concept]) -> bool:
        if BOTTOM in label:
            return True
        atoms = {concept.iri for concept in label if isinstance(concept, Atom)}
        return any(isinstance(concept, Neg) and concept.iri in atoms for concept in label)
