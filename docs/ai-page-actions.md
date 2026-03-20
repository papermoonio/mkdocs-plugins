# AI Page Actions Plugin

The AI Page Actions plugin injects a per-page AI actions widget (split-button dropdown) next to each page's H1 heading at build time. It reuses the shared [`ai_file_utils`](helper_library/ai-file-utils.md) library (in `helper_lib/ai_file_utils/`) for action resolution and HTML generation — the same library that powers the table widget via [`ai_file_actions`](helper_library/ai-file-actions.md).

## Usage

Add the plugin to your `mkdocs.yml`:

```yaml
plugins:
  - ai_page_actions
```

The plugin requires no configuration in `mkdocs.yml`. It automatically reads page exclusion rules from the site's `llms_config.json` (the same file used by `resolve_md`). Action definitions are managed in `helper_lib/ai_file_utils/ai_file_actions.json` (see [AI File Utils](helper_library/ai-file-utils.md)).

## How It Works

The plugin uses the `on_post_page` MkDocs hook, which runs on the fully rendered HTML page after all other content hooks (including `page_toggle`) have finished.

For each page:

1. Checks whether the page is excluded via `ai_file_utils.is_page_excluded()` (driven by `llms_config.json` exclusions, dot-directories, and front matter)
2. Parses the rendered HTML with BeautifulSoup to locate the H1 heading inside `.md-content`
3. Builds the URL for the resolved markdown file, which lives at the same path as the HTML page with a `.md` extension (e.g., `smart-contracts/overview/` → `/smart-contracts/overview.md`). For sites deployed under a subpath (e.g., `site_url: https://example.com/docs/`), the path prefix is extracted and prepended automatically (e.g., `/docs/smart-contracts/overview.md`)
4. Generates the widget HTML using `AIFileUtils.generate_dropdown_html()` with `primary_label="Copy page"` and `label_replace={"file": "page"}` so dropdown items read "View page in Markdown" etc.
5. Wraps the H1 and widget in a `<div class="h1-ai-actions-wrapper">` flex container

### Toggle Pages

For pages using the `page_toggle` plugin, the widget handles each variant independently. It finds H1s inside `.toggle-header > span[data-variant]` elements and reads the `data-filename` attribute from the corresponding toggle button to build the variant's markdown URL (e.g., the variant filename appended to the page's directory path).

## Page Exclusions

The plugin determines which pages to skip using the same exclusion rules that `resolve_md` uses to decide which pages get AI artifact files. This ensures the widget is never rendered on pages that have no AI files to serve. Exclusions are checked in the following order:

1. **Dot-directories**: Any page whose source path includes a directory starting with `.` (e.g., `.snippets/`, `.github/`) is always excluded automatically.
2. **`skip_basenames`**: Pages whose filename exactly matches an entry in `content.exclusions.skip_basenames` from `llms_config.json` are excluded (e.g., `README.md`, `LICENSE.md`).
3. **`skip_paths`**: Pages whose source path contains a `content.exclusions.skip_paths` substring from `llms_config.json` are excluded (e.g., `venv`, `node_modules`).
4. **Front matter**: Set `hide_ai_actions: true` in a page's front matter for a one-off override.

```yaml
---
hide_ai_actions: true
---
```

The plugin loads `llms_config.json` from the project root (the directory containing `mkdocs.yml`) during the `on_config` hook. If the file is missing, the plugin logs a warning and falls back to dot-directory and front-matter checks only.

## Styling

The widget uses the same CSS classes as the table widget (`ai-file-actions.css`). The H1 wrapper layout is controlled by `.h1-ai-actions-wrapper`, which includes mobile responsive styles that stack the H1 and widget vertically on small screens.

## Client-Side Behavior

The widget relies on `ai-file-actions.js` for all client-side interactions (copy, download, dropdown toggle, keyboard navigation, analytics). No additional JavaScript is needed.
