# Project Progress

## Status
🟡 In progress — Stage 6 complete, end-to-end test pending blackbiz

## Completed Stages
- ✅ Stage 1 — renderer.py (commits 5227621 → 8314294)
- ✅ Stage 2 — sanitizer.py (commits 66386ff → e41e4fb + ccc6b60 href fix)
- ✅ Stage 3 — ie_extractor.py (commits 6a667fe → 9d4b373 + ccc6b60)
- ✅ Stage 4 — condenser.py (commits 4c9aacd → 619e2ab)
- ✅ Stage 5 — xpath_generator.py (commits 178faf7 + 960e170)
- ✅ Stage 6 — formatter.py (commit 960e170)

## Current Stage
End-to-end test

## Next Action
Verify `python -m src.main https://s1.blackbiz.store/whats-new` produces correct output (altenens 4/4 already confirmed).

---

## Stage Checklist

- [x] Stage 1 — renderer.py (test: HTML length logs for both URLs)
- [x] Stage 2 — sanitizer.py (test: reduction ratio — altenens 78.6%, blackbiz 90.8%)
- [x] Stage 3 — ie_extractor.py (test: extracted JSON for both URLs — both PASSED)
- [x] Stage 4 — condenser.py (test: condensed HTML has class names)
- [x] Stage 5 — xpath_generator.py (test: full loop on both URLs)
- [x] Stage 6 — formatter.py (test: JSON output + console display — 26 unit tests passing)
- [x] main.py — entry point wiring all stages
- [ ] requirements.txt
- [ ] .gitignore
- [ ] README.md

## End-to-End Test
- [x] `python -m src.main https://altenens.is/whats-new/posts/` produces correct output (4/4 correct)
- [ ] `python -m src.main https://s1.blackbiz.store/whats-new` — code confirmed correct (integration test 4/4), fails with 30K TPM rate limit when run immediately after altenens; run in a fresh minute window

---

## Decisions Made
- Dependencies installed into `.venv/` (Python 3.13) due to Homebrew PEP 668 restriction — use `.venv/bin/pytest` to run tests
- `env.example` renamed to `.env.example` to match CLAUDE.md docs
- `_NAVIGATION_TIMEOUT_MS = 30_000` constant extracted (used for both networkidle and domcontentloaded fallback)
- `PlaywrightError` (base class) caught and wrapped in `PageRenderError` to cover network-unreachable errors (spec requirement that was missing from the plan)

## Issues Encountered
- System Python (3.14, Homebrew-managed) rejects global pip installs per PEP 668 — solved by creating `.venv`
- `PlaywrightTimeoutError` import was transiently removed in a cleanup commit then re-added in Task 4 — no functional impact

## Session Notes
Session 2026-05-03: Implemented Stage 1 end-to-end using subagent-driven development.
- 7 commits, 16 unit tests + 2 integration tests, all passing
- Integration tests confirmed: altenens.is=118 KB, blackbiz.store=142 KB

Session 2026-05-04: Implemented Stage 2 end-to-end using subagent-driven development.
- 6 commits (66386ff → e41e4fb), 24 unit tests + 2 integration tests, all passing
- Integration tests: altenens.is 117.5 KB → 25.1 KB (78.6%), blackbiz.store 142.6 KB → 13.1 KB (90.8%)

Session 2026-05-04 (continued): Implemented Stage 4 end-to-end using inline execution.
- 2 commits (4c9aacd → 619e2ab), 20 unit tests + 2 integration tests, all passing
- Integration tests: altenens.is 545-line condensed HTML with class names + title + author ✓; blackbiz.store 410-line condensed HTML with class names + author ✓
- Key observation: non-Latin (Cyrillic) titles may be mojibake from LLM in Stage 3; condenser finds author (ASCII) successfully and preserves structural context

Session 2026-05-06: Implemented Stage 5 end-to-end using inline execution.
- 1 commit (178faf7), 37 unit tests + 2 integration tests, all passing
- Integration tests: altenens.is 3/4 correct (title/author/date), link best_effort ✓; blackbiz.store 3/4 correct, link best_effort ✓
- Key: link field is best_effort because link.value is fallback title text from Stage 3 — validation can't confirm href match, but XPath returns valid hrefs
- `text_content()` substring matching means ancestor-container xpaths count as correct — this is intentional per spec

Session 2026-05-06 (continued): Implemented Stage 6 (formatter.py) and main.py.
- 26 formatter unit tests passing; xhr fix committed (ccc6b60) + Stage 6 (960e170)
- Altenens E2E: 4/4 correct, JSON saved to results/; blackbiz blocked by 30K TPM cap
- Cyrillic mojibake fixed as side-effect of href preservation — Stage 3 now returns correct Cyrillic text

Session 2026-05-05: Implemented Stage 3 end-to-end using inline execution.
- 5 commits (6a667fe → 9d4b373), 14 unit tests + 2 integration tests, all passing
- Integration tests: altenens.is extracted title/author/date/link ✓, blackbiz.store ✓
- Key decision: link.value falls back to title text when href stripped — code-level fallback added
- Resume: start Stage 4 with `condenser.py` — use `/superpowers:writing-plans`
