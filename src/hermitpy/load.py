"""Load an rdflib graph into the supported OWL fragment."""

from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection

from .errors import UnsupportedConstruct
from .syntax import (
    OWL_NOTHING,
    OWL_THING,
    BOTTOM,
    LITERAL,
    TOP,
    Atom,
    Concept,
    Conj,
    DataExists,
    DataForall,
    DataLiteral,
    DataRange,
    Disj,
    Exists,
    Forall,
    Role,
    inclusion,
    negate,
    nnf,
)

RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#")
RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")
XSD = Namespace("http://www.w3.org/2001/XMLSchema#")
SWRL = "http://www.w3.org/2003/11/swrl#"

_KNOWN_OWL_PREDICATES = {
    OWL.onProperty,
    OWL.onDatatype,
    OWL.withRestrictions,
    OWL.someValuesFrom,
    OWL.allValuesFrom,
    OWL.intersectionOf,
    OWL.unionOf,
    OWL.complementOf,
    OWL.inverseOf,
    OWL.equivalentClass,
    OWL.disjointWith,
    OWL.versionIRI,
    OWL.versionInfo,
    OWL.priorVersion,
    OWL.backwardCompatibleWith,
    OWL.incompatibleWith,
    OWL.deprecated,
}
_EXPLICIT_UNSUPPORTED = {
    RDFS.subPropertyOf,
    OWL.equivalentProperty,
    OWL.propertyDisjointWith,
    OWL.disjointUnionOf,
    OWL.imports,
    OWL.sameAs,
    OWL.differentFrom,
}
_UNSUPPORTED_TYPES = {
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.AsymmetricProperty,
    OWL.IrreflexiveProperty,
    OWL.ReflexiveProperty,
    OWL.AllDifferent,
    OWL.AllDisjointClasses,
    OWL.AllDisjointProperties,
    OWL.NegativePropertyAssertion,
    OWL.Axiom,
}
_DECLARATIONS = _UNSUPPORTED_TYPES | {
    OWL.Class,
    OWL.Restriction,
    OWL.ObjectProperty,
    OWL.DatatypeProperty,
    OWL.AnnotationProperty,
    OWL.TransitiveProperty,
    OWL.SymmetricProperty,
    OWL.Ontology,
    OWL.NamedIndividual,
    OWL.Datatype,
    RDFS.Class,
    RDFS.Datatype,
    RDF.Property,
}
_ANNOTATION_IRIS = {
    RDFS.label,
    RDFS.comment,
    RDFS.seeAlso,
    RDFS.isDefinedBy,
    OWL.versionInfo,
    OWL.deprecated,
}
_RESERVED_NAMESPACES = (str(RDF), str(RDFS), str(OWL), str(XSD))


class Ontology:
    """TBox and ABox accepted by the tableau."""

    def __init__(self) -> None:
        self.unfold: Dict[str, Tuple[Concept, ...]] = {}
        self.gcis: Tuple[Concept, ...] = ()
        self.domains: Dict[Role, Tuple[Concept, ...]] = {}
        self.ranges: Dict[Role, Tuple[Concept, ...]] = {}
        self.transitive: Set[str] = set()
        self.symmetric: Set[str] = set()
        self.inverse_of: Dict[str, str] = {}
        self.named_classes: Set[str] = set()
        self.individuals: Dict[str, Tuple[Concept, ...]] = {}
        self.assertions: Tuple[Tuple[str, Role, str], ...] = ()

    def inverse_role(self, role: Role) -> Role:
        """Return the canonical inverse of a role."""

        if role.iri in self.symmetric and not role.inverse:
            return Role(role.iri, False)
        if role.inverse:
            return Role(role.iri, False)
        named = self.inverse_of.get(role.iri)
        if named:
            return Role(named, False)
        return Role(role.iri, True)

    def is_transitive(self, role: Role) -> bool:
        """Return whether a role or its inverse is transitive."""

        return role.iri in self.transitive

    def canonical(self, iri: str) -> Role:
        """Return a forward role, rewriting a named inverse when one exists."""

        return Role(iri, False)


def load_ontology(graph: Graph) -> Ontology:
    """Convert an RDF graph into a tableau ontology.

    Constructs outside the fragment raise ``UnsupportedConstruct`` instead of
    being dropped.
    """

    _reject_unsupported_vocabulary(graph)
    ontology = Ontology()
    annotations = set(_ANNOTATION_IRIS)
    annotations.update(graph.subjects(RDF.type, OWL.AnnotationProperty))
    _collect_roles(graph, ontology)
    _collect_axioms(graph, ontology)
    _collect_assertions(graph, ontology, annotations)
    return ontology


