# Stage 4 — HTML Condenser

## Purpose

Take the **raw unsanitized HTML** from Stage 1 and the **extracted field values
and cue texts** from Stage 3, and produce a **condensed HTML snippet** that:

- Keeps only the nodes that are relevant to the target fields
- Preserves all original attributes (class, id, href, data-*, etc.)
- Replaces all irrelevant nodes' children with `"..."`

This condensed HTML is the input to Stage 5 (XPath Generator). It gives the LLM
a small, focused, attribute-rich HTML context from which it can write precise,
generalizable XPath selectors.

---

## Why This Step Exists

After Stage 3 we know WHAT the values are. Now we need to find WHERE they live
in the original DOM — with full attributes intact — so Stage 5 can write XPaths
that reference class names, IDs, and other structural attributes.

We cannot feed the full raw HTML to Stage 5 — it's too large and too noisy.
Instead we surgically trim the tree: keep the nodes containing our target values
and their surrounding context, collapse everything else to `"..."`.

The result is a compact HTML snippet — typically 50-150 lines — that contains
exactly the structural information needed to write robust XPaths.

This is a direct implementation of **Algorithm 2** from the XPath Agent paper
(Stanford, 2025).

---

## Inputs

| Input          | Type     | Description                                                  |
|----------------|----------|--------------------------------------------------------------|
| `raw_html`     | string   | Original rendered HTML from Stage 1 — with all attributes    |
| `ie_output`    | IEOutput | Pydantic model from Stage 3 — values and cue texts per field |

---

## Output

| Output           | Type   | Description                                                      |
|------------------|--------|------------------------------------------------------------------|
| `condensed_html` | string | Trimmed HTML preserving only target-relevant nodes with attributes |

---

## Algorithm

Direct implementation of **Algorithm 2** from the XPath Agent paper.

### Step 1 — Collect target texts

From the `ie_output`, collect all texts that need to be located in the raw HTML:

```python
target_texts = []
for field in [ie_output.title, ie_output.last_post_author,
              ie_output.last_post_date, ie_output.link]:
    if field.value:
        target_texts.append(field.value)
    if field.cue_text:
        target_texts.append(field.cue_text)
```

Both values AND cue texts are targets — cue texts are anchors in the DOM and
must be preserved in the condensed HTML for Stage 5 to use them.

### Step 2 — Define a distance function

The distance function measures how similar a node's text content is to a target
text. Use **normalized edit distance** (Levenshtein distance divided by max
length of the two strings). This handles minor whitespace differences and
truncation gracefully.

```python
def distance(node_text: str, target_text: str) -> float:
    # Returns 0.0 for exact match, 1.0 for completely different
    # Use rapidfuzz or python-Levenshtein for efficiency
    from rapidfuzz.distance import Levenshtein
    max_len = max(len(node_text), len(target_text))
    if max_len == 0:
        return 0.0
    return Levenshtein.distance(node_text, target_text) / max_len
```

Use a distance threshold of `0.1` — nodes with distance ≤ 0.1 to any target
text are considered matching nodes and must be kept in full.

### Step 3 — Find matching nodes

Traverse the entire raw HTML tree. For each node that has text content:
- Compute distance to every target text
- Track the minimum distance across all targets
- If minimum distance ≤ threshold → mark this node as a "target node"
- Record its XPath position for Step 4

```python
target_xpaths = set()
for element in tree.iter():
    node_text = (element.text or "").strip()
    tail_text = (element.tail or "").strip()
    for text in [node_text, tail_text]:
        if text:
            for target in target_texts:
                if distance(text, target) <= DISTANCE_THRESHOLD:
                    target_xpaths.add(tree.getpath(element))
```

### Step 4 — Condense the tree

Traverse the tree again. For each node:
- If the node's XPath is in `target_xpaths` → keep it fully (text + children + attributes)
- If any of the node's descendants are in `target_xpaths` → keep the node as
  a container but collapse its non-target children
- Otherwise → replace the node's children with a single text node `"..."`
  and clear its own text content if it has no direct target match

