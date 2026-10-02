"""Tests for the supported OWL fragment."""

import unittest

from rdflib import Graph

from hermitpy import InconsistentOntology, Reasoner, UnsupportedConstruct

EX = "https://example.org/"
THING = "http://www.w3.org/2002/07/owl#Thing"
NOTHING = "http://www.w3.org/2002/07/owl#Nothing"

PREAMBLE = """\
@prefix ex: <https://example.org/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
"""


def reasoner(body: str) -> Reasoner:
    graph = Graph()
    graph.parse(data=PREAMBLE + body, format="turtle")
    return Reasoner(graph)


def iri(local: str) -> str:
    return EX + local


class HierarchyTests(unittest.TestCase):
    def test_direct_subclass_skips_the_transitive_parent(self):
        classified = reasoner(
            """
            ex:Dog rdfs:subClassOf ex:Animal .
            ex:Animal rdfs:subClassOf ex:Organism .
            """
        )
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.unsatisfiable_classes(), [])
        self.assertEqual(
            classified.direct_subclasses(),
            [
                (iri("Animal"), iri("Organism")),
                (iri("Dog"), iri("Animal")),
                (iri("Organism"), THING),
            ],
        )

    def test_equivalence_is_mutual_and_shares_parents(self):
        classified = reasoner(
            """
            ex:Dog owl:equivalentClass ex:Canine .
            ex:Canine rdfs:subClassOf ex:Animal .
            """
        )
        pairs = classified.direct_subclasses()
        self.assertIn((iri("Dog"), iri("Canine")), pairs)
        self.assertIn((iri("Canine"), iri("Dog")), pairs)
        self.assertIn((iri("Dog"), iri("Animal")), pairs)
        self.assertIn((iri("Canine"), iri("Animal")), pairs)
        self.assertNotIn((iri("Dog"), THING), pairs)

    def test_disjoint_individual_is_inconsistent(self):
        classified = reasoner(
            """
            ex:Dog owl:disjointWith ex:Cat .
            ex:fido a ex:Dog, ex:Cat .
            """
        )
        self.assertFalse(classified.is_consistent())
        with self.assertRaises(InconsistentOntology):
            classified.direct_subclasses()

    def test_unsatisfiable_class_does_not_make_the_ontology_inconsistent(self):
        classified = reasoner(
            """
            ex:Unicorn rdfs:subClassOf ex:Horse, ex:NotHorse .
            ex:Horse owl:disjointWith ex:NotHorse .
            """
        )
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.unsatisfiable_classes(), [iri("Unicorn")])
        self.assertIn((iri("Unicorn"), NOTHING), classified.direct_subclasses())

    def test_union_subclass_follows_both_branches(self):
        classified = reasoner(
            """
            ex:Pet rdfs:subClassOf [ owl:unionOf ( ex:Cat ex:Dog ) ] .
            ex:Cat rdfs:subClassOf ex:Mammal .
            ex:Dog rdfs:subClassOf ex:Mammal .
            ex:Cat owl:disjointWith ex:Dog .
            """
        )
        self.assertIn((iri("Pet"), iri("Mammal")), classified.direct_subclasses())
        self.assertNotIn((iri("Pet"), iri("Cat")), classified.direct_subclasses())

    def test_intersection_on_the_left_is_a_general_inclusion(self):
        classified = reasoner(
            """
            ex:Dog rdfs:subClassOf ex:Mammal, ex:Pet .
            [ owl:intersectionOf ( ex:Mammal ex:Pet ) ]
                rdfs:subClassOf ex:HouseAnimal .
            """
        )
        self.assertIn(
            (iri("Dog"), iri("HouseAnimal")), classified.direct_subclasses()
        )

    def test_complement_makes_a_class_assertion_inconsistent(self):
        classified = reasoner(
            """
            ex:Dog rdfs:subClassOf [ owl:complementOf ex:Cat ] .
            ex:fido a ex:Dog, ex:Cat .
            """
        )
        self.assertFalse(classified.is_consistent())


