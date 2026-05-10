# Forum XPath Extractor

An AI-powered pipeline that takes a forum URL and automatically generates robust XPath selectors for four key fields present in any forum thread list: **title**, **last post author**, **last post date**, and **link**. It works across different forum software and layouts without any hardcoding - it uses LLMs to understand the semantic structure of each page rather than relying on fixed patterns.

---

## Architecture

The pipeline has seven stages that run in order. Each stage produces something the next stage needs.

```
URL
 |
[1] Page Renderer      -> raw HTML kept and passed to stages 4, 5, and 5.5
 |
[2] HTML Sanitizer     -> strips attributes and noise
 |
[3] IE Extractor       -> extracts one example value + cue text per field
 |
[4] HTML Condenser     -> focuses raw HTML around the target nodes
 |
[5] XPath Generator    -> generate-and-validate loop, up to 3 iterations per field
 |
[5.5] Reconciler       -> cross-checks match counts, fixes outliers
 |
[6] Output Formatter   -> JSON file + console summary
```

### Stage 1 - Page Renderer

Launches a headless browser, navigates to the URL, waits for JavaScript to finish, and captures the full rendered HTML. This raw HTML - with every class name, attribute, and element intact - is kept and passed through to Stages 4 and 5.

### Stage 2 - HTML Sanitizer

Takes the raw HTML and produces a stripped-down copy:
- Removes tags that carry no content: `<script>`, `<style>`, `<img>`, forms, iframes, etc.
- Clears every attribute from every remaining element - no class names, no IDs, no data attributes (only `href` on links is kept)
- Removes empty elements that contribute nothing

The result is a clean, text-and-structure-only version of the page - typically 10–20% of the original size. This is what the AI reads in Stage 3.

The **raw HTML from Stage 1 is kept in parallel** and passed forward separately. The sanitized version is for reading; the raw version is for XPath targeting later.

### Stage 3 - Information Extractor

Sends the sanitized HTML to an AI and asks it to find **one concrete example of each of the four target fields** on the page.

For each field the AI returns:
- `value` - the actual text it found (e.g. `"Sammtuga"` for `last_post_author`)
- `cue_text` - any nearby label that marks the field structurally (e.g. `"Latest: "`)

The AI uses a forum-expert system prompt (`src/prompts/forum-expert-skill/SKILL.md`) that teaches it how forums are laid out - how to distinguish the last poster from the original poster, how to read relative timestamps, and so on. The response is validated with Pydantic; if the JSON is malformed, one retry is attempted.

These four values are the input to Stage 4.

### Stage 4 - HTML Condenser

Takes the four example values and the raw HTML. For each value:
1. Fuzzy-searches the raw HTML tree for the element whose text matches it - fuzzy meaning it tolerates small differences (e.g. extra whitespace, minor encoding variations) rather than requiring an exact character-for-character match
2. Traces the path from that element up to the root, marking every ancestor
3. Discards every sibling subtree that doesn't lead to any target node

The result is a small, focused HTML snippet - still attribute-complete - that contains only the thread-list structure. This is what Stage 5 works with.

### Stage 5 - XPath Generator

Runs a generate-and-validate loop for each field, up to 3 iterations:

1. The AI receives the condensed HTML, the field name, the known example value, and the cue text. It writes an XPath.
2. The XPath is executed locally against the full raw HTML using `lxml`.
3. The result is checked: does it match anything? Does it return the expected value?
4. If it fails, the specific reason is sent back to the AI, which revises the XPath. Repeat.

Each field ends up as `correct` (matched and value confirmed), `best_effort` (matched something but expected value not found), or `failed` (no matches).

### Stage 5.5 - XPath Reconciler

Compares the match counts across all four XPaths. On a page with 20 threads, all four should return ~20 matches. If one is an outlier:

- **Too few** (e.g. 5 instead of 20): finds the rows the XPath is missing, shows them to the AI, and asks for a revised XPath that covers them
- **Too broad** (e.g. 60 instead of 20): finds a row where the XPath fires multiple times, shows the AI what it's over-matching, and asks for a narrower version

Any revision is tested before it's accepted - it must improve the count and still match the known sample value. If no improvement is found, the Stage 5 result is kept unchanged.

### Stage 6 - Output Formatter

Assembles the final result, computes an overall status (`success` / `partial` / `failed`), prints the console summary, and saves the JSON to `results/output_{domain}_{timestamp}.json`.

