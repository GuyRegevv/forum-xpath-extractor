# CLAUDE.md — Forum XPath Extractor

## What This Project Is

An AI-powered pipeline that receives a forum URL as input and automatically
extracts robust XPath selectors for four fields present in any forum thread list:

- `title` — the thread title
- `last_post_author` — the username of the most recent poster
- `last_post_date` — the date/time of the most recent post
- `link` — the URL of the thread

The system is **generic** — it works across different forum layouts and software
without any hardcoding. It achieves this by using LLMs to understand the semantic
structure of the page rather than relying on fixed selectors.

---

## Architecture Overview

The pipeline runs six sequential stages. Each stage has its own spec document
in `stages/`. Read the relevant spec before implementing any stage.

```
URL Input
    │
    ▼
[Stage 1] Page Renderer        → renders JS, returns full HTML
    │
    ▼
[Stage 2] HTML Sanitizer       → strips attributes/noise, keeps structure + text
    │                                              │
    ▼                                              │ (raw HTML passed through)
[Stage 3] IE Extractor         → LLM extracts values + cue texts
    │
    ▼
[Stage 4] HTML Condenser       → focuses raw HTML around target nodes
    │
    ▼
[Stage 5] XPath Generator      → LLM generates XPaths with feedback loop
    │
    ▼
[Stage 6] Output Formatter     → produces final JSON + console summary
    │
    ▼
JSON Output
```

### Critical data flow note

Two versions of the HTML exist in parallel from Stage 1 onward:

- **Sanitized HTML** (no attributes) → used only by Stage 3
- **Raw HTML** (full attributes) → passed directly to Stage 4 and Stage 5

Never pass sanitized HTML to Stage 4 or Stage 5. This is the single most
important architectural constraint in the pipeline.

---

## Research Foundation

This pipeline is based on the **XPath Agent paper** (Stanford, 2025):
*"XPath Agent: An Efficient XPath Programming Agent Based on LLM for Web Crawler"*

Key concepts borrowed from the paper:
- Two-stage pipeline: semantic IE first, XPath generation second
- HTML sanitization reducing page size to 10-20% of original (Algorithm 1)
- HTML condensation focusing on target nodes (Algorithm 2)
- Cue text extraction as structural anchors for XPath generation
- Conversational XPath Evaluator — feedback loop, max 3 iterations

Key additions beyond the paper:
- Forum-domain specialization via the forum-expert skill (Stage 3)
- Self-proving output — XPaths returned alongside extracted sample values
- Confidence levels per field (correct / best_effort / failed)
- Cross-pagination validation (bonus — see Stage 5 notes)

---

## Project Structure

```
forum-xpath-extractor/
│
├── CLAUDE.md                          ← you are here
│
├── stages/                            ← spec documents, one per pipeline stage
│   ├── 01-page-rendering.md
│   ├── 02-html-sanitizer.md
│   ├── 03-information-extraction.md
│   ├── 04-html-condenser.md
│   ├── 05-xpath-generator.md
│   └── 06-output-formatter.md
│
├── src/
│   ├── main.py                        ← entry point, CLI, orchestrates pipeline
│   ├── exceptions.py                  ← all custom exceptions defined here
│   │
│   ├── stages/
│   │   ├── renderer.py                ← Stage 1
│   │   ├── sanitizer.py               ← Stage 2
│   │   ├── ie_extractor.py            ← Stage 3
│   │   ├── condenser.py               ← Stage 4
│   │   ├── xpath_generator.py         ← Stage 5
│   │   └── formatter.py               ← Stage 6
│   │
│   └── prompts/
│       └── forum-expert-skill/        ← forum-expert IE prompt (Stage 3)
│           ├── SKILL.md               ← main system prompt, loaded at runtime
│           └── references/
│               ├── xenforo-patterns.md
│               ├── phpbb-patterns.md
│               └── generic-patterns.md
│
├── results/                           ← JSON output files saved here
│   └── .gitkeep
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## Entry Point — main.py

The entry point is a simple CLI that accepts a URL and runs the full pipeline:

```bash
python main.py https://altenens.is/whats-new/posts/
```

`main.py` is responsible for:
1. Parsing the URL argument
2. Instantiating and running each stage in order
3. Passing outputs between stages correctly
4. Catching any unhandled exceptions and printing a clean error message
5. Exiting with code 0 on success, code 1 on failure

The pipeline is async end-to-end. Use `asyncio.run()` in `main.py` to run it.

Example structure:

```python
import asyncio
import sys
from src.stages.renderer import render_page
from src.stages.sanitizer import sanitize_html
from src.stages.ie_extractor import extract_fields
from src.stages.condenser import condense_html
from src.stages.xpath_generator import generate_xpaths
from src.stages.formatter import format_output

