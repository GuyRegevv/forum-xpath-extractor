import copy
import logging
from lxml import html as lxml_html, etree
from src.exceptions import SanitizationError

logger = logging.getLogger(__name__)

REMOVE_TAGS = {
    "script", "style", "svg", "img", "link", "meta",
    "noscript", "head", "iframe", "canvas", "video", "audio",
    "input", "button", "form", "select", "textarea",
}

STRUCTURAL_CONTAINERS = {
    "div", "section", "article", "ul", "ol", "li", "table",
    "thead", "tbody", "tfoot", "tr", "th", "td", "dl", "dt", "dd",
    "figure", "figcaption", "header", "footer", "main", "nav", "aside",
    "html", "body",
}


def _get_tag(node) -> str:
    tag = node.tag
    if isinstance(tag, str) and "{" in tag:
        return tag.split("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def sanitize_html(raw_html: str) -> str:
    """
    Strip a rendered HTML page down to structural skeleton + text content.
    Implements Algorithm 1 from XPath Agent (2025).

    Args:
        raw_html: Full rendered HTML string from Stage 1

    Returns:
        Sanitized HTML string — same tree structure, no attributes, no noise.
        Typically 10-20% the size of the input.

    Raises:
        SanitizationError: If the HTML cannot be parsed or the result is empty
    """
    tree = lxml_html.fromstring(raw_html.encode("utf-8"))

    # Pass 1: depth-first traversal → left_stack; right_stack is reversed (bottom-up)
    left_stack = list(tree.iter())
    right_stack = list(reversed(left_stack))

    # Pass 2: bottom-up — children are processed before their parents
    for node in right_stack:
        if callable(node.tag):  # comment or processing instruction
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
            continue

        tag = _get_tag(node)
        if tag in REMOVE_TAGS:
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

    return etree.tostring(tree, encoding="unicode", method="html")
