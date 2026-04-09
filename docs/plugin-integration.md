# Plugin Integration & Data Flow

This page documents how the `page_toggle` and `ai_docs` plugins work independently and together, including the full data lifecycle, dependencies, and what a consuming MkDocs project must provide.

---

## `page_toggle` plugin

### What it does

Combines multiple variant pages (e.g. `stable`, `latest`) into a single canonical page with an interactive toggle UI. Non-canonical variant pages are removed from the built site.

### Input

Frontmatter on each page in the group:

```yaml
toggle:
  group: quickstart       # groups pages together — must match across all variants
  variant: stable         # unique identifier for this variant
  label: Stable           # button label (defaults to variant if omitted)
  canonical: true         # marks the page that hosts the toggle UI (one per group)
```

Optional frontmatter for badge and test integration (see [Template requirements](#template-requirements)):

```yaml
page_badges:
  tutorial_badge: Beginner
  test_workflow: my-workflow

page_tests:
  path: tests/path/to/test_file.ts
```

### Data lifecycle

| Hook | What happens |
| :--- | :--- |
| `on_page_content` | Runs for every page. For toggle pages, extracts the H1 and stores it separately, pre-renders the TOC, fixes tabbed element IDs for non-canonical variants, and stores all data in `self.toggle_groups`. Non-canonical pages return empty HTML. The canonical page calls `render_toggle_page` immediately and returns the toggle container HTML. |
| `on_post_build` | Warns if any variants were processed after the canonical page (which would mean the toggle rendered with incomplete data). Deletes non-canonical variant output files from the site. |

### What `render_toggle_page` produces

A self-contained `<div class="toggle-container">` block containing:

- **`.toggle-header`** — one `<span data-variant="...">` per variant holding that variant's H1
- **`.toggle-buttons`** — one `<button class="toggle-btn" data-variant="..." data-filename="..." data-canonical="...">` per variant
- **`<!-- toggle-badges -->`** — a placeholder comment that the template replaces with per-variant badge rows (see [Template requirements](#template-requirements))
- **`.toggle-content`** — one `<div class="toggle-panel" data-variant="..." data-toc-html="...">` per variant holding that variant's full page content. Each panel's HTML also contains a `<!-- toggle-tests-{variant} -->` comment injected immediately before the `<h2 id="where-to-go-next">` section, or at the end of the panel if that section is absent.

It also writes two keys onto the canonical page's `page.meta`:

```python
# Per-variant badge data — (variant, page_badges dict)
page.meta["toggle_variant_metas"] = [
    ("stable", {"tutorial_badge": "Beginner", "test_workflow": "..."}),
    ("latest", {}),
]

# Per-variant test data — (variant, page_tests dict, test_workflow string or None)
page.meta["toggle_variant_test_metas"] = [
    ("stable", {"path": "tests/path/to/test_file.ts"}, "my-workflow"),
    ("latest", {}, None),
]
```

These are the handoff points to the template — they tell the template which variants exist, what badges each one has, and where each variant's test file lives.

### Output

- Canonical page → full toggle container HTML with all variants embedded
- Non-canonical pages → deleted from the built site

---

## `ai_docs` plugin

### What it does

1. Generates the AI resources page (`ai-resources.md`) listing all available LLM artifact files
2. Injects a per-page AI actions widget (copy/download/view) into every built page
3. Generates resolved Markdown files for AI consumption after the build

### Input

- `llms_config.json` — defines project metadata, exclusions, categories, and output paths
- Plugin config in `mkdocs.yml`:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      ai_page_actions: true
      ai_page_actions_anchor: page-header-row   # optional
      ai_page_actions_style: split              # split (default) or dropdown
      ai_page_actions_dropdown_label: "Markdown for LLMs"
```

### Data lifecycle

| Hook | What happens |
| :--- | :--- |
| `on_page_markdown` | Generates AI resources page content for `ai-resources.md`. Skipped for all other pages. |
| `on_post_page` | Injects the AI actions widget into the built HTML for each page. Skipped for excluded pages and the homepage. |
| `on_post_build` | Resolves and writes all Markdown artifact files (per-page `.md` files, category bundles, site index) to the AI output directory. |

### Widget injection (`on_post_page`)

The plugin parses the built HTML with BeautifulSoup and finds `.md-content`, then follows one of three paths:

**Default mode (no `ai_page_actions_anchor`):**

Finds the `<h1>` and wraps it in a flex container:

```html
<div class="h1-ai-actions-wrapper">
  <h1>Page Title</h1>
  <div class="ai-file-actions-container">...</div>
</div>
```

**Anchor mode (`ai_page_actions_anchor` is set):**

Finds every element matching `.{anchor_class}` within `.md-content` and appends the widget into it. The H1 is left untouched.

**Toggle pages in anchor mode:**

For each `.toggle-btn[data-variant]` button within a `.toggle-container`, selects `.{anchor_class}[data-variant="{variant}"]` within that container and injects a widget scoped to that variant's file. The `data-url` is derived from the button's `data-filename` attribute (or the page route if absent).

---

## Using `page_toggle` and `ai_docs` together

### Data flow

```
page_toggle: on_page_content
  → stores variant HTML, H1, TOC per variant
  → calls render_toggle_page on canonical page
  → writes toggle_variant_metas to canonical page.meta
  → returns toggle container HTML (with <!-- toggle-badges --> placeholder)

MkDocs template: content.html
  → reads toggle_variant_metas from page.meta
  → replaces <!-- toggle-badges --> with per-variant .page-header-row[data-variant] elements
  → reads toggle_variant_test_metas from page.meta
  → replaces <!-- toggle-tests-{variant} --> in each panel with the rendered test block (or empty string)
  → renders final page HTML

ai_docs: on_post_page
  → parses final HTML
  → finds .{anchor_class}[data-variant] elements inside toggle containers
  → injects AI widget into each variant's slot with the correct data-url

page_toggle: on_post_build
  → warns if any variants were processed after the canonical page
  → deletes non-canonical output files

ai_docs: on_post_build
  → writes resolved .md artifact files
```

### The placeholder comment contracts

HTML comments are used for all placeholders (rather than real elements) because Python-Markdown can modify elements during processing (adding whitespace or newlines), which would break exact string matches. Comments pass through unmodified.

**`<!-- toggle-badges -->`** — emitted once inside the toggle container, between the header and the content panels. The template replaces it with one `<div class="page-header-row" data-variant="...">` per variant — these elements are what `ai_docs` targets in anchor mode to inject the per-variant AI widget.

**`<!-- toggle-tests-{variant} -->`** — emitted once inside each variant's content panel, immediately before `<h2 id="where-to-go-next">` (or at the end of the panel if that section is absent). The template replaces each one with the rendered test block for that variant (CI badge + "View tests" link), or an empty string if the variant has no `page_tests.path`.

### Why `toggle_variant_metas` and `toggle_variant_test_metas` exist

The `page_toggle` plugin knows which variants exist and what frontmatter each has, but it does not know what CSS classes or HTML structure the consuming project's template uses for badges or test blocks. Rather than hardcoding theme-specific markup, it exposes the raw data via `page.meta` and lets the template decide how to render it.

---

## Template requirements

For the placeholder replacements and badge/test rendering to work, the consuming project must override `content.html` to handle both `toggle_variant_metas` and `toggle_variant_test_metas`. The template needs to:

1. Check for `page.meta.toggle_variant_metas`
2. Build per-variant badge rows with `data-variant` attributes and replace `<!-- toggle-badges -->` in `page.content`
3. Check for `page.meta.toggle_variant_test_metas` and iterate over `(variant, tests, workflow)` tuples
4. For each variant, render the test block (or an empty string) and replace `<!-- toggle-tests-{variant} -->` in the content — use a Jinja2 `namespace` since loop-scoped variable assignments do not propagate to the outer scope
5. Skip the non-toggle `page_tests` injection block when `toggle_variant_metas` is present (to avoid rendering the test block twice on the canonical variant)

Each badge row must carry a `data-variant` attribute matching the variant name so that `ai_docs` can target it in anchor mode:

```html
<div class="page-header-row" data-variant="stable">...</div>
<div class="page-header-row" data-variant="latest">...</div>
```

For non-toggle pages, the template injects a single badge row after the `</h1>` tag, and the test block is injected before `<h2 id="where-to-go-next">` (or appended at the end).

---

## What a consuming project needs

### `mkdocs.yml`

```yaml
plugins:
  - page_toggle
  - ai_docs:
      llms_config: llms_config.json
      ai_page_actions_anchor: page-header-row
      ai_page_actions_style: dropdown
      ai_page_actions_dropdown_label: "Markdown for LLMs"
```

The `ai_page_actions_anchor` value must match the CSS class used in the template's badge row elements.

### `llms_config.json`

Required by `ai_docs`. Defines project metadata, page exclusions, categories, and AI artifact output paths. See [AI Docs](ai-docs.md) for the full schema.

### Template override (`content.html`)

Must handle both `toggle_variant_metas` (to replace `<!-- toggle-badges -->` with per-variant badge rows) and `toggle_variant_test_metas` (to replace each `<!-- toggle-tests-{variant} -->` with the rendered test block). See [Template requirements](#template-requirements) above.

### JavaScript and CSS

The toggle UI requires `toggle-pages.js` and `toggle-pages.css`. See [Page Toggle](page-toggle.md#-extra-js-and-css) for the full files and how to add them to `mkdocs.yml`.
