import copy
import logging

from lxml import etree as lxml_etree
from lxml import html as lxml_html
from rapidfuzz.distance import Levenshtein

from src.exceptions import CondensationError
from src.stages.ie_extractor import IEOutput

logger = logging.getLogger(__name__)

DISTANCE_THRESHOLD = 0.1


def _collect_target_texts(ie_output: IEOutput) -> list[str]:
    texts: list[str] = []
    for field in (
        ie_output.title,
        ie_output.last_post_author,
        ie_output.last_post_date,
        ie_output.link,
    ):
        if field.value:
            texts.append(field.value)
        if field.cue_text:
            texts.append(field.cue_text)
    return texts


def _compute_distance(a: str, b: str) -> float:
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0.0
    return Levenshtein.distance(a, b) / max_len


def _find_matching_xpaths(
    root: lxml_html.HtmlElement,
    tree: lxml_etree._ElementTree,
    target_texts: list[str],
) -> tuple[set[str], set[str]]:
    """Return (element_xpaths, found_target_texts) for elements matching any target."""
    element_xpaths: set[str] = set()
    found_target_texts: set[str] = set()

    for element in root.iter():
        node_text = (element.text or "").strip()
        tail_text = (element.tail or "").strip()
        for text in (node_text, tail_text):
            if not text:
                continue
            for target in target_texts:
                if _compute_distance(text, target) <= DISTANCE_THRESHOLD:
                    element_xpaths.add(tree.getpath(element))
                    found_target_texts.add(target)

    return element_xpaths, found_target_texts


def _compute_ancestor_xpaths(target_xpaths: set[str]) -> set[str]:
    ancestors: set[str] = set()
    for xpath in target_xpaths:
        parts = xpath.split('/')
        # parts[0] is '' (leading slash); '/'.join(['', 'html']) == '/html'
        for i in range(2, len(parts)):
            ancestors.add('/'.join(parts[:i]))
    return ancestors


def condense_html(raw_html: str, ie_output: IEOutput) -> str:
    """
    Produce a condensed HTML snippet containing only nodes relevant to the
    extracted field values and cue texts, with all original attributes preserved.
    Implements Algorithm 2 from XPath Agent (2025).

    Args:
        raw_html:  Full rendered HTML from Stage 1 (with attributes)
        ie_output: Validated IE output from Stage 3

    Returns:
        Condensed HTML string — small, focused, attribute-rich

    Raises:
        CondensationError: If no target nodes are found in the HTML,
                          or if the condensed output is empty
    """
    target_texts = _collect_target_texts(ie_output)
    logger.info("[Condenser] Searching for %d target texts", len(target_texts))
    logger.debug("[Condenser] Distance threshold: %.2f", DISTANCE_THRESHOLD)

    root = copy.deepcopy(lxml_html.fromstring(raw_html))
    tree = root.getroottree()

    target_xpaths, found_texts = _find_matching_xpaths(root, tree, target_texts)

    for text in target_texts:
        if text not in found_texts:
            logger.warning("[Condenser] No matching node found for target: %r", text)

    if not target_xpaths:
        raise CondensationError(
            "No target nodes found in raw HTML — IE values do not match raw HTML content"
        )

    logger.info(
        "[Condenser] Found matching nodes for %d/%d targets",
        len(found_texts),
        len(target_texts),
    )

    ancestor_xpaths = _compute_ancestor_xpaths(target_xpaths)

    for element in list(root.iter()):
        xpath = tree.getpath(element)
        if xpath in target_xpaths or xpath in ancestor_xpaths:
            continue
        for child in list(element):
            element.remove(child)
        element.text = "..."

    condensed = lxml_etree.tostring(
        root, encoding='unicode', method='html', pretty_print=True
    )

    if not condensed.strip():
        raise CondensationError("Condensed HTML is empty after processing")

    line_count = condensed.count('\n') + 1
    logger.info("[Condenser] Condensed HTML: %d lines", line_count)
    if line_count > 500:
        logger.warning(
            "[Condenser] Condensed HTML is large (%d lines) — consider adjusting threshold",
            line_count,
        )

    return condensed