def _reject_unsupported_vocabulary(graph: Graph) -> None:
    for predicate, obj in graph.predicate_objects():
        predicate_iri = str(predicate)
        object_iri = str(obj)
        if predicate_iri.startswith(SWRL) or object_iri.startswith(SWRL):
            raise UnsupportedConstruct("SWRL")
        if predicate in _EXPLICIT_UNSUPPORTED:
            raise UnsupportedConstruct(_term_name(predicate))
        if (
            predicate_iri.startswith(str(OWL))
            and predicate not in _KNOWN_OWL_PREDICATES
        ):
            raise UnsupportedConstruct(_term_name(predicate))
        if obj in _UNSUPPORTED_TYPES:
            raise UnsupportedConstruct(_term_name(obj))


def _collect_roles(graph: Graph, ontology: Ontology) -> None:
    for subject in graph.subjects(RDF.type, OWL.TransitiveProperty):
        if not isinstance(subject, URIRef):
            raise UnsupportedConstruct("anonymous transitive property")
        ontology.transitive.add(str(subject))
    for subject in graph.subjects(RDF.type, OWL.SymmetricProperty):
        if not isinstance(subject, URIRef):
            raise UnsupportedConstruct("anonymous symmetric property")
        ontology.symmetric.add(str(subject))
    for left, right in graph.subject_objects(OWL.inverseOf):
        if isinstance(left, URIRef) and isinstance(right, URIRef):
            _record_inverse(ontology, str(left), str(right))
    changed = True
    while changed:
        changed = False
        for left, right in list(ontology.inverse_of.items()):
            if left in ontology.transitive and right not in ontology.transitive:
                ontology.transitive.add(right)
                changed = True
            elif right in ontology.transitive and left not in ontology.transitive:
                ontology.transitive.add(left)
                changed = True


def _record_inverse(ontology: Ontology, left: str, right: str) -> None:
    if left == right:
        ontology.symmetric.add(left)
        return
    existing = ontology.inverse_of.get(left)
    if existing is not None and existing != right:
        raise UnsupportedConstruct("conflicting owl:inverseOf for {}".format(left))
    ontology.inverse_of[left] = right
    ontology.inverse_of[right] = left


def _collect_axioms(graph: Graph, ontology: Ontology) -> None:
    properties = _property_iris(graph, ontology)
    unfold: Dict[str, List[Concept]] = {}
    gcis: List[Concept] = []
    domains: Dict[Role, List[Concept]] = {}
    ranges: Dict[Role, List[Concept]] = {}
    parser = _ClassParser(graph, ontology)

    def add_inclusion(lhs: Concept, rhs: Concept) -> None:
        if isinstance(lhs, Atom) and lhs.iri not in (OWL_THING, OWL_NOTHING):
            consequence = nnf(rhs)
            if consequence != TOP:
                bucket = unfold.setdefault(lhs.iri, [])
                if consequence not in bucket:
                    bucket.append(consequence)
            return
        if lhs == BOTTOM:
            return
        gci = inclusion(lhs, rhs)
        if gci != TOP and gci not in gcis:
            gcis.append(gci)

    def add_domain(role: Role, concept: Concept) -> None:
        _append(domains, role, concept)
        _append(ranges, ontology.inverse_role(role), concept)

    def add_range(role: Role, concept: Concept) -> None:
        _append(ranges, role, concept)
        _append(domains, ontology.inverse_role(role), concept)

    for subject, obj in graph.subject_objects(RDFS.subClassOf):
        add_inclusion(parser.parse(subject), parser.parse(obj))
    for subject, obj in graph.subject_objects(OWL.equivalentClass):
        if subject in properties and obj in properties:
            raise UnsupportedConstruct("owl:equivalentClass on properties")
        left = parser.parse(subject)
        right = parser.parse(obj)
        add_inclusion(left, right)
        add_inclusion(right, left)
    for subject, obj in graph.subject_objects(OWL.disjointWith):
        if subject in properties or obj in properties:
            raise UnsupportedConstruct("owl:disjointWith on properties")
        left = parser.parse(subject)
        right = parser.parse(obj)
        add_inclusion(left, negate(right))
        add_inclusion(right, negate(left))
    data_properties = {
        subject
        for subject in graph.subjects(RDF.type, OWL.DatatypeProperty)
        if isinstance(subject, URIRef)
    }
    for prop, obj in graph.subject_objects(RDFS.domain):
        if _is_annotation(graph, prop):
            continue
        if not isinstance(prop, URIRef):
            raise UnsupportedConstruct("anonymous rdfs:domain")
        if prop in data_properties:
            add_inclusion(DataExists(str(prop), LITERAL), parser.parse(obj))
            continue
        add_domain(ontology.canonical(str(prop)), parser.parse(obj))
    for prop, obj in graph.subject_objects(RDFS.range):
        if _is_annotation(graph, prop):
            continue
        if not isinstance(prop, URIRef):
            raise UnsupportedConstruct("anonymous rdfs:range")
        if parser.is_data_range(obj):
            add_inclusion(TOP, DataForall(str(prop), parser.parse_data_range(obj)))
            continue
        add_range(ontology.canonical(str(prop)), parser.parse(obj))
    for subject in graph.subjects(RDF.type, OWL.Class):
        if isinstance(subject, URIRef) and str(subject) not in (OWL_THING, OWL_NOTHING):
            ontology.named_classes.add(str(subject))

    ontology.unfold = {iri: tuple(concepts) for iri, concepts in unfold.items()}
    ontology.gcis = tuple(gcis)
    ontology.domains = {role: tuple(concepts) for role, concepts in domains.items()}
    ontology.ranges = {role: tuple(concepts) for role, concepts in ranges.items()}


