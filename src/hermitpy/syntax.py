"""OWL class and role expressions in negation normal form."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Sequence, Union

OWL_THING = "http://www.w3.org/2002/07/owl#Thing"
OWL_NOTHING = "http://www.w3.org/2002/07/owl#Nothing"


@dataclass(frozen=True)
class Role:
    """An object-property IRI, optionally in the inverse direction."""

    iri: str
    inverse: bool = False


@dataclass(frozen=True)
class Atom:
    """A named class, owl:Thing, or owl:Nothing."""

    iri: str


@dataclass(frozen=True)
class Neg:
    """Negation of a named class. Complex negation is pushed inward."""

    iri: str


@dataclass(frozen=True)
class Conj:
    """Conjunction of negation-normal concepts."""

    operands: tuple


@dataclass(frozen=True)
class Disj:
    """Disjunction of negation-normal concepts."""

    operands: tuple


@dataclass(frozen=True)
class Exists:
    """Existential restriction on an object property."""

    role: Role
    filler: "Concept"


@dataclass(frozen=True)
class Forall:
    """Universal restriction on an object property."""

    role: Role
    filler: "Concept"


Concept = Union[Atom, Neg, Conj, Disj, Exists, Forall]

TOP = Atom(OWL_THING)
BOTTOM = Atom(OWL_NOTHING)


def nnf(concept: Concept) -> Concept:
    """Return the negation normal form of a concept."""

    return _nnf(concept, False)


def negate(concept: Concept) -> Concept:
    """Return the negation normal form of the complement of a concept."""

    return _nnf(concept, True)


def inclusion(lhs: Concept, rhs: Concept) -> Concept:
    """Return the NNF concept expressing that lhs is a subclass of rhs."""

    return _disj((negate(lhs), nnf(rhs)))


def _nnf(concept: Concept, negated: bool) -> Concept:
    if isinstance(concept, Atom):
        if negated:
            if concept.iri == OWL_THING:
                return BOTTOM
            if concept.iri == OWL_NOTHING:
                return TOP
            return Neg(concept.iri)
        if concept.iri == OWL_NOTHING:
            return BOTTOM
        if concept.iri == OWL_THING:
            return TOP
        return concept
    if isinstance(concept, Neg):
        return _nnf(Atom(concept.iri), not negated)
    if isinstance(concept, Conj):
        parts = tuple(_nnf(operand, negated) for operand in concept.operands)
        return _disj(parts) if negated else _conj(parts)
    if isinstance(concept, Disj):
        parts = tuple(_nnf(operand, negated) for operand in concept.operands)
        return _conj(parts) if negated else _disj(parts)
    if isinstance(concept, Exists):
        filler = _nnf(concept.filler, negated)
        if negated:
            return _forall(concept.role, filler)
        return _exists(concept.role, filler)
    filler = _nnf(concept.filler, negated)
    if negated:
        return _exists(concept.role, filler)
    return _forall(concept.role, filler)


def _conj(operands: Sequence[Concept]) -> Concept:
    flat: List[Concept] = []
    for operand in operands:
        if operand == BOTTOM:
            return BOTTOM
        if operand == TOP:
            continue
        if isinstance(operand, Conj):
            flat.extend(operand.operands)
        else:
            flat.append(operand)
    atoms = {concept.iri for concept in flat if isinstance(concept, Atom)}
    if any(isinstance(concept, Neg) and concept.iri in atoms for concept in flat):
        return BOTTOM
    unique = _unique(flat)
    if not unique:
        return TOP
    if len(unique) == 1:
        return unique[0]
    return Conj(tuple(unique))


def _disj(operands: Sequence[Concept]) -> Concept:
    flat: List[Concept] = []
    for operand in operands:
        if operand == TOP:
            return TOP
        if operand == BOTTOM:
            continue
        if isinstance(operand, Disj):
            flat.extend(operand.operands)
        else:
            flat.append(operand)
    atoms = {concept.iri for concept in flat if isinstance(concept, Atom)}
    negated = {concept.iri for concept in flat if isinstance(concept, Neg)}
    if atoms & negated:
        return TOP
    unique = _unique(flat)
    if not unique:
        return BOTTOM
    if len(unique) == 1:
        return unique[0]
    return Disj(tuple(unique))


def _exists(role: Role, filler: Concept) -> Concept:
    if filler == BOTTOM:
        return BOTTOM
    return Exists(role, filler)


def _forall(role: Role, filler: Concept) -> Concept:
    if filler == TOP:
        return TOP
    return Forall(role, filler)


def _unique(concepts: Iterable[Concept]) -> List[Concept]:
    seen = set()
    ordered = []
    for concept in sorted(concepts, key=repr):
        if concept in seen or concept == TOP:
            continue
        seen.add(concept)
        ordered.append(concept)
    return ordered
