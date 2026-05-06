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


def _get_tag(node: etree._Element) -> str:
    tag = node.tag
    if isinstance(tag, str) and "{" in tag:
        return tag.split("}", 1)[1]
    return tag if isinstance(tag, str) else ""


def _is_invisible(node: etree._Element) -> bool:
    tag = _get_tag(node)
    if tag in STRUCTURAL_CONTAINERS:
        return False
    has_text = bool(node.text and node.text.strip())
    has_children = len(node) > 0
    return not has_text and not has_children


def _remove_preserving_tail(node: etree._Element) -> None:
    parent = node.getparent()
    if parent is None:
        return
    tail = node.tail
    if tail and tail.strip():
        prev = node.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(node)


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
    if not raw_html or not raw_html.strip():
        raise SanitizationError("Input HTML is empty")

    try:
        tree = lxml_html.fromstring(raw_html.encode("utf-8"))
    except Exception as exc:
        raise SanitizationError(f"Failed to parse HTML: {exc}") from exc

    tree = copy.deepcopy(tree)

    # Pass 1: depth-first traversal; reversed for bottom-up processing in Pass 2
    right_stack = list(reversed(list(tree.iter())))

    # Pass 2: bottom-up — children are processed before their parents
    for node in right_stack:
        if callable(node.tag):  # comment or processing instruction
            _remove_preserving_tail(node)
            continue

        tag = _get_tag(node)
        if tag in REMOVE_TAGS:
            _remove_preserving_tail(node)
        elif _is_invisible(node):
            _remove_preserving_tail(node)
        else:
            href = node.get('href', '') if _get_tag(node) == 'a' else ''
            node.attrib.clear()
            if href:
                node.set('href', href)

    result = etree.tostring(tree, encoding="unicode", method="html")

    if not result or not result.strip():
        raise SanitizationError("Sanitized HTML is empty")

    original_kb = len(raw_html) / 1024
    result_kb = len(result) / 1024
    reduction = 1 - (result_kb / original_kb)
    logger.info(
        "[Sanitizer] Input: %.0f KB → Output: %.0f KB (%.1f%% reduction)",
        original_kb,
        result_kb,
        reduction * 100,
    )

    return result