class RoleTests(unittest.TestCase):
    def test_existential_and_universal_restrictions_clash(self):
        classified = reasoner(
            """
            ex:Dog owl:disjointWith ex:Human .
            ex:john a [
                a owl:Restriction ;
                owl:onProperty ex:hasChild ;
                owl:someValuesFrom ex:Dog
            ] .
            ex:john a [
                a owl:Restriction ;
                owl:onProperty ex:hasChild ;
                owl:allValuesFrom ex:Human
            ] .
            """
        )
        self.assertFalse(classified.is_consistent())

    def test_transitive_property_propagates_a_universal_restriction(self):
        classified = reasoner(
            """
            ex:partOf a owl:ObjectProperty, owl:TransitiveProperty .
            ex:Container rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:partOf ;
                owl:allValuesFrom ex:Located
            ] .
            ex:Located owl:disjointWith ex:Elsewhere .
            ex:a a ex:Container ;
                ex:partOf ex:b .
            ex:b ex:partOf ex:c .
            ex:c a ex:Elsewhere .
            """
        )
        self.assertFalse(classified.is_consistent())

    def test_nontransitive_property_does_not_propagate(self):
        classified = reasoner(
            """
            ex:partOf a owl:ObjectProperty .
            ex:Container rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:partOf ;
                owl:allValuesFrom ex:Located
            ] .
            ex:Located owl:disjointWith ex:Elsewhere .
            ex:a a ex:Container ;
                ex:partOf ex:b .
            ex:b ex:partOf ex:c .
            ex:c a ex:Elsewhere .
            """
        )
        self.assertTrue(classified.is_consistent())

    def test_inverse_role_sees_the_parent(self):
        classified = reasoner(
            """
            ex:hasChild owl:inverseOf ex:hasParent .
            ex:Happy owl:disjointWith ex:Parent .
            ex:Parent rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:hasChild ;
                owl:someValuesFrom [
                    a owl:Restriction ;
                    owl:onProperty ex:hasParent ;
                    owl:allValuesFrom ex:Happy
                ]
            ] .
            ex:john a ex:Parent .
            """
        )
        self.assertFalse(classified.is_consistent())

    def test_domain_applies_to_the_assertion_subject(self):
        classified = reasoner(
            """
            ex:hasChild rdfs:domain ex:Parent .
            ex:Happy owl:disjointWith ex:Parent .
            ex:john ex:hasChild ex:mary ;
                a ex:Happy .
            """
        )
        self.assertFalse(classified.is_consistent())

    def test_symmetric_property_is_bidirectional(self):
        classified = reasoner(
            """
            ex:married a owl:ObjectProperty, owl:SymmetricProperty .
            ex:Person rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:married ;
                owl:allValuesFrom ex:Happy
            ] .
            ex:Happy owl:disjointWith ex:Unhappy .
            ex:a ex:married ex:b .
            ex:b a ex:Person .
            ex:a a ex:Unhappy .
            """
        )
        self.assertFalse(classified.is_consistent())

    def test_existential_cycle_terminates_and_is_satisfiable(self):
        classified = reasoner(
            """
            ex:Person rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:hasParent ;
                owl:someValuesFrom ex:Person
            ] .
            """
        )
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.unsatisfiable_classes(), [])


class RejectionTests(unittest.TestCase):
    def test_cardinality_is_rejected(self):
        with self.assertRaises(UnsupportedConstruct) as raised:
            reasoner(
                """
                ex:C rdfs:subClassOf [
                    a owl:Restriction ;
                    owl:onProperty ex:p ;
                    owl:maxCardinality 1
                ] .
                """
            )
        self.assertIn("maxCardinality", str(raised.exception))

    def test_nominals_are_rejected(self):
        with self.assertRaises(UnsupportedConstruct) as raised:
            reasoner("ex:C owl:oneOf ( ex:a ex:b ) .")
        self.assertIn("oneOf", str(raised.exception))

    def test_datatype_restriction_matches_a_satisfiable_class(self):
        classified = reasoner(
            """
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:age a owl:DatatypeProperty .
            ex:Adult rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:age ;
                owl:someValuesFrom [
                    a rdfs:Datatype ;
                    owl:onDatatype xsd:integer ;
                    owl:withRestrictions ( [ xsd:minInclusive 18 ] )
                ]
            ] .
            """
        )
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.unsatisfiable_classes(), [])
        self.assertIn((iri("Adult"), THING), classified.direct_subclasses())

    def test_disjoint_numeric_bounds_make_the_class_unsatisfiable(self):
        classified = reasoner(
            """
            @prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
            ex:age a owl:DatatypeProperty .
            ex:Adult rdfs:subClassOf [
                a owl:Restriction ;
                owl:onProperty ex:age ;
                owl:someValuesFrom [
                    a rdfs:Datatype ;
                    owl:onDatatype xsd:integer ;
                    owl:withRestrictions ( [ xsd:minInclusive 18 ] )
                ]
            ] , [
                a owl:Restriction ;
                owl:onProperty ex:age ;
                owl:allValuesFrom [
                    a rdfs:Datatype ;
                    owl:onDatatype xsd:integer ;
                    owl:withRestrictions ( [ xsd:maxInclusive 10 ] )
                ]
            ] .
            """
        )
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.unsatisfiable_classes(), [iri("Adult")])
        self.assertIn((iri("Adult"), NOTHING), classified.direct_subclasses())

    def test_labels_are_ignored(self):
        classified = reasoner('ex:Dog rdfs:label "Dog" ; rdfs:subClassOf ex:Animal .')
        self.assertIn((iri("Dog"), iri("Animal")), classified.direct_subclasses())

    def test_empty_graph_is_consistent(self):
        classified = reasoner("")
        self.assertTrue(classified.is_consistent())
        self.assertEqual(classified.direct_subclasses(), [])


if __name__ == "__main__":
    unittest.main()
