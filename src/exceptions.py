class ForumXPathError(Exception):
    """Base exception for all pipeline errors."""


class PageRenderError(ForumXPathError):
    """Stage 1 — page failed to render."""


class SanitizationError(ForumXPathError):
    """Stage 2 — HTML could not be sanitized."""


class IEExtractionError(ForumXPathError):
    """Stage 3 — field extraction failed."""


class CondensationError(ForumXPathError):
    """Stage 4 — HTML condensation failed."""


class XPathGenerationError(ForumXPathError):
    """Stage 5 — XPath generation failed to start."""


class XPathSyntaxError(ForumXPathError):
    """Stage 5 — generated XPath has invalid syntax."""
