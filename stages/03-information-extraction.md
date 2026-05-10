# Stage 3 — Information Extraction (IE)

## Purpose

Take the **sanitized HTML** from Stage 2 and extract the **actual text values**
that correspond to the four target fields of a forum thread list:

- `title` — the thread title
- `last_post_author` — the username of whoever posted most recently in the thread
- `last_post_date` — the date/time of the most recent post in the thread
- `link` — the relative or absolute URL of the thread

This stage does NOT generate XPaths. Its only job is semantic understanding —
identify what the values are and what contextual labels appear near them.

The output of this stage feeds directly into:
- Stage 4 (Condenser) — to locate the relevant nodes in the original HTML
- Stage 5 (XPath Generator) — as grounding context for XPath construction

---

## Why a Dedicated IE Step

Asking an LLM to generate XPaths directly from HTML in one shot produces poor
results. The page contains too much noise — navigation, ads, sidebars, footers,
pagination — and the LLM loses focus on the actual thread list.

Separating semantic understanding (this stage) from structural analysis (Stage 5)
dramatically improves XPath quality and generalizability. This is the core
architectural finding of the XPath Agent paper (Stanford, 2025) that this
pipeline is built on.

- IE step answers: **"What are the values?"**
- XPath step answers: **"Where exactly are they in the DOM?"**

---

## Inputs

| Input            | Type   | Description                                        |
|------------------|--------|----------------------------------------------------|
| `sanitized_html` | string | Output of Stage 2 — stripped HTML, no attributes   |

---

## Output

A structured JSON object representing extracted field values from ONE representative
thread item on the page, including cue texts for each field.

```json
{
  "title": {
    "value": "How to configure XenForo permissions",
    "cue_text": ""
  },
  "last_post_author": {
    "value": "darkuser99",
    "cue_text": "Latest: "
  },
  "last_post_date": {
    "value": "Yesterday at 11:42 PM",
    "cue_text": ""
  },
  "link": {
    "value": "/threads/how-to-configure-xenforo-permissions.1234/",
    "cue_text": ""
  }
}
```

### Field definitions

**`value`** — The exact text as it appears in the sanitized HTML.
Character-level accuracy is mandatory. Do not paraphrase, normalize, or reformat.
If the date reads "Yesterday at 11:42 PM" that is the value — not "2024-12-01".
If the link reads "/threads/some-title.1234/" that is the value — not the full URL.

**`cue_text`** — The label or indicative text that appears near the value and
semantically signals its meaning. Examples:
- For last_post_author: `"Latest: "`, `"Last post by "`, `"by "`
- For last_post_date: `"Yesterday"` is the value itself, not a cue — cue would
  be something like `"Last activity: "`
- For title and link: cue_text is usually empty `""` — titles are self-evident
- If no cue text exists, use `""`

Cue texts are critical for Stage 5 — they allow the XPath generator to use
semantic anchors rather than hardcoding specific values into selectors.

---

## LLM Configuration

### Temperature
`0` — deterministic, factual extraction. No creativity needed.

### Max tokens
`1000` — the output schema is compact.

### Response format
Instruct the model to respond in **JSON only** — no preamble, no explanation,
no markdown fences. Raw JSON string that can be parsed directly.

### Output validation
Use **Pydantic** to validate and parse the LLM response. Define models:

```python
from pydantic import BaseModel

class FieldExtraction(BaseModel):
    value: str
    cue_text: str

class IEOutput(BaseModel):
    title: FieldExtraction
    last_post_author: FieldExtraction
    last_post_date: FieldExtraction
    link: FieldExtraction
```

If the LLM returns invalid JSON or fails Pydantic validation, retry once with
an explicit correction message before raising `IEExtractionError`.

---

## Prompt Architecture

The prompt is composed of three parts assembled at call time:

### Part 1 — System Prompt (Forum Expert Skill)
A detailed, domain-specific system prompt that gives the LLM deep knowledge of
forum HTML structure, vocabulary, semantic patterns, and common pitfalls.

