from pathlib import Path

from rdflib import Graph

from hermitpy import Reasoner

graph = Graph()
graph.parse(Path(__file__).with_name("hierarchy.ttl"))
reasoner = Reasoner(graph)

print(reasoner.is_consistent())
for child, parent in reasoner.direct_subclasses():
    print(child, "subClassOf", parent)
