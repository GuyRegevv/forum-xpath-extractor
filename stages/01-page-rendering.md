# Stage 1 — Page Rendering

## Purpose

Receive a forum URL as input and return the **fully rendered HTML** of that page —
meaning JavaScript has executed and the complete DOM is available.

This is a prerequisite for all subsequent stages. Without a fully rendered page,
dynamic forum content (thread lists loaded via JS) will be missing from the HTML,
and all downstream processing will fail silently or produce wrong results.

---

## Why Playwright

Forum pages are almost universally JavaScript-rendered. A plain HTTP request (e.g.
with `httpx` or `requests`) returns the server-side HTML skeleton — which on modern
forum software like XenForo, phpBB, and vBulletin typically contains little to none
of the actual thread list data. The thread items are injected into the DOM by JS
after page load.

Playwright launches a real Chromium browser, executes JavaScript, and waits for the
page to reach a stable state before returning the HTML. This is the correct tool for
this job. Selenium is an alternative but Playwright is preferred for its cleaner
async API, better reliability, and active maintenance.

---

## Inputs

| Input | Type   | Description                                      |
|-------|--------|--------------------------------------------------|
| `url` | string | A publicly accessible forum URL to be rendered   |

No authentication, no cookies, no session state. The assignment specifies pages are
publicly accessible. Do not implement any login logic.

---

## Output

| Output        | Type   | Description                                                  |
|---------------|--------|--------------------------------------------------------------|
| `html`        | string | The full rendered HTML of the page as a UTF-8 string         |
| `final_url`   | string | The final URL after any redirects                            |

Return both. The final URL matters because some forums redirect to a canonical URL
and we want to record what was actually loaded.

---

## Implementation

### Library
```
playwright (async API)
```

Install: `pip install playwright && playwright install chromium`

### Browser configuration

Run in **headless mode**. The target forums are selected specifically to avoid
CAPTCHA and Cloudflare challenges (per the assignment brief), so no stealth or
anti-bot configuration is required. Keep it simple.

Set a realistic user agent string to avoid trivial bot detection:
```
Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36
```

### Wait strategy

Do NOT use a fixed sleep timer (e.g. `time.sleep(3)`). This is fragile — too short
on slow pages, too long on fast ones.

Use Playwright's `wait_until="networkidle"` strategy, which waits until there are
no more than 2 in-flight network requests for 500ms. This reliably indicates the
page and its dynamic content have finished loading.

If `networkidle` times out (default 30s), fall back to `wait_until="domcontentloaded"`
and log a warning. Do not raise an exception — return whatever HTML is available.

### Page size awareness

After rendering, log the size of the returned HTML in KB. This is useful for
debugging and for understanding how much the sanitizer (Stage 2) is reducing the
payload.

### Viewport

Set viewport to `1920x1080`. Some forum layouts render differently on narrow
viewports and may hide columns or collapse thread metadata. Full desktop width
ensures all fields are present in the DOM.

---

## Function Signature

```python
async def render_page(url: str) -> dict:
    """
    Render a forum URL using Playwright and return the full HTML.

    Args:
        url: Publicly accessible forum URL

    Returns:
        {
            "html": str,       # Full rendered HTML as UTF-8 string
            "final_url": str,  # URL after redirects
        }

    Raises:
        PageRenderError: If the page fails to load entirely (non-2xx, timeout, etc.)
    """
```

Define a custom `PageRenderError` exception in a shared `exceptions.py` module.
All stages should use shared exceptions — do not use bare `Exception`.

---

## Error Handling

| Scenario                        | Behaviour                                                        |
|---------------------------------|------------------------------------------------------------------|
| Page returns non-2xx status     | Raise `PageRenderError` with status code and URL                 |
| Navigation timeout (>30s)       | Retry once with `domcontentloaded`, then raise `PageRenderError` |
| Network unreachable             | Raise `PageRenderError` immediately, no retry                    |
| Page loads but HTML is empty    | Raise `PageRenderError` with message "Empty HTML returned"       |

---

## What NOT to do

- Do not use `requests` or `httpx` — they do not execute JavaScript
- Do not use fixed `sleep()` waits
- Do not implement proxy rotation, CAPTCHA solving, or cookie injection — out of scope
- Do not parse or modify the HTML at this stage — return it raw
- Do not cache responses — always fetch fresh

---

## File location

```
src/
└── stages/
    └── renderer.py   # Contains render_page() and PageRenderError
```

---

## Dependencies

```
playwright>=1.40.0
```

Add to `requirements.txt`.

---

## Notes for Claude Code

- Use the `async with async_playwright()` context manager pattern — do not manage
  browser lifecycle manually
- Open a new browser context per call (not per session) to avoid state leakage
  between runs
- Close the browser context in a `finally` block to prevent resource leaks
- The function is `async` — the caller is responsible for running it in an event loop