def _append(buckets: Dict[Role, List[Concept]], role: Role, concept: Concept) -> None:
    bucket = buckets.setdefault(role, [])
    if concept not in bucket:
        bucket.append(concept)


def _property_iris(graph: Graph, ontology: Ontology) -> Set[URIRef]:
    properties = {URIRef(iri) for iri in ontology.inverse_of}
    properties.update(URIRef(iri) for iri in ontology.transitive)
    properties.update(URIRef(iri) for iri in ontology.symmetric)
    for predicate in (OWL.ObjectProperty, OWL.TransitiveProperty, OWL.SymmetricProperty):
        for subject in graph.subjects(RDF.type, predicate):
            if isinstance(subject, URIRef):
                properties.add(subject)
    for obj in graph.objects(None, OWL.onProperty):
        if isinstance(obj, URIRef):
            properties.add(obj)
    return properties


def _collect_assertions(graph: Graph, ontology: Ontology, annotations: set) -> None:
    concepts: Dict[str, List[Concept]] = {}
    assertions: List[Tuple[str, Role, str]] = []
    parser = _ClassParser(graph, ontology)

    def individual(node: URIRef) -> str:
        iri = str(node)
        concepts.setdefault(iri, [])
        return iri

    for subject, obj in graph.subject_objects(RDF.type):
        if obj in _DECLARATIONS:
            continue
        if isinstance(subject, BNode):
            raise UnsupportedConstruct("anonymous individual")
        if not isinstance(subject, URIRef):
            raise UnsupportedConstruct("individual")
        concept = parser.parse(obj)
        bucket = concepts.setdefault(str(subject), [])
        if concept not in bucket:
            bucket.append(concept)

    for subject, predicate, obj in graph:
        if _is_reserved(predicate) or predicate in annotations:
            continue
        if isinstance(obj, Literal):
            if not isinstance(subject, URIRef):
                raise UnsupportedConstruct("literal assertion")
            iri = individual(subject)
            filler = _literal_range(obj)
            fact = DataLiteral(str(predicate), filler)
            bucket = concepts.setdefault(iri, [])
            if fact not in bucket:
                bucket.append(fact)
            continue
        if isinstance(subject, BNode) or isinstance(obj, BNode):
            raise UnsupportedConstruct("anonymous individual")
        if not isinstance(subject, URIRef) or not isinstance(obj, URIRef):
            raise UnsupportedConstruct("object property assertion")
        assertions.append(
            (individual(subject), ontology.canonical(str(predicate)), individual(obj))
        )

    ontology.individuals = {
        iri: tuple(bucket) for iri, bucket in sorted(concepts.items())
    }
    ontology.assertions = tuple(assertions)


