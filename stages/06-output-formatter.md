# Stage 6 — Output Formatter

## Purpose

Take the raw XPath results from Stage 5 and produce the **final structured
output** of the pipeline — a clean, well-formed JSON document that is
self-proving, human-readable, and immediately useful to whoever receives it.

This is the last stage. Its output is what gets returned to the user.

---

## Why a Dedicated Formatter

Stage 5 returns internal data structures — Pydantic models, validation metadata,
iteration counts, warning flags. The formatter's job is to translate all of that
into a clean, presentable output that:

- Shows both XPaths AND sample values (self-proving — no need to run anything to trust it)
- Communicates confidence clearly (correct vs best-effort)
- Is structured consistently regardless of whether all fields succeeded or not
- Is ready to be printed, saved to file, or returned via API

---

## Inputs

| Input           | Type            | Description                                          |
|-----------------|-----------------|------------------------------------------------------|
| `xpath_results` | XPathResults    | Output of Stage 5 — XPaths, sample values, metadata |
| `url`           | string          | The original input URL                               |

---

## Output Schema

The final output is a JSON object with this structure:

```json
{
  "url": "https://altenens.is/whats-new/posts/",
  "status": "success",
  "fields": {
    "title": {
      "xpath": "//div[contains(@class,'structItem-title')]//a",
      "sample_value": "Configure permissions for user groups",
      "confidence": "correct",
      "iterations": 1
    },
    "last_post_author": {
      "xpath": "//div[contains(@class,'structItem-cell--latest')]//a[contains(@class,'username')]",
      "sample_value": "darkuser99",
      "confidence": "correct",
      "iterations": 2
    },
    "last_post_date": {
      "xpath": "//div[contains(@class,'structItem-cell--latest')]//time",
      "sample_value": "Yesterday at 11:42 PM",
      "confidence": "correct",
      "iterations": 1
    },
    "link": {
      "xpath": "//div[contains(@class,'structItem-title')]//a/@href",
      "sample_value": "/threads/configure-permissions.1234/",
      "confidence": "correct",
      "iterations": 1
    }
  },
  "summary": {
    "total_fields": 4,
    "correct": 4,
    "best_effort": 0,
    "failed": 0
  }
}
```

---

## Field-Level Properties

### `xpath`
The XPath selector string. Always present — never null.

### `sample_value`
The actual value extracted by running the XPath against the live page.
Proves the XPath works without requiring the reader to run it.
If the XPath matched 0 elements, set to `null`.

### `confidence`
One of three values:

| Value         | Meaning                                                               |
|---------------|-----------------------------------------------------------------------|
| `"correct"`   | XPath was validated — matched the expected value from Stage 3         |
| `"best_effort"` | XPath did not validate after 3 iterations — best available result   |
| `"failed"`    | XPath matched 0 elements even after 3 iterations                      |

### `iterations`
Number of LLM iterations used to generate this XPath (1–3).
Useful for debugging and understanding pipeline performance.

---

## Top-Level Properties

### `status`
One of:

| Value       | Condition                                          |
|-------------|----------------------------------------------------|
| `"success"` | All 4 fields have confidence `"correct"`           |
| `"partial"` | At least 1 field is `"correct"`, at least 1 is not |
| `"failed"`  | All fields are `"best_effort"` or `"failed"`       |

### `summary`
Counts of fields by confidence level. Always present. Gives an at-a-glance
view of pipeline performance without reading all four fields.

---

## Pydantic Output Models

Define the output schema with Pydantic for internal use before serializing to JSON:

```python
from pydantic import BaseModel
from typing import Literal, Optional

class FieldOutput(BaseModel):
    xpath: str
    sample_value: Optional[str]
    confidence: Literal["correct", "best_effort", "failed"]
    iterations: int

class SummaryOutput(BaseModel):
    total_fields: int
    correct: int
    best_effort: int
    failed: int

class PipelineOutput(BaseModel):
    url: str
    status: Literal["success", "partial", "failed"]
    fields: dict[str, FieldOutput]
    summary: SummaryOutput
```

Serialize to JSON using:
```python
output.model_dump_json(indent=2)
```

---

## Console Output

In addition to the JSON output, print a human-readable summary to stdout
after the pipeline completes. This is what the manager sees when running
the script.

Format:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Forum XPath Extractor — Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 URL     : https://altenens.is/whats-new/posts/
 Status  : SUCCESS (4/4 fields correct)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 TITLE
   XPath  : //div[contains(@class,'structItem-title')]//a
   Sample : Configure permissions for user groups
   ✓ correct (1 iteration)

 LAST POST AUTHOR
   XPath  : //div[contains(@class,'structItem-cell--latest')]//a[contains(@class,'username')]
   Sample : darkuser99
   ✓ correct (2 iterations)

 LAST POST DATE
   XPath  : //div[contains(@class,'structItem-cell--latest')]//time
   Sample : Yesterday at 11:42 PM
   ✓ correct (1 iteration)

 LINK
   XPath  : //div[contains(@class,'structItem-title')]//a/@href
   Sample : /threads/configure-permissions.1234/
   ✓ correct (1 iteration)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Full JSON output saved to: output.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Use `✓` for correct, `⚠` for best_effort, `✗` for failed.

---

## File Output

Always save the full JSON output to a file in addition to printing the summary.

File naming convention:
```
output_{domain}_{timestamp}.json
```

Example: `output_altenens.is_20241201_114200.json`

Extract the domain from the input URL using `urllib.parse.urlparse`.
Use `datetime.now().strftime("%Y%m%d_%H%M%S")` for the timestamp.

Save to a `./results/` directory. Create it if it does not exist.

---

## Function Signature

```python
def format_output(
    xpath_results: XPathResults,
    url: str
) -> PipelineOutput:
    """
    Assemble the final pipeline output from Stage 5 results.
    Prints a human-readable summary to stdout.
    Saves the full JSON to ./results/.

    Args:
        xpath_results: Output from Stage 5
        url: The original input URL

    Returns:
        PipelineOutput: Validated Pydantic model — also serialized to JSON file
    """
```

---

## Error Handling

This stage should never raise exceptions — it is the last stage and must
always produce output, even if that output reflects failures upstream.

| Scenario                         | Behaviour                                                   |
|----------------------------------|-------------------------------------------------------------|
| Some fields failed in Stage 5    | Include them with confidence="failed", status="partial"     |
| All fields failed                | status="failed", still write the JSON file                  |
| Cannot write to ./results/       | Log warning, print JSON to stdout instead, do not raise     |

---

## What NOT to do

- Do not filter out or hide failed/best_effort fields — always include all four
  fields in the output regardless of confidence
- Do not raise exceptions — absorb all errors and reflect them in the output
- Do not print raw Pydantic model repr — always use the formatted console output
- Do not omit the sample_value — it is the proof that the XPath works

---

## File Location

```
src/
└── stages/
    └── formatter.py    # Contains format_output() and output Pydantic models
results/
    └── .gitkeep        # Commit the directory, not its contents
```

---

## Dependencies

No new dependencies — uses only `pydantic`, `json`, `pathlib`, `datetime`,
and `urllib.parse` from the standard library.

---

## Notes for Claude Code

- The console output formatting uses Unicode box-drawing characters (━) —
  verify these render correctly in the target terminal before finalising
- The `results/` directory should be in `.gitignore` — add it
- When printing the summary line, compute the correct fraction dynamically:
  `f"{summary.correct}/{summary.total_fields} fields correct"`
- Keep the formatter completely stateless — it reads from xpath_results and
  writes output, no side effects beyond the file write and stdout print
