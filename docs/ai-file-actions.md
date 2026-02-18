# AI File Actions Plugin

The AI File Actions plugin is a thin MkDocs wrapper around the shared [`ai_file_utils`](ai-file-utils.md) library. It provides an entry point for MkDocs plugin discovery and delegates all action resolution and HTML generation to `AIFileUtils`.

## Usage

To use this plugin, add it to your `mkdocs.yml`:

```yaml
plugins:
  - ai_file_actions
```

## Features

### JSON-Driven Dropdown

Dropdown items are driven by the `ai_file_actions.json` schema in the `ai_file_utils` package. Each action in the JSON defines:

- `type` — `"link"` (opens a URL) or `"clipboard"` (copies content)
- `id` — Unique identifier (e.g., `"view-markdown"`, `"download-markdown"`)
- `label` — Display text for the menu item
- `icon` — Inline SVG markup for the item's icon
- `href` — URL template (link-type actions)
- `download` — Filename for download (link-type actions with download behavior)
- `clipboardContent` — Content template (clipboard-type actions)
- `promptTemplate` — Prompt template for AI tool actions
- `analyticsKey` — Analytics event key

To add, remove, or modify dropdown items, edit `ai_file_actions.json`. No plugin code changes are needed.

### API

**`generate_dropdown_html(url, filename, exclude=None, primary_label=None, site_url="")`**

Delegates to [`AIFileUtils.generate_dropdown_html`](ai-file-utils.md#using-in-python-code). See the `ai_file_utils` docs for full parameter and return documentation.

```python
plugin.generate_dropdown_html(
    url="/ai/llms-full.jsonl",
    filename="llms-full.jsonl",
    exclude=["view-markdown"],
    primary_label="Copy file",  # optional label override
    site_url="https://docs.example.com",  # optional, for prompt templates
)
```

## Integration

The generated HTML relies on client-side JavaScript (`ai-file-actions.js`) to handle click events and perform the actual actions (fetch, copy, download, open). The JavaScript dispatches based on `data-action-type` attributes (`link` or `clipboard`) set by the plugin, rather than hardcoded action names.
