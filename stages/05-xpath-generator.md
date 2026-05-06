# Stage 5 — XPath Generator

## Purpose

Take the **condensed HTML** from Stage 4 and the **extracted field values and
cue texts** from Stage 3, and generate **robust, generalizable XPath selectors**
for each of the four target fields:

- `title`
- `last_post_author`
- `last_post_date`
- `link`

This stage also runs a **self-correcting feedback loop** — it validates each
generated XPath against the live DOM and asks the LLM to refine it if the result
is wrong, missing, or redundant. Maximum 3 iterations per field.

---

## Why a Feedback Loop

LLMs are not perfect XPath programmers on the first attempt. Common failure modes:
- XPath matches 0 elements (too specific, wrong path)
- XPath matches too many elements (too broad, grabs unrelated nodes)
- XPath hardcodes a specific value (not generalizable)
- XPath syntax is valid but logically wrong

The feedback loop closes the gap between "syntactically correct" and "actually
works on this page." This is the "Conversational XPath Evaluator" from the
XPath Agent paper (Stanford, 2025) — and it is the single most important quality
mechanism in the pipeline.

---

## Inputs

| Input            | Type     | Description                                                    |
|------------------|----------|----------------------------------------------------------------|
| `condensed_html` | string   | Output of Stage 4 — focused HTML with full attributes          |
| `ie_output`      | IEOutput | Pydantic model from Stage 3 — values and cue texts per field   |
| `raw_html`       | string   | Original rendered HTML from Stage 1 — used for XPath validation|

---

## Output

A structured JSON object with one XPath per field:

```json
{
  "title": {
    "xpath": "//div[contains(@class,'structItem-title')]//a",
    "sample_value": "Configure permissions for user groups"
  },
  "last_post_author": {
    "xpath": "//div[contains(@class,'structItem-cell--latest')]//a[contains(@class,'username')]",
    "sample_value": "darkuser99"
  },
  "last_post_date": {
    "xpath": "//div[contains(@class,'structItem-cell--latest')]//time",
    "sample_value": "Yesterday at 11:42 PM"
  },
  "link": {
    "xpath": "//div[contains(@class,'structItem-title')]//a/@href",
    "sample_value": "/threads/configure-permissions.1234/"
  }
}
```

Each field includes both the XPath selector and a sample value extracted by
running the XPath against the live page. This makes the output self-proving —
the manager can see immediately that the XPaths work without running them manually.

---

## LLM Configuration

### Temperature
`0` — deterministic output. XPath generation is a precise technical task.

### Max tokens
`500` per field per iteration — XPaths are short, reasoning is brief.

### Response format
JSON only. No preamble, no markdown fences. Raw JSON parseable directly.

Per-field response schema:
```json
{
  "thought": "brief reasoning about how to locate this element",
  "xpath": "the XPath expression"
}
```

Use Pydantic to validate:
```python
class XPathResult(BaseModel):
    thought: str
    xpath: str
```

---

## Prompt Architecture

The XPath generation prompt is composed per-field. For each field, assemble:

### System Prompt
```
You are a pro software engineer specializing in XPath query generation.
Your task is to read the HTML provided and generate ONE XPath expression
that reliably extracts the target value from any page with this structure.

Rules:
1. Never hardcode the target value — not the full string, not a fragment of it.
   Titles, usernames, dates, and URLs are all different on every page.
2. Use contains(@class, 'value') instead of @class='value' for class matching
   — elements often have multiple classes.
3. Never filter on text content. Do not use contains(., '...'), [.='...'], or
   text()='...' to match dynamic values. Navigate to elements using class names,
   tag names, data attributes, and XPath axes only.
   Exception: you MAY use a contains(., '...') predicate on a stable structural
   label (the cue text) to locate an anchor element — never on the target value.
4. If a cue text exists, use it as a structural anchor — traverse from the
   cue text node to the target using XPath axes (following-sibling, parent,
   ancestor, descendant).
5. String functions (contains, starts-with, normalize-space) are allowed on
   attributes only — e.g. contains(@href, '/members/'). Never on text content.
6. Prefer class-based or semantic-attribute-based paths over positional indices.
7. The XPath must work on any page of this forum — imagine it running on 100
   different thread listing pages with completely different content.
8. Always respond in this exact JSON format:
   {"thought": "...", "xpath": "..."}
```

### User Message (initial)
```
Target field: {field_name}
Target value: {ie_output.field.value}
Cue text: {ie_output.field.cue_text}  (empty string if none)

HTML context:
{condensed_html}

Generate the XPath for the target field.
```

