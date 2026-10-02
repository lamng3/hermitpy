"""OWL class and role expressions in negation normal form."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from math import ceil, floor
from typing import Iterable, List, Optional, Sequence, Union

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


@dataclass(frozen=True)
class DataRange:
    """A literal range HermiT can compare by bounds and datatype family."""

    kind: str
    lower: Optional[Decimal] = None
    upper: Optional[Decimal] = None
    lower_inclusive: bool = True
    upper_inclusive: bool = True
    integer_only: bool = False
    complemented: bool = False

    def complement(self) -> "DataRange":
        return DataRange(
            self.kind,
            self.lower,
            self.upper,
            self.lower_inclusive,
            self.upper_inclusive,
            self.integer_only,
            not self.complemented,
        )

    def empty(self) -> bool:
        if self.complemented:
            return self.kind == "literal" and self.lower is None and self.upper is None
        if self.integer_only:
            least = _least_integer(self.lower, self.lower_inclusive)
            greatest = _greatest_integer(self.upper, self.upper_inclusive)
            if least is not None and greatest is not None and least > greatest:
                return True
            return False
        if self.lower is None or self.upper is None:
            return False
        if self.lower > self.upper:
            return True
        if self.lower == self.upper and not (
            self.lower_inclusive and self.upper_inclusive
        ):
            return True
        return False


@dataclass(frozen=True)
class DataExists:
    """Existential restriction on a datatype property."""

    role: str
    filler: DataRange


@dataclass(frozen=True)
class DataForall:
    """Universal restriction on a datatype property."""

    role: str
    filler: DataRange


@dataclass(frozen=True)
class DataLiteral:
    """One asserted literal on a datatype property."""

    role: str
    filler: DataRange


Concept = Union[
    Atom, Neg, Conj, Disj, Exists, Forall, DataExists, DataForall, DataLiteral
]

LITERAL = DataRange("literal")

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
    if isinstance(concept, Forall):
        filler = _nnf(concept.filler, negated)
        if negated:
            return _exists(concept.role, filler)
        return _forall(concept.role, filler)
    if isinstance(concept, DataExists):
        filler = concept.filler.complement() if negated else concept.filler
        if negated:
            return _data_forall(concept.role, filler)
        return _data_exists(concept.role, filler)
    if isinstance(concept, DataForall):
        filler = concept.filler.complement() if negated else concept.filler
        if negated:
            return _data_exists(concept.role, filler)
        return _data_forall(concept.role, filler)
    return concept


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


def _data_exists(role: str, filler: DataRange) -> Concept:
    if filler.empty():
        return BOTTOM
    return DataExists(role, filler)


def _data_forall(role: str, filler: DataRange) -> Concept:
    if filler.kind == "literal" and not filler.complemented and filler.lower is None:
        return TOP
    return DataForall(role, filler)


def data_allows(needed: DataRange, constraints: Sequence[DataRange]) -> bool:
    """Return whether some value in ``needed`` satisfies every constraint."""

    if needed.empty():
        return False
    current: Optional[DataRange] = needed
    for item in constraints:
        if current is None:
            return False
        if item.complemented:
            blocked = item.complement()
            if _positive_subset(current, blocked):
                return False
            continue
        current = _positive_intersect(current, item)
    return current is not None


def _positive_intersect(left: DataRange, right: DataRange) -> Optional[DataRange]:
    if left.kind != right.kind and "literal" not in (left.kind, right.kind):
        return None
    if left.kind == "literal":
        kind = right.kind
    elif right.kind == "literal":
        kind = left.kind
    else:
        kind = left.kind
    lower, lower_inclusive = _tighter_lower(left, right)
    upper, upper_inclusive = _tighter_upper(left, right)
    combined = DataRange(
        kind,
        lower,
        upper,
        lower_inclusive,
        upper_inclusive,
        left.integer_only or right.integer_only,
    )
    if combined.empty():
        return None
    return combined


def _positive_subset(inner: DataRange, outer: DataRange) -> bool:
    if inner.empty():
        return True
    if outer.kind == "literal" and outer.lower is None and outer.upper is None:
        return True
    if inner.kind != outer.kind:
        return False
    if outer.integer_only and not inner.integer_only:
        return False
    return _bound_inside(inner, outer)


def _tighter_lower(left: DataRange, right: DataRange):
    if left.lower is None:
        return right.lower, right.lower_inclusive
    if right.lower is None:
        return left.lower, left.lower_inclusive
    if left.lower > right.lower:
        return left.lower, left.lower_inclusive
    if right.lower > left.lower:
        return right.lower, right.lower_inclusive
    return left.lower, left.lower_inclusive and right.lower_inclusive


def _tighter_upper(left: DataRange, right: DataRange):
    if left.upper is None:
        return right.upper, right.upper_inclusive
    if right.upper is None:
        return left.upper, left.upper_inclusive
    if left.upper < right.upper:
        return left.upper, left.upper_inclusive
    if right.upper < left.upper:
        return right.upper, right.upper_inclusive
    return left.upper, left.upper_inclusive and right.upper_inclusive


def _bound_inside(inner: DataRange, outer: DataRange) -> bool:
    if outer.lower is not None:
        if inner.lower is None:
            return False
        if inner.lower < outer.lower:
            return False
        if inner.lower == outer.lower and inner.lower_inclusive and not outer.lower_inclusive:
            return False
    if outer.upper is not None:
        if inner.upper is None:
            return False
        if inner.upper > outer.upper:
            return False
        if inner.upper == outer.upper and inner.upper_inclusive and not outer.upper_inclusive:
            return False
    return True


def _least_integer(lower: Optional[Decimal], inclusive: bool) -> Optional[int]:
    if lower is None:
        return None
    number = ceil(lower)
    if not inclusive and Decimal(number) == lower:
        number += 1
    return number


def _greatest_integer(upper: Optional[Decimal], inclusive: bool) -> Optional[int]:
    if upper is None:
        return None
    number = floor(upper)
    if not inclusive and Decimal(number) == upper:
        number -= 1
    return number


def _unique(concepts: Iterable[Concept]) -> List[Concept]:
    seen = set()
    ordered = []
    for concept in sorted(concepts, key=repr):
        if concept in seen or concept == TOP:
            continue
        seen.add(concept)
        ordered.append(concept)
    return ordered
