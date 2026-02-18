# AI Page Actions Plugin

The AI Page Actions plugin injects a per-page AI actions widget (split-button dropdown) next to each page's H1 heading at build time. It reuses the shared [`ai_file_utils`](ai-file-utils.md) library (in `helper_lib/ai_file_utils/`) for slug resolution, URL building, action resolution, and HTML generation — the same library that powers the table widget via [`ai_file_actions`](ai-file-actions.md).

## Usage

Add the plugin to your `mkdocs.yml`:

```yaml
plugins:
  - ai_page_actions
```

The plugin requires no configuration. Exclusion rules and action definitions are managed centrally in `helper_lib/ai_file_utils/ai_file_actions.json` (see [AI File Utils](ai-file-utils.md)).

## How It Works

The plugin uses the `on_post_page` MkDocs hook, which runs on the fully rendered HTML page after all other content hooks (including `page_toggle`) have finished.

For each page:

1. Checks whether the page is excluded via `ai_file_utils.is_page_excluded()` (configured in `ai_file_actions.json` under `pageWidget`)
2. Parses the rendered HTML with BeautifulSoup to locate the H1 heading inside `.md-content`
3. Builds the slug and `/ai/pages/{slug}.md` URL using `AIFileUtils.build_slug()` and `AIFileUtils.build_ai_page_url()`
4. Generates the widget HTML using `AIFileUtils.generate_dropdown_html()` with `primary_label="Copy page"`
5. Wraps the H1 and widget in a `<div class="h1-ai-actions-wrapper">` flex container

### Toggle Pages

For pages using the `page_toggle` plugin, the widget handles each variant independently. It finds H1s inside `.toggle-header > span[data-variant]` elements and reads the `data-filename` attribute from the corresponding toggle button to build variant-specific slugs via `AIFileUtils.build_toggle_slug()`.

## Page Exclusions

Pages can be excluded from widget injection in two ways, both configured in `ai_file_actions.json`:

- **By source path**: Add the page's source path (or a suffix) to `pageWidget.excludePages`
- **By front matter**: Set the key defined in `pageWidget.frontMatterKey` (default: `hide_ai_actions`) to `true` in the page's front matter

```yaml
---
hide_ai_actions: true
---
```

## Styling

The widget uses the same CSS classes as the table widget (`ai-file-actions.css`). The H1 wrapper layout is controlled by `.h1-ai-actions-wrapper`, which includes mobile responsive styles that stack the H1 and widget vertically on small screens.

## Client-Side Behavior

The widget relies on `ai-file-actions.js` for all client-side interactions (copy, download, dropdown toggle, keyboard navigation, analytics). No additional JavaScript is needed.
