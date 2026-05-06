# Forum XPath Extractor

An AI-powered pipeline that takes a forum URL and automatically generates robust XPath selectors for four key fields present in any forum thread list: **title**, **last post author**, **last post date**, and **link**. It works across different forum software and layouts without any hardcoding — it uses LLMs to understand the semantic structure of each page.

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

---

## Usage

```bash
python -m src.main <url>
```

Example:

```bash
python -m src.main https://altenens.is/whats-new/posts/
```

Add `--verbose` for debug-level logging.

---

## Example Output

Console summary:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Forum XPath Extractor — Results
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 URL     : https://altenens.is/whats-new/posts/
 Status  : SUCCESS (4/4 fields correct)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 TITLE
   XPath  : //div[contains(@class, 'structItem-title')]/a[contains(@data-tp-primary, 'on')]
   Sample : Configure permissions for user groups
   ✓ correct (1 iteration)

 LAST POST AUTHOR
   XPath  : //div[contains(@class, 'structItem-cell--latest')]//a[contains(@class, 'username')]
   Sample : darkuser99
   ✓ correct (1 iteration)

 LAST POST DATE
   XPath  : //div[contains(@class, 'structItem-cell--latest')]//time
   Sample : Yesterday at 11:42 PM
   ✓ correct (1 iteration)

 LINK
   XPath  : //div[contains(@class, 'structItem-cell--main')]//div[contains(@class, 'structItem-title')]/a/@href
   Sample : /threads/configure-permissions.1234/
   ✓ correct (1 iteration)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 Full JSON output saved to: results/output_altenens.is_20241201_114200.json
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

JSON output (saved to `results/`):

```json
{
  "url": "https://altenens.is/whats-new/posts/",
  "status": "success",
  "fields": {
    "title": {
      "xpath": "//div[contains(@class, 'structItem-title')]/a[contains(@data-tp-primary, 'on')]",
      "sample_value": "Configure permissions for user groups",
      "confidence": "correct",
      "iterations": 1
    },
    "last_post_author": {
      "xpath": "//div[contains(@class, 'structItem-cell--latest')]//a[contains(@class, 'username')]",
      "sample_value": "darkuser99",
      "confidence": "correct",
      "iterations": 1
    },
    "last_post_date": {
      "xpath": "//div[contains(@class, 'structItem-cell--latest')]//time",
      "sample_value": "Yesterday at 11:42 PM",
      "confidence": "correct",
      "iterations": 1
    },
    "link": {
      "xpath": "//div[contains(@class, 'structItem-cell--main')]//div[contains(@class, 'structItem-title')]/a/@href",
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

## Architecture

The pipeline runs six sequential stages:

1. **Page Renderer** (`renderer.py`) — headless Chromium renders the page with JavaScript, returns full HTML
2. **HTML Sanitizer** (`sanitizer.py`) — strips attributes and noise, keeps structural skeleton and text (~80% size reduction)
3. **IE Extractor** (`ie_extractor.py`) — LLM extracts one example value and a cue text per field from the sanitized HTML
4. **HTML Condenser** (`condenser.py`) — fuzzy-matches target values against the raw HTML tree, collapses irrelevant nodes
5. **XPath Generator** (`xpath_generator.py`) — LLM feedback loop generates and validates one XPath per field (max 3 iterations)
6. **Output Formatter** (`formatter.py`) — assembles final JSON with confidence levels, prints console summary, saves to file

Based on the XPath Agent paper (Stanford, 2025): *"XPath Agent: An Efficient XPath Programming Agent Based on LLM for Web Crawler"*.
