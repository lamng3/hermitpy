"""Errors raised by the hypertableau reasoner."""


class UnsupportedConstruct(ValueError):
    """Raised when an ontology uses OWL outside the supported fragment."""

    def __init__(self, construct: str) -> None:
        self.construct = construct
        super().__init__(
            "Unsupported OWL construct: {}. hermitpy does not ignore "
            "constructs outside its fragment.".format(construct)
        )


class InconsistentOntology(ValueError):
    """Raised when classification is requested for an inconsistent ontology."""


class ReasonerLimitExceeded(RuntimeError):
    """Raised when tableau search exceeds its safety bound."""
