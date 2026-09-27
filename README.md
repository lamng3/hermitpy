# hermitpy

hermitpy is a Python reasoner for a documented fragment of OWL. It decides
consistency and builds a direct class hierarchy with a hypertableau completion
graph. It does not need a JVM.

The procedure follows the hypertableau calculus published for HermiT
(Motik, Shearer, and Horrocks, 2009). HermiT itself is copyright Oxford
University Computing Laboratory, 2008-2014, and is licensed under LGPL-3.0.
hermitpy is a separate implementation under the same license. See `NOTICE`.

## Fragment

Supported:

- named classes, `owl:Thing`, and `owl:Nothing`
- `rdfs:subClassOf`, `owl:equivalentClass`, `owl:disjointWith`, and `owl:complementOf`
- `owl:intersectionOf` and `owl:unionOf`
- `owl:someValuesFrom` and `owl:allValuesFrom` on object properties
- `owl:inverseOf`, `owl:TransitiveProperty`, and `owl:SymmetricProperty`
- `rdfs:domain` and `rdfs:range`
- class assertions and object-property assertions on named individuals

Datatype restrictions, cardinality, property chains, nominals, role hierarchies,
keys, and SWRL raise `UnsupportedConstruct`. They are not dropped.

## Install

```bash
pip install -e .
```

Requires Python 3.8 or later.

## Use

```python
from rdflib import Graph
from hermitpy import Reasoner

graph = Graph()
graph.parse("ontology.ttl")
reasoner = Reasoner(graph)
reasoner.is_consistent()
reasoner.direct_subclasses()
```

`direct_subclasses` returns pairs of IRIs. Equivalent classes appear in both
directions. Every satisfiable class with no stricter named parent is linked to
`owl:Thing`. An inconsistent ontology raises `InconsistentOntology` instead of
classifying every class as `owl:Nothing`.

The API reference is [docs/index.html](docs/index.html).
