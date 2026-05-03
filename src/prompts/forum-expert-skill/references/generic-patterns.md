# Generic Forum Patterns

Use this reference when the sanitized HTML does not clearly match XenForo or
phpBB patterns, or when the forum appears to use custom software.

---

## Universal Forum Structural Laws

Regardless of platform, these structural rules hold across virtually all forums:

1. **Thread items are always siblings** — they share the same parent container
   and have identical or near-identical internal structure
2. **The title is always a link** — `<a>` tag, most prominent text in the unit
3. **Last post info is always positionally separate** from the title section —
   either a different column, a sub-row, or a trailing section
4. **Relative timestamps always mean last activity** — "X ago", "Yesterday",
   day names are never used for thread creation dates
5. **Absolute timestamps near the title mean creation date** — not your target

---

## Identifying the Thread Container

When you cannot identify the platform, find the thread container by looking for
the smallest repeating element that contains ALL of:
- One prominent link (the title)
- At least one short text that looks like a username
- At least one date or time expression

That element is your thread unit. Everything you extract must come from within it.

---

## Relative Timestamp Patterns (Always Last Activity)

These text patterns always indicate a last-post date, never a creation date:

- `"X minutes ago"` / `"X hours ago"` / `"X days ago"`
- `"Yesterday at HH:MM"`
- `"Today at HH:MM"`
- Day names: `"Monday at HH:MM"`, `"Tuesday at HH:MM"`, etc.
- `"Just now"`

Absolute timestamps (e.g. `"Dec 1, 2024"`, `"01/12/2024"`, `"2024-12-01"`) can
be either creation dates or last-post dates — determine by position within the
thread unit (last-post section vs. title section).

---

## When No Cue Text Exists

Many forums display last post info without any label — just a username and
timestamp in a dedicated column. In this case:

- Set `cue_text` to `""` for all fields
- Identify the last_post_author by position: it's the username that appears
  in the right-hand or bottom section of the thread unit, NOT the one near the title
- The date adjacent to that username is the last_post_date

---

## Multi-Column Table Forums

Older or simpler forums often use `<table>` layouts:

```
| Thread Title        | Author   | Replies | Views | Last Post           |
|---------------------|----------|---------|-------|---------------------|
| How to do X         | user123  | 42      | 1.2K  | admin, Dec 1        |
```

In sanitized HTML this becomes nested `<tr>` / `<td>` elements. The last `<td>`
in each row is the last post cell — extract author and date from there.
The first `<td>` contains the title link.
