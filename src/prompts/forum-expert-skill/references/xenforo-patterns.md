# XenForo DOM Patterns

XenForo is the most modern and widely deployed forum software. Both target URLs
in the assignment (`altenens.is` and `s1.blackbiz.store`) run on XenForo.
This reference should be loaded when the sanitized HTML shows XenForo patterns.

---

## How to Recognize XenForo (Without Attributes)

Even without class names, XenForo pages have recognizable structural fingerprints:

- Thread list items are structured as a flat list of sibling containers
- Each item has a two-region layout: a "main" region (title + metadata) and a
  "latest" region (last post info)
- The "latest" region almost always contains the cue text **"Latest:"** or
  **"Latest post"** as a visible text label
- Timestamps use a `<time>` element whose text content is human-readable
  ("Yesterday at 11:42 PM", "Monday at 3:15 AM", "Dec 1, 2024")
- Thread titles are always wrapped in an `<a>` inside a heading-like container
- Usernames in the last post section are short `<a>` tags

---

## Annotated Sanitized HTML Example

Below is what a XenForo thread list item looks like AFTER sanitization
(all attributes stripped, invisible nodes removed):

```html
<div>                                          <!-- thread item container -->
  <div>                                        <!-- main section -->
    <div>
      <a>Configure permissions for user groups</a>   <!-- TITLE + LINK -->
    </div>
    <div>
      <a>AdminUser</a>                         <!-- OP username — DO NOT EXTRACT -->
      <span>Dec 1, 2024</span>                <!-- Thread creation date — DO NOT EXTRACT -->
      <span>142</span>                         <!-- Reply count — IGNORE -->
      <span>3K</span>                          <!-- View count — IGNORE -->
    </div>
  </div>
  <div>                                        <!-- last post section -->
    <span>Latest: </span>                      <!-- CUE TEXT for last_post_author -->
    <a>darkuser99</a>                          <!-- LAST POST AUTHOR ← extract this -->
    <time>Yesterday at 11:42 PM</time>         <!-- LAST POST DATE ← extract this -->
  </div>
</div>
```

### Extraction from this example:
```json
{
  "title": {
    "value": "Configure permissions for user groups",
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
    "value": "/threads/configure-permissions-for-user-groups.1234/",
    "cue_text": ""
  }
}
```

---

## XenForo-Specific Notes

- The "Latest:" label is almost always present — use it as the anchor for
  last_post_author
- `<time>` elements in XenForo always contain the last activity timestamp
  in the last post section
- Thread titles on XenForo "What's New" pages (`/whats-new/posts/`) may appear
  slightly differently than on category listing pages — but the structure is the same
- XenForo sometimes shows prefix labels before thread titles (e.g. "[HELP]", "[SOLVED]")
  — include these in the title value as they appear
- Pagination links inside thread items (for threads with many pages: "1 2 3 ... 10")
  appear as small number links after the title — do not include them in the title value
