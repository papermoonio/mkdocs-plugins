# AI File Actions Plugin

The AI File Actions plugin provides reusable UI components and logic for AI-related file actions, such as copying content to the clipboard, downloading files, or viewing them. It is designed to be used by other plugins (like the AI Resources Page plugin) to ensure consistent UI and behavior across the documentation site.

## Usage

To use this plugin, add it to your `mkdocs.yml`:

```yaml
plugins:
  - ai_file_actions
```

## Features

### Dropdown Action Component

The plugin provides a method to generate a consistent dropdown menu component for file actions. This component currently supports:

- **Copy**: Copying the file content to the clipboard.
- **View**: Opening the file in a new browser tab.
- **Download**: Downloading the file to the user's device.

### API

**`generate_dropdown_html(url: str, filename: str) -> str`**

Generates the HTML structure for the AI file actions split-button dropdown.

- **Parameters**:
    - `url` (str): The URL of the file to act upon (e.g., the path to the resolved Markdown file).
    - `filename` (str): The filename to be used when downloading the file.
- **Returns**: A string containing the HTML markup for the component.

## Integration

The generated HTML relies on client-side JavaScript to handle the click events and perform the actual actions (fetch, copy, download). The HTML structure uses specific classes (`copy-to-llm`, `ai-resources-action`, etc.) that the JavaScript handlers target.
