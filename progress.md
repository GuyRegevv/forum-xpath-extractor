# Project Progress

## Status
✅ Pipeline complete — all 6 stages implemented, both URLs producing 4/4 correct

## Completed Stages
- ✅ Stage 1 — renderer.py (commits 5227621 → 8314294)
- ✅ Stage 2 — sanitizer.py (commits 66386ff → e41e4fb + ccc6b60 href fix)
- ✅ Stage 3 — ie_extractor.py (commits 6a667fe → 9d4b373 + ccc6b60 + 38687a1)
- ✅ Stage 4 — condenser.py (commits 4c9aacd → 619e2ab)
- ✅ Stage 5 — xpath_generator.py (commits 178faf7 + 960e170 + d962cf1)
- ✅ Stage 6 — formatter.py (commit 960e170)

## Stage Checklist

- [x] Stage 1 — renderer.py
- [x] Stage 2 — sanitizer.py
- [x] Stage 3 — ie_extractor.py
- [x] Stage 4 — condenser.py
- [x] Stage 5 — xpath_generator.py
- [x] Stage 6 — formatter.py (26 unit tests)
- [x] main.py — entry point wiring all stages
- [x] requirements.txt
- [x] .gitignore
- [x] README.md

## End-to-End Test
- [x] `python -m src.main https://altenens.is/whats-new/posts/` — 4/4 correct
- [x] `python -m src.main https://s1.blackbiz.store/whats-new` — 4/4 correct

---

## Post-completion fixes (2026-05-06)
- `response_format={"type": "json_object"}` added to all LLM calls — eliminates invalid JSON retries, all fields now 1 iteration
- Hardcoded value detection in `validate_xpath` — rejects XPaths containing literal field values, forces structural selectors
- Mojibake repair in Stage 3 — `_fix_encoding()` reverses UTF-8-as-Latin-1 misread for Cyrillic titles/dates

## Decisions Made
- Dependencies installed into `.venv/` (Python 3.13) due to Homebrew PEP 668 restriction — use `.venv/bin/pytest` to run tests
- `env.example` renamed to `.env.example` to match CLAUDE.md docs
- `_NAVIGATION_TIMEOUT_MS = 30_000` constant extracted (used for both networkidle and domcontentloaded fallback)
- `PlaywrightError` (base class) caught and wrapped in `PageRenderError` to cover network-unreachable errors
- Stage 2 preserves `href` on `<a>` tags — enables Stage 3 to extract real thread URLs instead of falling back to title text
- `response_format={"type": "json_object"}` used on all LLM calls instead of prompt-only JSON enforcement
- Hardcoded value check (min length 6) in `validate_xpath` — code-enforced, not prompt-enforced

---

## Session Notes
Session 2026-05-03: Implemented Stage 1.
- 7 commits, 16 unit tests + 2 integration tests

Session 2026-05-04: Implemented Stages 2 and 4.
- Stage 2: 24 unit tests + 2 integration tests; altenens 78.6% reduction, blackbiz 90.8%
- Stage 4: 20 unit tests + 2 integration tests

Session 2026-05-05: Implemented Stage 3.
- 5 commits, 14 unit tests + 2 integration tests

Session 2026-05-06: Implemented Stages 5 and 6, main.py, README.
- Stage 5: 37 unit tests + 2 integration tests
- Stage 6: 26 unit tests
- Post-completion: 3 bug fixes (response_format, hardcoded values, mojibake)
- Final state: both URLs 4/4 correct, 1 iteration per field, clean Cyrillic output

Session 2026-05-06 (continued): Stage 5.5 reconciler + provider flexibility.
- Implemented reconcile_xpaths — LLM diagnostic for match-count discrepancies
- Added original_xpath and explanation fields to FieldXPathResult and FieldOutput
- Wired reconcile_xpaths into pipeline between Stage 5 and Stage 6
- Tightened Stage 5 system prompt to forbid text-content predicates on dynamic values
- Added pluggable LLM provider support via OPENAI_BASE_URL env var
- Added rapidfuzz partial_ratio fallback (≥85) in validate_xpath for near-identical strings (e.g. ё vs е)
- Updated .env.example with OpenAI and Gemini provider examples
- Tested Gemini (account-level quota issue — limit: 0) and Groq (TPM too low for payload size)
- Switched to Mistral (mistral-small-latest) — both URLs 4/4 correct