### Feedback Message (on retry)
```
Your previous XPath was: {previous_xpath}
Validation result: {feedback}

Refine the XPath based on this feedback.
The refined XPath must address the issue described.
Respond in the same JSON format: {"thought": "...", "xpath": "..."}
```

---

## The Feedback Loop

Run the feedback loop **per field independently**. Each field gets up to 3
attempts. Fields do not share attempt counts.

### Loop structure

```
for each field in [title, last_post_author, last_post_date, link]:
    attempts = []
    for iteration in range(MAX_ITERATIONS):  # MAX_ITERATIONS = 3
        xpath = call_llm(field, condensed_html, previous_attempts)
        feedback = validate_xpath(xpath, raw_html, expected_value)
        attempts.append((xpath, feedback))
        if feedback.is_correct:
            break
    best = select_best(attempts)
    results[field] = best
```

### Validation function

```python
def validate_xpath(xpath: str, raw_html: str, expected_value: str) -> ValidationFeedback:
    """
    Run the XPath against the raw HTML and evaluate the result.

    Returns a ValidationFeedback object with:
    - is_correct: bool
    - match_count: int
    - matched_values: list[str]
    - feedback_message: str  (human/LLM-readable description of what went wrong)
    """
```

### Validation logic and feedback messages

| Scenario                        | is_correct | feedback_message                                              |
|---------------------------------|------------|---------------------------------------------------------------|
| XPath syntax error              | False      | "XPath syntax error: {lxml error message}"                   |
| Matches 0 elements              | False      | "Missing: XPath matched 0 elements. Expected to find: '{value}'" |
| Matches expected value exactly  | True       | "Correct"                                                     |
| Matches value among results     | True       | "Correct (found among {n} matches)"                          |
| Matches but value not in results| False      | "Redundant: XPath matched {n} elements but none contained '{value}'. Matched: {sample}" |
| Matches too many (>20 results)  | False      | "Too broad: XPath matched {n} elements. Narrow it down."     |

### Selecting the best result

After the loop, select the best XPath from all attempts:
1. If any attempt is `is_correct` → take the first correct one
2. If no attempt is correct → take the attempt with the highest match count
   that is still ≤ 20 (closest to finding the right element)
3. If all attempts matched 0 → take the last attempt and flag with a warning

Never raise an exception just because no correct XPath was found — always
return the best available result and log a warning. The pipeline should be
resilient and produce partial output rather than failing entirely.

---

## XPath Validation Implementation

Use `lxml` to run XPaths against the parsed raw HTML:

```python
from lxml import html as lxml_html
from lxml import etree

def run_xpath(xpath: str, raw_html: str) -> list[str]:
    """
    Execute an XPath against the raw HTML and return matched text values.
    Returns empty list if XPath syntax is invalid or matches nothing.
    """
    try:
        tree = lxml_html.fromstring(raw_html)
        results = tree.xpath(xpath)
        # Handle both element results and attribute/text results
        values = []
        for r in results:
            if isinstance(r, str):
                values.append(r.strip())
            elif hasattr(r, 'text_content'):
                values.append(r.text_content().strip())
        return values
    except etree.XPathError as e:
        raise XPathSyntaxError(str(e))
```

---

## Handling the Link Field Specially

The `link` field requires extracting an `href` attribute value, not text content.
The XPath for links must end with `/@href`:

```
//div[contains(@class,'structItem-title')]//a/@href
```

When validating the link XPath:
- Run the XPath and expect string results (attribute values), not elements
- Compare against `ie_output.link.value` which is the URL path
- Accept both absolute URLs and relative paths as correct

Instruct the LLM explicitly in the prompt for this field:
```
Note: This field is a URL. The XPath must end with /@href to extract the
attribute value, not the text content of the link.
```

---

## Conversation History Per Field

To give the LLM context across iterations, maintain a message history per field:

```python
messages = [
    {"role": "user", "content": initial_prompt},
    {"role": "assistant", "content": first_xpath_response},
    {"role": "user", "content": feedback_prompt},
    {"role": "assistant", "content": second_xpath_response},
    ...
]
```

This is the "conversational" aspect of the Conversational XPath Evaluator.
The LLM sees its previous attempts and the feedback — this dramatically improves
refinement quality compared to stateless retries.

---

## Error Handling

