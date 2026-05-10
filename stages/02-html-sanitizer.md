# Stage 2 — HTML Sanitizer

## Purpose

Take the raw rendered HTML from Stage 1 and produce a **stripped-down version**
that preserves only the structural skeleton and text content of the page — removing
all attributes, invisible nodes, scripts, styles, and noise.

This sanitized HTML is the input to Stage 3 (IE / Information Extraction). It is
NOT used for XPath generation — that uses a different version of the HTML (see
Stage 4, the Condenser).

---

## Why This Step Exists

A fully rendered forum page can be 500KB–2MB of raw HTML. It contains:
- Inline CSS and JS blocks
- SVG icons and image tags
- Navigation bars, sidebars, footers, ads
- Hundreds of meaningless wrapper divs with utility class names
- Invisible elements (display:none, hidden inputs, ARIA artifacts)
- Metadata tags, link preloads, tracking pixels

Feeding this directly to an LLM for semantic analysis wastes context window,
introduces noise that degrades extraction quality, and increases cost.

The paper (XPath Agent, 2025) demonstrated that sanitizing HTML down to tag
structure + text content reduces page size to **10–20% of the original** on
average, with no meaningful loss of semantic information for the IE task.

---

## What Gets Removed

| Element                          | Reason                                              |
|----------------------------------|-----------------------------------------------------|
| `<script>` tags + content        | Code, not content                                   |
| `<style>` tags + content         | CSS, not content                                    |
| `<svg>` tags + content           | Icons, not content                                  |
| `<img>` tags                     | Images carry no text for IE                         |
| `<link>`, `<meta>` tags          | Page metadata, not relevant to thread structure     |
| `<noscript>` tags                | Fallback content, not what the user sees            |
| ALL HTML attributes              | class, id, href, data-*, aria-*, style, etc.        |
| Invisible nodes                  | Elements with no visible text and no relevant children |
| Empty nodes                      | Tags that contain only whitespace after stripping   |
| HTML comments                    | <!-- ... -->                                        |

## What Gets Kept

| Element                          | Reason                                              |
|----------------------------------|-----------------------------------------------------|
| Structural tags                  | div, section, article, ul, li, table, tr, td, etc.  |
| Semantic tags                    | a, span, p, h1-h6, time, strong, em                 |
| Text content                     | The actual visible text inside elements             |

---

## Algorithm

This is a direct implementation of **Algorithm 1** from the XPath Agent paper.

The algorithm performs two passes over the HTML tree:

### Pass 1 — Build traversal stacks (depth-first)
Traverse the tree depth-first, pushing nodes onto a `left_stack`.
Simultaneously build a `right_stack` in reverse order.
This sets up a bottom-up processing order for Pass 2.

### Pass 2 — Clean nodes bottom-up
Process nodes from leaves to root (via `right_stack`).
For each node:
- If the node is **invisible or has no meaningful text** → remove it from parent
- Otherwise → strip all its attributes, keep its tag and text

Bottom-up order is critical: a parent node is only evaluated after all its
children have already been processed. This means by the time we check if a
parent is "empty," we already know which of its children survived.

### Invisibility / emptiness criteria

A node is considered invisible or empty if ALL of the following are true:
- Its tag is not a structural container (not div, section, article, ul, ol, table, etc.)
- It contains no direct text content (or only whitespace)
- It has no children remaining after Pass 2 processing

Additionally, unconditionally remove nodes whose tag is in this blocklist
regardless of content:
```python
REMOVE_TAGS = {
    "script", "style", "svg", "img", "link", "meta",
    "noscript", "head", "iframe", "canvas", "video", "audio",
    "input", "button", "form", "select", "textarea"
}
```

Note: keep `<a>` tags — they carry link text which is meaningful for identifying
thread titles and author names even without the href attribute.

Note: keep `<time>` tags — forums frequently use `<time>` for timestamps. The
text content of `<time>` (e.g. "Yesterday at 11:42 PM") is the value we need.

---

## Implementation

### Library
```
lxml
```

Use `lxml.html` for parsing — it handles malformed real-world HTML better than
Python's built-in `html.parser` and is significantly faster than BeautifulSoup
for tree traversal.

### Parsing

```python
from lxml import html as lxml_html

tree = lxml_html.fromstring(raw_html)
```

### Attribute stripping

After determining a node should be kept, strip all its attributes:
```python
node.attrib.clear()
```

### Serialization

After sanitization, serialize back to an HTML string:
```python
from lxml import etree
sanitized_html = etree.tostring(tree, encoding="unicode", method="html")
```

---

## Function Signature

```python
def sanitize_html(raw_html: str) -> str:
    """
    Strip a rendered HTML page down to structural skeleton + text content.
    Removes all attributes, scripts, styles, invisible nodes, and noise.
    Implements Algorithm 1 from XPath Agent (2025).

    Args:
        raw_html: Full rendered HTML string from Stage 1

    Returns:
        Sanitized HTML string — same tree structure, no attributes, no noise.
        Typically 10-20% the size of the input.

    Raises:
        SanitizationError: If the HTML cannot be parsed or the result is empty
    """
```

Define `SanitizationError` in the shared `exceptions.py`.

---

## Logging

After sanitization, log:
- Input size in KB
- Output size in KB
- Reduction percentage

Example:
```
[Sanitizer] Input: 842 KB → Output: 94 KB (88.8% reduction)
```

This is useful for debugging and for validating the sanitizer is working correctly.

---

## What NOT to do

- Do not use regex to parse or modify HTML — use lxml tree operations only
- Do not remove `<a>` tags — their text content is essential for IE
- Do not remove `<time>` tags — forums use them for timestamps
- Do not modify text content — preserve it character-for-character as the paper
  requires ("character-level consistency" is critical for Stage 3 cue text matching)
- Do not sanitize in-place on the original HTML — work on a deep copy so the
  original is available for Stage 4 (the Condenser needs the unsanitized HTML
  with attributes intact)
- Do not use BeautifulSoup — lxml is faster and more reliable for this task

---

## Critical Note — Two HTML Versions

This stage produces the **sanitized HTML** used only by Stage 3 (IE).

The **original raw HTML** from Stage 1 must be preserved and passed separately
to Stage 4 (Condenser). The Condenser needs the full attributes (class names,
IDs, hrefs) to produce useful XPaths. Never pass sanitized HTML to the Condenser.

The pipeline must maintain both versions in parallel from this point:

```
raw_html (from Stage 1)
    ├── → sanitize_html() → sanitized_html → Stage 3 (IE)
    └── → (kept as-is)   → raw_html       → Stage 4 (Condenser)
```

---

## File Location

```
src/
└── stages/
    └── sanitizer.py   # Contains sanitize_html() and SanitizationError
```

---

## Dependencies

```
lxml>=5.0.0
```

Add to `requirements.txt`.

---

## Notes for Claude Code

- The two-pass stack approach from the paper is the correct implementation —
  do not simplify to a single recursive traversal, as bottom-up order is semantically
  important for empty node detection
- Test the sanitizer on both provided forum URLs before integrating with the
  pipeline and log the reduction ratio to verify it's in the expected 80-90% range
- If lxml fails to parse the HTML (rare but possible with severely malformed pages),
  catch the exception and raise `SanitizationError` with the original lxml error
  message attached
