class AnalysisUnavailableError(RuntimeError):
    """The reasoning service could not produce a usable structured answer.

    Raised instead of ever fabricating an answer. Its message must stay
    generic: provider response bodies can echo prompt (evidence) text.
    """