| Scenario                              | Behaviour                                                        |
|---------------------------------------|------------------------------------------------------------------|
| LLM returns invalid JSON              | Retry the same iteration with correction prompt (counts as attempt) |
| XPath syntax error from lxml          | Include lxml error in feedback, continue loop                    |
| All 3 iterations produce wrong XPath  | Use best available, log warning, do not raise exception          |
| LLM API call fails                    | Raise `XPathGenerationError` immediately — do not retry API calls|
| condensed_html is empty               | Raise `XPathGenerationError` before starting loop                |

Define `XPathGenerationError` and `XPathSyntaxError` in `exceptions.py`.

---

## Logging

Log at each iteration:
```
[XPathGen] Field: last_post_author | Iteration 1/3
[XPathGen] Generated: //div[contains(@class,'structItem-cell--latest')]//a
[XPathGen] Validation: Correct (matched 'darkuser99')

[XPathGen] Field: title | Iteration 1/3
[XPathGen] Generated: //a[contains(@class,'title')]
[XPathGen] Validation: Missing — 0 elements matched
[XPathGen] Field: title | Iteration 2/3
[XPathGen] Generated: //div[contains(@class,'structItem-title')]//a
[XPathGen] Validation: Correct (matched 'Configure permissions for user groups')
```

---

## What NOT to do

- Do not run all four fields in a single LLM call — generate XPaths per field
  independently so the feedback loop can target each field precisely
- Do not use positional XPaths like `//div[3]/span[2]` — these break across
  pages. Always use attribute-based or semantic paths.
- Do not accept an XPath that hardcodes the target value (e.g.
  `//a[text()='darkuser99']`) — flag this in feedback as "value-dependent, not generalizable"
- Do not raise an exception if a field's XPath is imperfect — return best available
- Do not pass sanitized HTML to lxml for validation — use raw HTML only

---

## File Location

```
src/
└── stages/
    └── xpath_generator.py
```

## Internal Code Structure

`xpath_generator.py` is a single file but must be implemented as clearly separated
internal functions. Do not collapse everything into one large function.
The required structure is:

```python
# ── Entry Point ────────────────────────────────────────────────────────────────

async def generate_xpaths(condensed_html, ie_output, raw_html) -> XPathResults:
    """
    Orchestrates XPath generation for all four fields sequentially.
    Calls _generate_single() per field and collects results.
    """

# ── Per-Field Generator ────────────────────────────────────────────────────────

async def _generate_single(field_name, field_value, cue_text,
                           condensed_html, raw_html) -> FieldXPathResult:
    """
    Runs the feedback loop for a single field.
    Maintains conversation history across iterations.
    Calls the LLM, calls validate_xpath(), selects best result.
    Max iterations defined by MAX_ITERATIONS constant.
    """

# ── Validation ─────────────────────────────────────────────────────────────────

def validate_xpath(xpath, raw_html, expected_value) -> ValidationFeedback:
    """
    Evaluates a generated XPath against the raw HTML.
    Returns structured feedback: is_correct, match_count, matched_values,
    feedback_message.
    """

# ── XPath Execution ────────────────────────────────────────────────────────────

def run_xpath(xpath, raw_html) -> list[str]:
    """
    Executes an XPath against parsed HTML using lxml.
    Returns list of matched text/attribute values.
    Raises XPathSyntaxError on invalid XPath syntax.
    """

# ── Best Result Selector ───────────────────────────────────────────────────────

def _select_best(attempts: list[tuple[str, ValidationFeedback]]) -> FieldXPathResult:
    """
    Given all attempts for a field, selects the best XPath.
    Priority: correct > closest match > last attempt.
    Assigns confidence level: correct / best_effort / failed.
    """
```

This separation makes each concern independently testable and easy to debug.
Claude Code must not merge these into a single monolithic function.

---

## Dependencies

```
openai>=1.0.0
lxml>=5.0.0
pydantic>=2.0.0
```

---

## Notes for Claude Code

- Process all four fields sequentially, not in parallel — keeps logs readable
  and avoids race conditions on shared state
- The `thought` field in each LLM response is valuable — log it at DEBUG level
  so it's visible during development and tuning
- When building the feedback message, always include the previous XPath and the
  specific matched values (not just the count) — seeing what was actually matched
  helps the LLM understand why it was wrong
- After all four fields are processed, log a summary table:
  ```
  [XPathGen] Results summary:
    title           : CORRECT (1 iteration)
    last_post_author: CORRECT (2 iterations)
    last_post_date  : CORRECT (1 iteration)
    link            : WARNING — best effort (3 iterations, no correct match)
  ```
- The MAX_ITERATIONS constant (3) should be defined at module level so it is
  easy to change during testing
