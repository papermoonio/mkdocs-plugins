# AI Docs Plugin

The AI Docs plugin consolidates [`resolve_md`](resolve-md.md), [`ai_page_actions`](ai-page-actions.md), and [`ai_resources_page`](ai-resources-page.md) into a single plugin. It generates AI-ready artifacts from your documentation (resolved markdown files, category bundles, site index, and `llms.txt`) and optionally injects a per-page actions widget and generates an AI resources page.

> ⚠️ **Deprecation notice:**
>
> The individual `resolve_md`, `ai_page_actions`, and `ai_resources_page` plugins are deprecated and kept only for backward compatibility. Migrate to `ai_docs` at your convenience — they will be removed in a future major release.

## Usage

Replace the three separate plugin entries in your `mkdocs.yml` with a single `ai_docs` block:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
```

Both `ai_resources_page` and `ai_page_actions` are enabled by default. To opt out of either feature:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      ai_resources_page: false
      ai_page_actions: false
```

## Configuration

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `llms_config` | `string` | `llms_config.json` | Path to the LLM config file, relative to `mkdocs.yml`. |
| `ai_resources_page` | `bool` | `true` | Generate the AI resources page from `ai-resources.md`. Set to `false` to disable. |
| `ai_page_actions` | `bool` | `true` | Inject the per-page AI actions widget next to each H1. Set to `false` to disable. |
| `ai_page_actions_anchor` | `string` | `""` | CSS class name of the element(s) to append the widget into instead of wrapping the H1. When set, the default H1-wrapping behavior is replaced — see [Custom anchor](#custom-anchor). |
| `ai_page_actions_style` | `string` | `"split"` | Widget layout style. `"split"` renders a copy button left of the dropdown arrow; `"dropdown"` renders a single labelled button with all actions inside — see [Widget style](#widget-style). |
| `ai_page_actions_dropdown_label` | `string` | `"Markdown for LLMs"` | Trigger button label when `ai_page_actions_style` is `"dropdown"`. |
| `enabled` | `bool` | `true` | Disable the entire plugin (all features). Supports `!ENV` for environment-based toggling. |

The `llms_config` file controls content filtering, category definitions, and output paths. See [Resolve Markdown](resolve-md.md#-configuration) for a full breakdown of the `llms_config.json` schema.

## Features

### Artifact generation

Always runs when the plugin is enabled. Processes every documentation markdown file to:

- Resolve variable (`{{ variable }}`) and snippet (`--8<--`) placeholders
- Strip HTML comments
- Write resolved `.md` files alongside their corresponding HTML pages in the build output
- Generate per-category bundle files under `ai/categories/`
- Generate `site-index.json` and `llms-full.jsonl` under `ai/`
- Generate `llms.txt` at the site root

### AI page actions (`ai_page_actions`)

Injects an AI actions widget (split-button by default, or plain dropdown via `ai_page_actions_style`) next to each page's H1 heading at build time. The widget lets readers copy, download, or open the page's resolved markdown in an LLM tool. Pages listed in `llms_config.json` exclusions, dot-directories, and pages with `hide_ai_actions: true` in their front matter are automatically skipped.

See [AI Page Actions](ai-page-actions.md) for details on exclusion rules, toggle page handling, and styling.

#### Widget style

The widget supports two layout styles, controlled by `ai_page_actions_style`.

**`split`** (default) — a copy button sits to the left of a chevron trigger that opens the dropdown:

```yaml
plugins:
  - ai_docs:
      ai_page_actions_style: split   # default, same as omitting the option
```

**`dropdown`** — a single labelled button opens a menu that contains all actions, including copy. No separate copy button is rendered outside the menu:

```yaml
plugins:
  - ai_docs:
      ai_page_actions_style: dropdown
      ai_page_actions_dropdown_label: Markdown for LLMs   # default
```

The container gets the additional CSS class `ai-file-actions-container--dropdown` so you can style the two modes independently. Resources table widgets always carry `ai-file-actions-container--table`. See [Styling](ai-page-actions.md#styling) for the full class reference and CSS examples.

#### Custom anchor

By default, the widget is placed by wrapping the H1 in a `<div class="h1-ai-actions-wrapper">` flex container. If your theme or custom layout already has a dedicated slot for page-level actions, you can redirect the widget there instead:

```yaml
plugins:
  - ai_docs:
      ai_page_actions_anchor: my-page-actions
```

The plugin then finds every element that has the class `my-page-actions` within `.md-content` and appends the widget into it, leaving the H1 untouched. If no matching element is found on a given page, the page is left unchanged and a debug message is logged. Toggle-page variant handling is not applied in anchor mode — the widget always uses the page's own `.md` path.

### AI resources page (`ai_resources_page`)

Automatically generates the content for a page named `ai-resources.md`, replacing it with a table listing all available LLM artifact files (global indexes and per-category bundles) with copy, view, and download actions.

See [AI Resources Page](ai-resources-page.md) for details on the generated content and `llms_config.json` requirements.

## Notes

- All three features share a single `llms_config.json` load — the file is read once per build and cached.
- Disabling `ai_resources_page` or `ai_page_actions` skips only those hooks; artifact generation always runs.
- The plugin registers under the `ai_docs` entry point. The deprecated `resolve_md`, `ai_page_actions`, and `ai_resources_page` entry points remain registered and functional until removed.
