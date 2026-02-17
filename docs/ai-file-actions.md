# AI File Actions

`ai_file_actions` is a shared library (in `lib/ai_file_actions/`) that provides a convenience wrapper around [`ai_file_utils`](ai-file-utils.md). It delegates all action resolution and HTML generation to `AIFileUtils`.

This is **not** a standalone MkDocs plugin. It does not need to be added to `mkdocs.yml`.

## Usage

Import and use directly in Python code:

```python
from lib.ai_file_actions.plugin import AiFileActionsPlugin

actions = AiFileActionsPlugin()
html = actions.generate_dropdown_html(
    url="/ai/llms-full.jsonl",
    filename="llms-full.jsonl",
    exclude=["view-markdown"],
)
```

## JSON-Driven Dropdown

Dropdown items are driven by the `ai_file_actions.json` schema in the shared `lib/ai_file_utils/` library. Each action in the JSON defines:

- `type` — `"link"` (opens a URL) or `"clipboard"` (copies content)
- `id` — Unique identifier (e.g., `"view-markdown"`, `"download-markdown"`)
- `label` — Display text for the menu item
- `icon` — Inline SVG markup for the item's icon
- `href` — URL template (link-type actions)
- `download` — Filename for download (link-type actions with download behavior)
- `clipboardContent` — Content template (clipboard-type actions)
- `promptTemplate` — Prompt template for AI tool actions
- `analyticsKey` — Analytics event key

To add, remove, or modify dropdown items, edit `lib/ai_file_utils/ai_file_actions.json`. No code changes are needed.

## Integration

The generated HTML relies on client-side JavaScript (`ai-file-actions.js`) to handle click events and perform the actual actions (fetch, copy, download, open). The JavaScript dispatches based on `data-action-type` attributes (`link` or `clipboard`) set by the library, rather than hardcoded action names.
