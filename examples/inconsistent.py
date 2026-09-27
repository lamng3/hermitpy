from pathlib import Path

from rdflib import Graph

from hermitpy import Reasoner

graph = Graph()
graph.parse(Path(__file__).with_name("inconsistent.ttl"))
print(Reasoner(graph).is_consistent())