Session 2026-05-07: Robustness fixes + additional URL testing.
- Fixed validate_xpath: when XPath matches 0 elements, include HTML snippet (±4 lines around field value) in both initial prompt and 0-match feedback — guides LLM to correct nesting on first attempt
- Fixed reconciler _to_element_xpath: strip string(...) wrappers before building relative XPath — previously caused silent skip when last failed xpath used string()
- Tested on xenforo.com/community/ — 4/4, reconciler revised date (2→40) and link (10→40)
- Tested on xenforo.com/community/whats-new/ — 4/4
- Tested on xenforo.com/community/whats-new/posts/4477951/ — 4/4
- Tested on meta.discourse.org/latest — failed at IE stage (Discourse uses avatars, no text username in thread list)
- Mistral confirmed as working free provider for the pipeline

Session 2026-05-07 (continued, part 2): Reconciler too-broad detection + shared loop refactor.
- Added too-broad detection: fields with match_count > 2×median are flagged as over-matching
- Median-based reference_count: outlier-high counts excluded so they don't cause false too-few flags
- Added _extract_over_matched_example: finds first row where flagged XPath matches >1 element
- Added _build_too_broad_prompt + _SYSTEM_PROMPT_TOO_BROAD: separate diagnostic for narrowing
- Extracted _find_row_containers as shared helper (used by both too-few and too-broad extractors)
- Extracted _run_reconcile_loop: shared feedback loop, accept_if_improved flips direction
- Too-broad fields processed before too-few so reference counts are clean for second pass
- Both URLs tested: 4/4 correct, reconciler silent (Stage 5 produced clean XPaths this run)
- Previous run (link=44) would now be caught as too-broad and narrowed before title gets falsely flagged

Session 2026-05-07 (continued): Reconciler robustness overhaul.

## Reconciler Design (as of this session)

### What match_count is
`match_count` = number of elements the XPath returns when run against the full raw HTML page.
A discrepancy (e.g. last_post_author=18, others=20) means 2 thread rows have a structural
variant the XPath doesn't cover — not that the XPath is fundamentally wrong.

### How the reconciler finds missing rows
1. Run the reference XPath (field with highest match_count, preferring title on ties) to get
   reference elements (e.g. 20 title `<a>` elements).
2. Walk up from each reference element using `getparent()` until the parent contains more than
   one reference element — at that point the child is the row container (e.g. `<div class="structItem">`).
   This is more general than the original path-divergence heuristic — works on any DOM structure,
   not just XenForo's regular tree.
3. For each row container, run the flagged field's XPath relative to that container.
   - No match → problem row (serialized and sent to LLM)
   - Match → good row (up to 2 kept for structural comparison)

### What gets sent to the LLM
- Forum URL + reference count + which field is being investigated
- All 4 current XPaths with their match counts
- HTML of up to 2 "good" rows (rows that DO match — for structural comparison)
- HTML of all problem rows (rows that don't match)
NOT sent: full page HTML, sanitized HTML, condensed HTML — only the targeted row chunks.

### Feedback loop (MAX_RECONCILE_ITERATIONS = 2)
- Iteration 1: LLM sees full context (good rows + problem rows) and proposes a revised XPath
- If revision fails validation, a factual feedback message is appended (no hints, just what went wrong)
- Iteration 2: LLM refines with conversation history still intact
- Acceptance requires BOTH: new_count > old_count AND validate_xpath confirms value is still found
- If neither iteration succeeds, explanation is still stored but original XPath is kept

### Guards added this session
- Skip reconciliation if field confidence != "correct" (best_effort/failed XPaths have unverified
  sample_value, so count-fixing is meaningless)
- Revised XPath must pass validate_xpath (value check) not just count improvement
- Reference field is dynamic: field with highest match_count, not hardcoded to title
- Row-finding uses walk-up heuristic instead of path-divergence (more general across forum software)
