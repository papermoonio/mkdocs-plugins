# AI File Utils

The `ai_file_utils` module serves as a centralized "contract" and utility service for defining and resolving actions related to AI artifacts. It allows you to separate the *definition* of actions (like "View Markdown", "Open in ChatGPT") from the *implementation* in the UI.

This is not a standalone MkDocs plugin but a shared library that lives in `helper_lib/ai_file_utils/` (separate from `plugins/`). Other plugins (like `ai_file_actions`, `ai_page_actions`, and `ai_resources_page`) import it to resolve action lists and generate the split-button dropdown HTML for any documentation page.

## 🔹 Usage

Since this is a helper library, you do not need to add it to your `mkdocs.yml` plugins list.

### Using in Python Code

Import the utility class directly in your code.

**`resolve_actions`** takes page context and returns a list of fully resolved action objects:

```python
from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils

utils = AIFileUtils()

actions = utils.resolve_actions(
    page_url="/directory/page.md",
    filename="page.md",
    content="# My Page Content...",
    prompt_page_url="https://docs.example.com/directory/page.md",  # optional
)
```

**`generate_dropdown_html`** renders the split-button dropdown component:

```python
from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils

utils = AIFileUtils()

html = utils.generate_dropdown_html(
    url="/directory/page.md",
    filename="page.md",
    exclude=["view-markdown"],  # optional
    primary_label="Copy page",  # optional
)
```

**Parameters:**

- `url` (str): The URL of the file to act upon.
- `filename` (str): The filename for the download action.
- `exclude` (list | None, optional): Action IDs to exclude from the dropdown. Defaults to `None` (all actions shown).
- `primary_label` (str | None, optional): Override the primary button's label. Defaults to `None` (uses the label from JSON, e.g., "Copy file").
- `site_url` (str, optional): The base site URL (e.g., `"https://docs.polkadot.com/"`). When provided, the fully-qualified URL is built and passed to prompt templates so external services (ChatGPT, Claude) receive a complete address. Defaults to `""`.
- `label_replace` (dict | None, optional): String replacements to apply to dropdown item labels. For example, `{"file": "page"}` changes "View file in Markdown" to "View page in Markdown". Defaults to `None` (labels used as-is from JSON).

**Returns:** An HTML string containing the split-button dropdown. The action marked `primary: true` in the JSON renders as the left-side button; all other actions render as dropdown items.

### Page Exclusion

The `is_page_excluded` method checks whether a page should be excluded from widget injection. It accepts the page's source path, front matter metadata, and optional skip lists from `llms_config.json`:

```python
excluded = utils.is_page_excluded(
    page.file.src_path,
    page.meta,
    skip_basenames=["README.md", "LICENSE.md"],
    skip_paths=["venv", "node_modules"],
)
```

Exclusions are checked in order:

1. **Dot-directories** — any path component starting with `.` (always applied)
2. **`skip_basenames`** — exact filename match
3. **`skip_paths`** — substring match against the source path
4. **Front matter** — the key defined in `pageWidget.frontMatterKey` (default: `hide_ai_actions`)

## Page Widget Configuration

The `pageWidget` section of `ai_file_actions.json` controls front-matter-based exclusion:

```json
{
  "pageWidget": {
    "frontMatterKey": "hide_ai_actions"
  }
}
```

| Field | Type | Description |
| :--- | :--- | :--- |
| `frontMatterKey` | `string` | Front matter key that, when truthy, excludes a page from widget injection. |

Path-based exclusions (`skip_basenames` and `skip_paths`) are defined in `llms_config.json` under `content.exclusions` and passed in by the calling plugin (e.g., `ai_page_actions`).

## Action Model

The core of this module is the **Action Model**, defined in `ai_file_actions.json`. This JSON schema defines what actions are available and how they behave.

### Schema Fields

| Field | Type | Description |
| :--- | :--- | :--- |
| `type` | `string` | The category of action. Currently supports `link` (navigation) and `clipboard` (copy text). |
| `id` | `string` | Unique identifier (e.g., `view-markdown`, `open-chat-gpt`). |
| `label` | `string` | The human-readable text displayed in the UI. |
| `analyticsKey` | `string` | A standardized key for tracking usage events. |
| `href` | `string` | (Link only) The destination URL. Supports interpolation. |
| `download` | `string` | (Link only) If present, triggers a file download with this filename. |
| `clipboardContent` | `string` | (Clipboard only) The text to be copied. |
| `promptTemplate` | `string` | (LLM only) A template used to generate the `{{ prompt }}` variable. |
| `icon` | `string` | Inline SVG markup for the action's icon. |
| `trailingIcon` | `string` | Inline SVG markup rendered after the label (e.g., external-link arrow). |
| `primary` | `boolean` | If `true`, renders as the left-side button instead of a dropdown item. |

### Interpolation Variables

The module supports dynamic injection of context using `{{ variable }}` syntax.

| Variable | Description |
| :--- | :--- |
| `{{ page_url }}` | The URL to the resolved AI artifact. In prompt templates, this is the fully-qualified `prompt_page_url` (e.g., `https://docs.example.com/directory/page.md`). In other fields (`href`, `download`), it is the relative path. |
| `{{ filename }}` | The filename of the markdown file (e.g., `basics.md`). |
| `{{ content }}` | The full text content of the markdown file. |
| `{{ prompt }}` | A special variable generated by processing the `promptTemplate` and URL-encoding the result. |

## 🔹 Adding New Actions

To add a new action (e.g., "Open in Gemini"), you modify `helper_lib/ai_file_utils/ai_file_actions.json`. You do not need to write new Python code.

### Example: Adding a New LLM

```json
{
  "type": "link",
  "id": "open-gemini",
  "label": "Open in Gemini",
  "href": "https://gemini.google.com/app?q={{ prompt }}",
  "promptTemplate": "Read {{ page_url }} and explain it to me.",
  "analyticsKey": "open_page_markdown_gemini"
}
```

This configuration will automatically:
1.  Resolve `{{ page_url }}` in the prompt template (using the fully-qualified `prompt_page_url`).
2.  URL-encode the result into `{{ prompt }}`.
3.  Inject it into the `href`.