**This is defined in a separate file: `forum_expert_skill.md`**

Read the full contents of `forum_expert_skill.md` and inject it as the system
prompt verbatim. This file is a first-class artifact — treat it as carefully
as source code. It covers:
- Forum anatomy and thread list structure
- Forum software vocabulary (XenForo, phpBB, vBulletin, generic)
- The OP vs last-poster distinction (critical)
- Common cue texts for each field
- Priority rules when multiple candidates exist
- Anti-patterns and false positives to ignore
- The cue text concept and how to apply it

### Part 2 — Task Instruction
A concise instruction block appended after the system prompt:

```
Your task is to analyse the forum HTML below and extract the following fields
from ONE thread item that clearly shows all four fields:

- title: the thread title
- last_post_author: the username of the most recent poster (NOT the original poster)
- last_post_date: the date/time of the most recent post (NOT the thread creation date)
- link: the URL path of the thread

For each field, also extract the cue_text — the nearby label text that signals
the field's meaning. If no cue text exists, use an empty string.

Return ONLY a JSON object. No explanation. No markdown. Raw JSON only.
Follow this exact schema:
{
  "title": {"value": "...", "cue_text": "..."},
  "last_post_author": {"value": "...", "cue_text": "..."},
  "last_post_date": {"value": "...", "cue_text": "..."},
  "link": {"value": "...", "cue_text": "..."}
}
```

### Part 3 — HTML Context
The sanitized HTML appended as the final user message:

```
# Forum HTML:
{sanitized_html}
```

---

## Error Handling

| Scenario                              | Behaviour                                                  |
|---------------------------------------|------------------------------------------------------------|
| LLM returns invalid JSON              | Retry once with correction prompt, then raise `IEExtractionError` |
| Pydantic validation fails             | Retry once with correction prompt, then raise `IEExtractionError` |
| Any field value is empty string       | Raise `IEExtractionError` — all four fields are required   |
| LLM returns a field not in schema     | Ignore extra fields, Pydantic handles this                 |
| LLM API call fails                    | Raise `IEExtractionError` with upstream error attached     |

---

## What NOT to do

- Do not pass raw unsanitized HTML to the LLM — sanitized only
- Do not ask the LLM to extract XPaths at this stage — values only
- Do not normalize or clean the extracted values — character-level accuracy required
- Do not extract multiple thread items — one representative item is sufficient
  for the XPath generation to produce generalizable selectors
- Do not hardcode expected values — the LLM must discover them from the HTML
- Do not use a low-quality or fast model here — this stage sets the quality
  ceiling for everything downstream

---

## File Location

```
src/
├── stages/
│   └── ie_extractor.py        # Contains extract_fields() function
├── prompts/
│   └── forum_expert_skill.md  # The forum-expert system prompt (separate artifact)
└── exceptions.py              # IEExtractionError defined here
```

---

## Function Signature

```python
async def extract_fields(sanitized_html: str) -> IEOutput:
    """
    Extract thread field values and cue texts from sanitized forum HTML.
    Uses a forum-expert LLM prompt to identify title, last_post_author,
    last_post_date, and link from the thread list.

    Args:
        sanitized_html: Stripped HTML string from Stage 2

    Returns:
        IEOutput: Validated Pydantic model with value + cue_text for each field

    Raises:
        IEExtractionError: If extraction fails after retry
    """
```

---

## Dependencies

```
openai>=1.0.0
pydantic>=2.0.0
```

Add to `requirements.txt`.

---

## Notes for Claude Code

- The forum_expert_skill.md file is loaded at runtime from disk — do not hardcode
  its contents into the Python source. Read it with `Path("src/prompts/forum_expert_skill.md").read_text()`
- Log the extracted values at INFO level after successful extraction — this makes
  debugging downstream failures much easier
- The retry prompt for invalid JSON should include the original response and say
  explicitly: "Your previous response was not valid JSON. Return only raw JSON,
  no explanation, no markdown fences."
- Keep the system prompt and task instruction as separate string variables in the
  code before joining — makes them easier to modify independently during development
