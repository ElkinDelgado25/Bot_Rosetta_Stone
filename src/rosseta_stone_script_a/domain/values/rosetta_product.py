from enum import Enum


class RosettaProduct(str, Enum):
    """Which Rosetta Stone product an account lands on after login.

    Foundations covers A1/A2; Fluency Builder is the newer product (e.g. B1),
    served from ``learn.rosettastone.com`` with a different backend and content
    model. See docs/FLUENCY_BUILDER.md.
    """

    FOUNDATIONS = "foundations"
    FLUENCY_BUILDER = "fluency_builder"
    EXAM = "exam"
    UNKNOWN = "unknown"