class _ClassParser:
    """Parse class expressions, rejecting constructs outside the fragment."""

    def __init__(self, graph: Graph, ontology: Ontology) -> None:
        self.graph = graph
        self.ontology = ontology
        self._stack: Set[BNode] = set()

    def parse(self, node) -> Concept:
        if isinstance(node, Literal):
            raise UnsupportedConstruct("literal class expression")
        if isinstance(node, URIRef):
            iri = str(node)
            if iri.startswith(str(XSD)) or iri in {
                str(RDFS.Literal),
                str(OWL.real),
                str(OWL.rational),
            }:
                raise UnsupportedConstruct("datatype {}".format(iri))
            if (node, RDF.type, RDFS.Datatype) in self.graph or (
                node,
                RDF.type,
                OWL.Datatype,
            ) in self.graph:
                raise UnsupportedConstruct("datatype {}".format(iri))
            if iri not in (OWL_THING, OWL_NOTHING):
                self.ontology.named_classes.add(iri)
            return nnf(Atom(iri))
        if not isinstance(node, BNode):
            raise UnsupportedConstruct("class expression")
        if node in self._stack:
            raise UnsupportedConstruct("cyclic class expression")
        self._stack.add(node)
        try:
            return self._parse_bnode(node)
        finally:
            self._stack.remove(node)

    def _parse_bnode(self, node: BNode) -> Concept:
        complement = self.graph.value(node, OWL.complementOf)
        if complement is not None:
            return negate(self.parse(complement))
        intersection = self.graph.value(node, OWL.intersectionOf)
        if intersection is not None:
            return nnf(_conjunction(self._members(intersection)))
        union = self.graph.value(node, OWL.unionOf)
        if union is not None:
            return nnf(_disjunction(self._members(union)))
        on_property = self.graph.value(node, OWL.onProperty)
        if on_property is not None or (node, RDF.type, OWL.Restriction) in self.graph:
            return self._parse_restriction(node, on_property)
        raise UnsupportedConstruct("class expression")

    def _parse_restriction(self, node: BNode, on_property) -> Concept:
        if on_property is None:
            raise UnsupportedConstruct("owl:Restriction without owl:onProperty")
        role = self._parse_role(on_property)
        some = self.graph.value(node, OWL.someValuesFrom)
        every = self.graph.value(node, OWL.allValuesFrom)
        if some is not None and every is not None:
            raise UnsupportedConstruct(
                "restriction with both someValuesFrom and allValuesFrom"
            )
        if some is not None:
            if self.is_data_range(some):
                self._require_forward_data_role(role)
                return nnf(DataExists(role.iri, self.parse_data_range(some)))
            return nnf(Exists(role, self.parse(some)))
        if every is not None:
            if self.is_data_range(every):
                self._require_forward_data_role(role)
                return nnf(DataForall(role.iri, self.parse_data_range(every)))
            return nnf(Forall(role, self.parse(every)))
        raise UnsupportedConstruct("owl:Restriction")

    def _require_forward_data_role(self, role: Role) -> None:
        if role.inverse:
            raise UnsupportedConstruct("datatype restriction on an inverse property")

    def is_data_range(self, node) -> bool:
        if isinstance(node, URIRef):
            return _xsd_range(str(node)) is not None
        if isinstance(node, BNode):
            return self.graph.value(node, OWL.onDatatype) is not None or (
                node,
                RDF.type,
                RDFS.Datatype,
            ) in self.graph
        return False

    def parse_data_range(self, node) -> DataRange:
        if isinstance(node, URIRef):
            found = _xsd_range(str(node))
            if found is None:
                raise UnsupportedConstruct("datatype {}".format(node))
            return found
        if not isinstance(node, BNode):
            raise UnsupportedConstruct("datatype")
        base = self.graph.value(node, OWL.onDatatype)
        if not isinstance(base, URIRef):
            raise UnsupportedConstruct("datatype restriction")
        data_range = _xsd_range(str(base))
        if data_range is None:
            raise UnsupportedConstruct("datatype {}".format(base))
        facets = self.graph.value(node, OWL.withRestrictions)
        if facets is None:
            return data_range
        try:
            members = list(Collection(self.graph, facets))
        except (ValueError, TypeError) as error:
            raise UnsupportedConstruct("datatype restriction") from error
        for facet in members:
            data_range = _apply_facet(self.graph, data_range, facet)
        if data_range.empty():
            return data_range
        return data_range

    def _parse_role(self, node) -> Role:
        if isinstance(node, URIRef):
            return self.ontology.canonical(str(node))
        if isinstance(node, BNode):
            inverse = self.graph.value(node, OWL.inverseOf)
            if isinstance(inverse, URIRef):
                return self.ontology.inverse_role(self.ontology.canonical(str(inverse)))
        raise UnsupportedConstruct("object property expression")

    def _members(self, node) -> Tuple[Concept, ...]:
        try:
            return tuple(self.parse(member) for member in Collection(self.graph, node))
        except (ValueError, TypeError) as error:
            raise UnsupportedConstruct("RDF list") from error


def _conjunction(members: Tuple[Concept, ...]) -> Concept:
    if not members:
        return TOP
    if len(members) == 1:
        return members[0]
    return Conj(members)


