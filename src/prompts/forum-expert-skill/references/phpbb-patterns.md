# phpBB DOM Patterns

phpBB is one of the oldest and most widely deployed open-source forum platforms.
Load this reference when the sanitized HTML shows phpBB structural patterns.

---

## How to Recognize phpBB (Without Attributes)

Even without class names, phpBB pages have recognizable structural fingerprints:

- Thread lists are almost always rendered as `<table>` structures with `<tr>` per thread
- Each thread row has a clear column separation: title column on the left,
  statistics (replies, views) in the middle, last post info on the right
- The last post column typically shows "by username" pattern — the word "by"
  appears as plain text immediately before the username
- Timestamps are usually absolute (e.g. "Mon Dec 01, 2024 11:42 pm") rather
  than relative — phpBB rarely uses relative timestamps
- Thread titles are wrapped in `<a>` tags inside a `<td>` cell
- Moderator-only threads often have icons or prefix labels before the title

---

## Annotated Sanitized HTML Example

Below is what a phpBB thread list row looks like AFTER sanitization
(all attributes stripped, invisible nodes removed):

```html
<tr>                                           <!-- thread row -->
  <td>                                         <!-- icon/status cell — IGNORE -->
    <span></span>
  </td>
  <td>                                         <!-- title cell -->
    <a>How to configure phpBB permissions</a>  <!-- TITLE + LINK <- extract -->
    <div>
      <a>OriginalPoster</a>                    <!-- OP username — DO NOT EXTRACT -->
    </div>
  </td>
  <td>                                         <!-- replies cell — IGNORE -->
    <span>42</span>
  </td>
  <td>                                         <!-- views cell — IGNORE -->
    <span>1200</span>
  </td>
  <td>                                         <!-- last post cell -->
    <span>Mon Dec 01, 2024 11:42 pm</span>    <!-- LAST POST DATE <- extract -->
    <span>by </span>                           <!-- CUE TEXT for last_post_author -->
    <a>darkuser99</a>                          <!-- LAST POST AUTHOR <- extract -->
  </td>
</tr>
```

### Extraction from this example:
```json
{
  "title": {
    "value": "How to configure phpBB permissions",
    "cue_text": ""
  },
  "last_post_author": {
    "value": "darkuser99",
    "cue_text": "by "
  },
  "last_post_date": {
    "value": "Mon Dec 01, 2024 11:42 pm",
    "cue_text": ""
  },
  "link": {
    "value": "viewtopic.php?t=1234",
    "cue_text": ""
  }
}
```

---

## phpBB-Specific Notes

- The cue text for last_post_author in phpBB is almost always `"by "` — a short
  plain text node immediately before the username link
- phpBB timestamps are absolute and formatted like `"Mon Dec 01, 2024 11:42 pm"`
  — this is the last post date despite being absolute, because it appears in the
  last post column, not the title column
- The title cell may contain sub-page links (e.g. "1, 2, 3") after the title
  link — do not include these in the title value
- Some phpBB installations show "Moderator" or "Administrator" badges near usernames
  — these are role labels, not part of the username value
- phpBB links follow the pattern `viewtopic.php?t=ID` or `./viewtopic.php?t=ID`
- The first `<td>` in each row is typically an icon cell with no meaningful text — skip it
