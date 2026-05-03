import pytest
from src.exceptions import (
    ForumXPathError,
    PageRenderError,
    SanitizationError,
    IEExtractionError,
    CondensationError,
    XPathGenerationError,
    XPathSyntaxError,
)


def test_exception_hierarchy():
    assert issubclass(ForumXPathError, Exception)
    assert issubclass(PageRenderError, ForumXPathError)
    assert issubclass(SanitizationError, ForumXPathError)
    assert issubclass(IEExtractionError, ForumXPathError)
    assert issubclass(CondensationError, ForumXPathError)
    assert issubclass(XPathGenerationError, ForumXPathError)
    assert issubclass(XPathSyntaxError, ForumXPathError)


def test_base_exception_catches_all_pipeline_errors():
    for exc_class in [
        PageRenderError, SanitizationError, IEExtractionError,
        CondensationError, XPathGenerationError, XPathSyntaxError,
    ]:
        with pytest.raises(ForumXPathError):
            raise exc_class("test")


def test_exceptions_carry_message():
    exc = PageRenderError("HTTP 404 for https://example.com")
    assert "404" in str(exc)
    assert "https://example.com" in str(exc)