def _disjunction(members: Tuple[Concept, ...]) -> Concept:
    if not members:
        return BOTTOM
    if len(members) == 1:
        return members[0]
    return Disj(members)


def _is_annotation(graph: Graph, prop) -> bool:
    return prop in _ANNOTATION_IRIS or (prop, RDF.type, OWL.AnnotationProperty) in graph


def _is_reserved(predicate) -> bool:
    iri = str(predicate)
    return any(iri.startswith(namespace) for namespace in _RESERVED_NAMESPACES)


_XSD_RANGES = {
    "integer": DataRange("numeric", integer_only=True),
    "int": DataRange("numeric", integer_only=True),
    "long": DataRange("numeric", integer_only=True),
    "short": DataRange("numeric", integer_only=True),
    "nonNegativeInteger": DataRange("numeric", Decimal(0), integer_only=True),
    "positiveInteger": DataRange("numeric", Decimal(1), integer_only=True),
    "nonPositiveInteger": DataRange(
        "numeric", upper=Decimal(0), integer_only=True
    ),
    "negativeInteger": DataRange(
        "numeric", upper=Decimal(-1), integer_only=True
    ),
    "decimal": DataRange("numeric"),
    "double": DataRange("numeric"),
    "float": DataRange("numeric"),
    "string": DataRange("string"),
    "anyURI": DataRange("string"),
    "date": DataRange("string"),
    "dateTime": DataRange("string"),
    "boolean": DataRange("boolean"),
}


def _xsd_range(iri: str) -> Optional[DataRange]:
    if iri == str(RDFS.Literal):
        return DataRange("literal")
    if iri in (str(OWL.real), str(OWL.rational)):
        return DataRange("numeric")
    if not iri.startswith(str(XSD)):
        return None
    return _XSD_RANGES.get(iri[len(str(XSD)) :])


def _apply_facet(graph: Graph, data_range: DataRange, facet) -> DataRange:
    if not isinstance(facet, BNode):
        raise UnsupportedConstruct("datatype facet")
    updated = data_range
    found = False
    for predicate, value in graph.predicate_objects(facet):
        name = str(predicate)[len(str(XSD)) :] if str(predicate).startswith(str(XSD)) else ""
        if name not in {"minInclusive", "minExclusive", "maxInclusive", "maxExclusive"}:
            raise UnsupportedConstruct("datatype facet {}".format(_term_name(predicate)))
        if not isinstance(value, Literal):
            raise UnsupportedConstruct("datatype facet")
        found = True
        number = Decimal(str(value))
        inclusive = name.endswith("Inclusive")
        if name.startswith("min"):
            updated = _set_lower(updated, number, inclusive)
        else:
            updated = _set_upper(updated, number, inclusive)
    if not found:
        raise UnsupportedConstruct("datatype facet")
    return updated


def _set_lower(data_range: DataRange, number: Decimal, inclusive: bool) -> DataRange:
    lower, lower_inclusive = data_range.lower, data_range.lower_inclusive
    if lower is None or number > lower:
        lower, lower_inclusive = number, inclusive
    elif number == lower:
        lower_inclusive = lower_inclusive and inclusive
    return DataRange(
        data_range.kind,
        lower,
        data_range.upper,
        lower_inclusive,
        data_range.upper_inclusive,
        data_range.integer_only,
        data_range.complemented,
    )


def _set_upper(data_range: DataRange, number: Decimal, inclusive: bool) -> DataRange:
    upper, upper_inclusive = data_range.upper, data_range.upper_inclusive
    if upper is None or number < upper:
        upper, upper_inclusive = number, inclusive
    elif number == upper:
        upper_inclusive = upper_inclusive and inclusive
    return DataRange(
        data_range.kind,
        data_range.lower,
        upper,
        data_range.lower_inclusive,
        upper_inclusive,
        data_range.integer_only,
        data_range.complemented,
    )


def _literal_range(literal: Literal) -> DataRange:
    datatype = str(literal.datatype) if literal.datatype is not None else str(XSD.string)
    base = _xsd_range(datatype)
    if base is None:
        raise UnsupportedConstruct("literal datatype {}".format(datatype))
    if base.kind == "numeric":
        number = Decimal(str(literal))
        return DataRange("numeric", number, number, True, True, base.integer_only)
    return DataRange(base.kind)


def _term_name(term) -> str:
    text = str(term)
    for namespace, prefix in (
        (str(OWL), "owl:"),
        (str(RDFS), "rdfs:"),
        (str(RDF), "rdf:"),
    ):
        if text.startswith(namespace):
            return prefix + text[len(namespace) :]
    return text
