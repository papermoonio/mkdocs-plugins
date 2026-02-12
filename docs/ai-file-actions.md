# AI File Actions Plugin

The AI File Actions plugin provides reusable UI components and logic for AI-related file actions, such as copying content to the clipboard, downloading files, viewing them, or opening them in AI tools. It is designed to be used by other plugins (like the AI Resources Page plugin) to ensure consistent UI and behavior across the documentation site.

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

**`generate_dropdown_html(url: str, filename: str, exclude: list | None = None) -> str`**

Generates the HTML structure for the AI file actions split-button dropdown.

- **Parameters**:
    - `url` (str): The URL of the file to act upon (e.g., the path to the resolved Markdown file).
    - `filename` (str): The filename to be used when downloading the file.
    - `exclude` (list | None, optional): A list of action IDs to exclude from the dropdown. Defaults to `None` (all actions shown).
- **Returns**: A string containing the HTML markup for the component.

**Example — exclude the View action:**

```python
plugin.generate_dropdown_html(
    url="/ai/llms-full.jsonl",
    filename="llms-full.jsonl",
    exclude=["view-markdown"]
)
```

## Integration

The generated HTML relies on client-side JavaScript (`ai-file-actions.js`) to handle click events and perform the actual actions (fetch, copy, download, open). The JavaScript dispatches based on `data-action-type` attributes (`link` or `clipboard`) set by the plugin, rather than hardcoded action names.
