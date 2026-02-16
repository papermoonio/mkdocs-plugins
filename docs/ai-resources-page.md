# AI Resources Page Plugin

The AI Resources Page plugin automates the generation of an "AI Resources" page for your documentation site. It processes a configuration file (`llms_config.json`) to dynamically build an overview section and a table of resources (global files and category bundles) optimized for LLMs.

## Installation

This plugin is included in the `papermoon-mkdocs-plugins` package.

```bash
pip install papermoon-mkdocs-plugins
```

## Configuration

Add the plugin to your `mkdocs.yml`:

```yaml
plugins:
  - ai_resources_page
```

### `llms_config.json`

The plugin relies on an `llms_config.json` file in your project root to determine what content to generate.

Key sections used by this plugin:

- **`project`**:
    - `name`: The name of your project (e.g., "Polkadot"). **Required**.
- **`content`**:
    - `categories_order`: A list of category names to appear in the table.
    - `categories_info`: A dictionary where keys match `categories_order` and values contain metadata like `description`.
- **`outputs`**:
    - `public_root`: The URL path where AI artifacts are served (default: `/ai/`).

#### Example Config

```json
{
  "project": {
    "name": "My Project"
  },
  "content": {
    "categories_order": ["Basics", "Reference"],
    "categories_info": {
      "Basics": {
        "description": "General knowledge base and overview content."
      },
      "Reference": {
        "description": "API references and glossary."
      }
    }
  },
  "outputs": {
    "public_root": "/ai/"
  }
}
```

## How It Works

1.  **Detection**: The plugin hooks into the `on_page_markdown` event and looks for a page named `ai-resources.md` (by filename).
2.  **Generation**:
    *   It replaces the page content with a standard Introduction/Overview using the `project.name`.
    *   It generates a table including:
        *   **Standard Files**: `llms.txt`, `site-index.json`, `llms-full.jsonl`.
        *   **Categories**: Iterates through `categories_order` to create rows for each category bundle, using descriptions from `categories_info`.
3.  **Client-Side Actions**: Each table row includes a split-button dropdown (generated via the shared [`ai_file_utils`](ai-file-utils.md) library) with copy, view, download, and LLM tool actions.

## Notes

- This plugin is designed to work in tandem with the `resolve_md` plugin (which generates the actual artifact files) and the `ai_file_utils` shared library (which provides the dropdown UI). Client-side JavaScript (`ai-file-actions.js`) handles the button actions.
- If `project.name` is missing from `llms_config.json`, the build will fail with an error to prevent incorrect branding.
