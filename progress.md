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