async def run_pipeline(url: str):
    rendered   = await render_page(url)
    sanitized  = sanitize_html(rendered["html"])
    ie_output  = await extract_fields(sanitized)
    condensed  = condense_html(rendered["html"], ie_output)
    xpaths     = await generate_xpaths(condensed, ie_output, rendered["html"])
    output     = format_output(xpaths, url)
    return output

if __name__ == "__main__":
    url = sys.argv[1]
    asyncio.run(run_pipeline(url))
```

---

## Exceptions

All custom exceptions live in `src/exceptions.py`. Never use bare `Exception`.

```python
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
```

---

## Environment Variables

Store the OpenAI API key in a `.env` file. Never hardcode it.

```bash
# .env
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o   # set the model here, not in code
```

Load with `python-dotenv` at the top of `main.py`:
```python
from dotenv import load_dotenv
load_dotenv()
```

All LLM calls across stages must read `MODEL_NAME` from the environment:
```python
import os
model = os.getenv("MODEL_NAME", "gpt-4o")
```

This means the model can be changed without touching any source file.

---

## Implementation Order

Implement stages in pipeline order. Do not skip ahead.
Each stage should be tested independently before moving to the next.

1. `renderer.py` — test by printing HTML length for both target URLs
2. `sanitizer.py` — test by logging reduction ratio (expect 80-90%)
3. `ie_extractor.py` — test by printing extracted JSON for both URLs
4. `condenser.py` — test by printing condensed HTML and verifying class names present
5. `xpath_generator.py` — test by running full loop on both URLs
6. `formatter.py` — test by verifying JSON output and console display

---

## Target URLs

The pipeline must work correctly on both of these URLs:

```
https://altenens.is/whats-new/posts/
https://s1.blackbiz.store/whats-new
```

Both run XenForo. Both are publicly accessible with no CAPTCHA or bot protection.
Test on both URLs after implementing each stage.

---

## Coding Conventions

- **Language:** Python 3.11+
- **Async:** All LLM calls and Playwright calls are async. Stage functions that
  call LLMs or the browser must be `async def`. Pure processing functions
  (sanitizer, condenser, formatter) are synchronous `def`.
- **Type hints:** All function signatures must have full type hints
- **Pydantic:** Use Pydantic v2 for all structured data — LLM outputs, pipeline
  outputs, validation results. No raw dicts for structured data.
- **Logging:** Use Python's standard `logging` module. Set level to INFO by
  default, DEBUG available via `--verbose` flag. Format:
  `[StageName] message`
- **No hardcoding:** No forum-specific class names, selectors, or values in
  source code. All domain knowledge lives in the prompt files under `src/prompts/`
- **No global state:** Each pipeline run is fully isolated. No module-level
  mutable state.

---

## Dependencies — requirements.txt

```
playwright>=1.40.0
lxml>=5.0.0
openai>=1.0.0
pydantic>=2.0.0
rapidfuzz>=3.0.0
python-dotenv>=1.0.0
```

---

## .gitignore

```
.env
results/
__pycache__/
*.pyc
.playwright/
```

---

## README.md

Write a README that covers:
1. What the project does (one paragraph)
2. Installation (`pip install -r requirements.txt && playwright install chromium`)
3. Configuration (copy `.env.example` to `.env`, add API key and model name)
4. Usage (`python main.py <url>`)
5. Example output (paste a real JSON result)
6. Architecture overview (reference the stages briefly)

The README is a deliverable — write it as if the manager will read it.

---

## Important Reminders

- Read the stage spec document before implementing each stage
- The forum-expert skill at `src/prompts/forum-expert-skill/SKILL.md` is loaded
  from disk at runtime in Stage 3 — do not hardcode its contents into Python
- Stage 5 (`xpath_generator.py`) must be structured as five internal functions —
  see the spec for the required function breakdown
- The `results/` directory must be created automatically if it does not exist —
  do not assume it exists
- Both target URLs must produce correct output before the project is complete