> The two-stage approach (semantic extraction first, XPath generation second) is inspired by the XPath Agent paper (Stanford, 2025): *"XPath Agent: An Efficient XPath Programming Agent Based on LLM for Web Crawler"*.

---

## Installation

```bash
pip install -r requirements.txt
playwright install chromium
```

---

## Configuration

Copy the example environment file and fill in your OpenAI API key:

```bash
cp .env.example .env
```

Edit `.env`:

```
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o
```

The model can be swapped (e.g. `gpt-4o-mini`, any OpenAI-compatible endpoint) without touching any source file. To use a custom API base URL (e.g. Azure, local proxy), set `OPENAI_BASE_URL` as well.

---

## Usage

```bash
python -m src.main <url>
```

Example:

```bash
python -m src.main https://altenens.is/whats-new/posts/
```

Add `--verbose` / `-v` for debug-level logging.

---

## Example Output

Console summary printed at the end of a run:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Forum XPath Extractor - Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 URL     : https://altenens.is/whats-new/posts/
 Status  : SUCCESS (4/4 fields correct)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 TITLE
   XPath  : //div[contains(@class, 'structItem-title')]/a
   Sample : 👸DROPS - 1081👸 YOONG TEN'S ONLYFANS💋
   ✓ correct (1 iteration, 20 matches)

 LAST POST AUTHOR
   XPath  : //div[contains(@class, 'structItem-cell--latest')]/div[contains(@class, 'structItem-minor')]/a[contains(@class, 'username')]
   Sample : Sammtuga
   ✓ correct (1 iteration, 20 matches)

 LAST POST DATE
   XPath  : //div[contains(@class, 'structItem-cell--latest')]/a/time[contains(@class, 'structItem-latestDate')]
   Sample : A moment ago
   ✓ correct (2 iterations, 20 matches)

 LINK
   XPath  : //div[contains(@class, 'structItem-title')]/a/@href
   Sample : /threads/princessdrops-1081princess-yoong-tens-onlyfanskiss-mark.2937283/
   ✓ correct (1 iteration, 20 matches)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Full JSON output saved to: results/output_altenens.is_20260510_111837.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

JSON file saved to `results/`:

```json
{
  "url": "https://altenens.is/whats-new/posts/",
  "status": "success",
  "fields": {
    "title": {
      "xpath": "//div[contains(@class, 'structItem-title')]/a",
      "sample_value": "👸DROPS - 1081👸 YOONG TEN'S ONLYFANS💋",
      "confidence": "correct",
      "iterations": 1,
      "match_count": 20,
      "original_xpath": null,
      "explanation": null
    },
    "last_post_author": {
      "xpath": "//div[contains(@class, 'structItem-cell--latest')]/div[contains(@class, 'structItem-minor')]/a[contains(@class, 'username')]",
      "sample_value": "Sammtuga",
      "confidence": "correct",
      "iterations": 1,
      "match_count": 20,
      "original_xpath": null,
      "explanation": null
    },
    "last_post_date": {
      "xpath": "//div[contains(@class, 'structItem-cell--latest')]/a/time[contains(@class, 'structItem-latestDate')]",
      "sample_value": "A moment ago",
      "confidence": "correct",
      "iterations": 2,
      "match_count": 20,
      "original_xpath": null,
      "explanation": null
    },
    "link": {
      "xpath": "//div[contains(@class, 'structItem-title')]/a/@href",
      "sample_value": "/threads/princessdrops-1081princess-yoong-tens-onlyfanskiss-mark.2937283/",
      "confidence": "correct",
      "iterations": 1,
      "match_count": 20,
      "original_xpath": null,
      "explanation": null
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

Each field includes a `confidence` level (`correct` / `best_effort` / `failed`), the number of LLM iterations it took, and the match count - how many thread rows the XPath hits on the page.

---

## Design Approach

**No hardcoding.** Forum-specific knowledge lives exclusively in the LLM system prompt at `src/prompts/forum-expert-skill/SKILL.md`. No class names, selectors, or structural assumptions appear in the Python source code.

**Two HTML representations.** Sanitized HTML (attribute-free) is used only for the IE extraction step, where the LLM needs to read text without token noise. Raw HTML (full attributes) is used everywhere XPaths are generated and validated, since real XPaths target attributes like `@class` and `@href`.

**Self-proving output.** Every XPath is validated on the actual page before being returned. The `sample_value` and `match_count` in the output prove that the XPath works - they are not invented.
