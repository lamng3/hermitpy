# hermitpy

[Documentation](https://lamng3.github.io/hermit-docs/)

hermitpy is a Python OWL reasoner. It checks whether an ontology is consistent
and builds a direct class hierarchy for a documented fragment of OWL. Reasoning
uses a hypertableau completion graph and does not need a JVM.

The decision procedure follows Motik, Shearer, and Horrocks, "Hypertableau
Reasoning for Description Logics," Journal of Artificial Intelligence
Research, 2009. hermitpy is licensed under LGPL-3.0-or-later. See `LICENSE`
and `NOTICE`.

## Fragment

Supported:

- named classes, `owl:Thing`, and `owl:Nothing`
- `rdfs:subClassOf`, `owl:equivalentClass`, `owl:disjointWith`, and `owl:complementOf`
- `owl:intersectionOf` and `owl:unionOf`
- `owl:someValuesFrom` and `owl:allValuesFrom` on object and datatype properties
- numeric datatype restrictions (`xsd:minInclusive`, `xsd:maxInclusive`, `xsd:minExclusive`, `xsd:maxExclusive`)
- `owl:inverseOf`, `owl:TransitiveProperty`, and `owl:SymmetricProperty`
- `rdfs:domain` and `rdfs:range`
- class assertions and object-property assertions on named individuals

Cardinality, property chains, nominals, role hierarchies, keys, and SWRL raise
`UnsupportedConstruct`. They are not dropped.

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

Examples are in `examples/`.

`direct_subclasses` returns pairs of IRIs. Equivalent classes appear in both
directions. Every satisfiable class with no stricter named parent is linked to
`owl:Thing`. An inconsistent ontology raises `InconsistentOntology` instead of
classifying every class as `owl:Nothing`.

Notes on the fragment, the API, and the hypertableau are published at
<https://lamng3.github.io/hermit-docs/>.
The short API page in this repository is [docs/index.html](docs/index.html),
also served at <https://lamng3.github.io/hermitpy/>.