The key rule: **ancestor nodes of target nodes are always kept as structural
context** — they provide the class names and hierarchy that Stage 5 needs
to write the XPath.

### Step 5 — Serialize

Serialize the condensed tree back to an HTML string with full attributes preserved.

---

## Critical Constraint — Use Raw HTML, Not Sanitized

This stage MUST receive the **original raw HTML from Stage 1**, not the sanitized
HTML from Stage 2. The sanitized HTML has all attributes stripped — using it here
would produce condensed HTML with no class names or IDs, making it useless for
XPath generation.

The pipeline must maintain both versions in parallel:

```
Stage 1 raw_html
    ├── Stage 2 → sanitized_html → Stage 3 (IE)
    └── Stage 4 (Condenser) ← raw_html passed directly here
```

---

## What the Output Looks Like

Given a XenForo page and extracted values from Stage 3, the condensed HTML
output might look like:

```html
<div class="structItem structItem--thread">
  <div class="structItem-cell structItem-cell--main">
    <div class="structItem-title">
      <a href="/threads/configure-permissions.1234/">Configure permissions for user groups</a>
    </div>
    <div class="structItem-meta">
      ...
    </div>
  </div>
  <div class="structItem-cell structItem-cell--latest">
    <span class="structItem-latestDate">
      <span>Latest: </span>
      <a href="/members/darkuser99/" class="username">darkuser99</a>
      <time class="u-dt" datetime="2024-12-01T23:42:00+0000">Yesterday at 11:42 PM</time>
    </span>
  </div>
</div>
```

Everything outside the relevant thread unit is collapsed to `"..."`.
The target values and their immediate context are preserved in full with
all original attributes — giving Stage 5 exactly what it needs.

---

## Function Signature

```python
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
```

Define `CondensationError` in the shared `exceptions.py`.

---

## Error Handling

| Scenario                                  | Behaviour                                                        |
|-------------------------------------------|------------------------------------------------------------------|
| No matching nodes found for any target    | Raise `CondensationError` — IE values don't match raw HTML       |
| Condensed output is empty                 | Raise `CondensationError`                                        |
| Only some targets found (partial match)   | Log a warning per missing target, proceed with what was found    |
| Distance threshold finds too many nodes   | Log warning if condensed HTML > 500 lines, proceed anyway        |

---

## Logging

After condensation, log:
- Number of target texts searched for
- Number of target nodes found
- Condensed HTML size in lines
- Any target texts that had no match (warning level)

Example:
```
[Condenser] Searching for 6 target texts
[Condenser] Found matching nodes for 6/6 targets
[Condenser] Condensed HTML: 87 lines
```

---

## What NOT to do

- Do not use the sanitized HTML as input — attributes are required
- Do not remove any attributes from the condensed output — class names and IDs
  are essential for Stage 5 XPath generation
- Do not use exact string matching for node lookup — use the distance function
  to handle whitespace variations and minor differences
- Do not keep the entire thread list — only the ONE thread unit that contains
  the target values should be preserved in full. Sibling thread units should
  be collapsed.
- Do not collapse the target node's parent chain — ancestors must be kept as
  structural context all the way up to a reasonable root

---

## File Location

```
src/
└── stages/
    └── condenser.py    # Contains condense_html() and CondensationError
```

---

## Dependencies

```
lxml>=5.0.0
rapidfuzz>=3.0.0     # For efficient fuzzy string matching
```

Add both to `requirements.txt`.

---

## Notes for Claude Code

- Use `lxml.html` for parsing — same library as the sanitizer for consistency
- `tree.getpath(element)` from lxml returns the XPath of any element — use this
  to track which nodes are targets without storing element references directly
- The distance threshold of `0.1` is a starting value — if testing shows too
  many or too few matches, adjust it. Log the threshold value used so it is
  easy to tune.
- Test the condenser on both provided forum URLs and manually inspect the
  condensed output to verify: (a) target values are present, (b) class names
  are preserved, (c) the output is small enough to be useful (~50-150 lines)
- If `rapidfuzz` is unavailable, `difflib.SequenceMatcher` is an acceptable
  fallback but is slower
