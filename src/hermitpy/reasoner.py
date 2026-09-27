"""Public classification API over an rdflib graph."""

from __future__ import annotations

from typing import List, Optional, Tuple

from rdflib import Graph

from .errors import InconsistentOntology
from .load import Ontology, load_ontology
from .syntax import OWL_NOTHING, OWL_THING, Atom, Conj, Neg, nnf
from .tableau import Solver


class Reasoner:
    """Classify a description-logic ontology loaded from RDF.

    The supported fragment is named classes, ``rdfs:subClassOf``,
    ``owl:equivalentClass``, ``owl:disjointWith``, complement, intersection,
    union, existential and universal object restrictions, inverses, transitive
    and symmetric object properties, ``rdfs:domain``, ``rdfs:range``, class
    assertions, and object-property assertions. Other OWL constructs raise
    ``UnsupportedConstruct``.
    """

    def __init__(self, graph: Graph) -> None:
        self.ontology: Ontology = load_ontology(graph)
        self._solver = Solver(self.ontology)
        self._consistent: Optional[bool] = None

    def is_consistent(self) -> bool:
        """Return whether the ontology has a model."""

        if self._consistent is None:
            self._consistent = self._solver.consistent()
        return self._consistent

    def unsatisfiable_classes(self) -> List[str]:
        """Return named classes that are empty in every model."""

        if not self.is_consistent():
            return sorted(self.ontology.named_classes)
        return [
            iri
            for iri in sorted(self.ontology.named_classes)
            if not self._solver.concept_satisfiable(Atom(iri))
        ]

    def direct_subclasses(self) -> List[Tuple[str, str]]:
        """Return direct subclass pairs, including links to owl:Thing.

        Equivalent named classes are returned in both directions. An
        inconsistent ontology raises ``InconsistentOntology`` instead of
        collapsing every class to owl:Nothing.
        """

        if not self.is_consistent():
            raise InconsistentOntology("Cannot classify an inconsistent ontology.")
        unsatisfiable = set(self.unsatisfiable_classes())
        satisfiable = [
            iri
            for iri in sorted(self.ontology.named_classes)
            if iri not in unsatisfiable
        ]
        nodes = [OWL_THING] + satisfiable
        subsumes = {iri: {iri} for iri in nodes}
        for subclass in nodes:
            for superclass in nodes:
                if subclass != superclass and self._subsumes(subclass, superclass):
                    subsumes[subclass].add(superclass)

        pairs = set()
        for left in satisfiable:
            for right in satisfiable:
                if left < right and right in subsumes[left] and left in subsumes[right]:
                    pairs.add((left, right))
                    pairs.add((right, left))
        for subclass in nodes:
            if subclass == OWL_THING:
                continue
            proper = [
                superclass
                for superclass in subsumes[subclass]
                if superclass != subclass and subclass not in subsumes[superclass]
            ]
            for superclass in proper:
                if any(
                    _strictly_between(subclass, middle, superclass, subsumes)
                    for middle in proper
                ):
                    continue
                pairs.add((subclass, superclass))
        unsatisfiable_list = sorted(unsatisfiable)
        for iri in unsatisfiable_list:
            pairs.add((iri, OWL_NOTHING))
        for left in unsatisfiable_list:
            for right in unsatisfiable_list:
                if left < right:
                    pairs.add((left, right))
                    pairs.add((right, left))
        return sorted(pairs)

    def _subsumes(self, subclass: str, superclass: str) -> bool:
        if subclass == superclass:
            return True
        concept = nnf(Conj((Atom(subclass), Neg(superclass))))
        return not self._solver.concept_satisfiable(concept)


def _strictly_between(
    subclass: str,
    middle: str,
    superclass: str,
    subsumes: dict,
) -> bool:
    return (
        middle != subclass
        and middle != superclass
        and middle in subsumes[subclass]
        and superclass in subsumes[middle]
        and subclass not in subsumes[middle]
        and middle not in subsumes[superclass]
    )
