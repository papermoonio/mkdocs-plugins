# Changelog

## 0.1.0a13

### New Features

#### `ai_docs` — Agent skills

Generates structured, agent-ready skill files from a JSON configuration. Set `agent_skills_config` in your `mkdocs.yml` to enable:

```yaml
plugins:
  - ai_docs:
      agent_skills_config: agent_skills_config.json
```

For each skill defined in the config, the plugin writes a `{skill_id}.md` file to `ai/skills/` with YAML front matter and structured Markdown sections. An accompanying `skills-index.md` lists all skills and is surfaced in the aggregate table on the AI Resources page.

**Skill front matter** includes `name` (title), `description`, and optionally `version`, `chain_role`, `invocation`, `license`, `compatibility`, and a `metadata` block with `workflow_pattern` and `generated` timestamp.

**Rendered body sections** (each conditional on the skill config):

- `## Prerequisites`
- `## Project Structure`
- `## Environment Variables`
- `## Execution Steps`
- `## Reference Code Index`
- `## Examples` — numbered subsections with trigger phrase, action list, and result
- `## Error Recovery`
- `## Supplementary Context`

**Page widget injection:** each skill maps to a single documentation page via `primary_page`. The plugin injects a skills dropdown widget on that page alongside the Markdown for LLMs widget.

**New configuration options:**

- **`agent_skills_config`**: Path to the skills config JSON, relative to `mkdocs.yml`. Skills are enabled when this is set and the file exists.
- **`ai_skills_dropdown_label`**: Label text for the skills dropdown trigger button. Defaults to `"Agent skill"`.

## 0.1.0a11

### New Features

#### `ai_docs` — Configurable page actions style and anchor

Three new configuration options are available under the `ai_docs` plugin:

- **`ai_page_actions_anchor`**: A CSS class name that scopes where the per-page AI actions widget is injected. When set, the plugin looks for an element with that class inside the toggle container (matched by `data-variant`) rather than wrapping the H1. Useful when the template renders its own anchor slots.
- **`ai_page_actions_style`**: Controls the widget presentation. Accepts `"split"` (default, a primary button with a dropdown arrow) or `"dropdown"` (a single button that opens a full dropdown menu).
- **`ai_page_actions_dropdown_label`**: Sets the label text shown on the dropdown trigger button when `ai_page_actions_style` is `"dropdown"`.

### Bug Fixes

#### `ai_docs` — `{target=\_blank}` stripped from resolved markdown output

Resolved markdown files no longer contain `{target=\_blank}` attribute syntax. This attribute is unnecessary in plain markdown output, and when the `.jsonl` bundle is serialised via `json.dumps` the JSON spec requires every backslash to be escaped — turning `\_blank` in the source into `\\_blank` in the file. Removing the attribute at resolution time eliminates the escaping issue entirely.

## 0.1.0a10

### Bug Fixes

#### `ai_docs` — AI resources table placeholder now survives all markdown processors

The placeholder used to inject the AI resources table was a raw HTML `<div>` element. Some environments caused Python-Markdown to emit the element with a newline inside (`<div>\n</div>`), which prevented the exact string match in `on_post_build` from finding it — leaving an empty div on the page instead of the table. The placeholder has been changed to an HTML comment (`<!-- ai-resources-aggregate-table -->`), which passes through markdown processing and HTML serialization completely unchanged.

## 0.1.0a9

### New Features

#### `ai_docs` — Unified AI documentation plugin

`resolve_md`, `ai_page_actions`, and `ai_resources_page` have been consolidated into a single `ai_docs` plugin. The three separate plugin entries in `mkdocs.yml` are replaced by one block:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      ai_resources_page: true  # default, opt out to disable
      ai_page_actions: true    # default, opt out to disable
```

- Core artifact generation (resolved pages, category bundles, site index, `llms.txt`) always runs when the plugin is enabled.
- `ai_resources_page` and `ai_page_actions` are feature flags that can be set to `false` to disable individual UI features without disabling the whole plugin.
- `llms_config` now defaults to `"llms_config.json"` rather than being required.
- The old `resolve_md`, `ai_page_actions`, and `ai_resources_page` plugins remain available in this release for backward compatibility. They are deprecated and will be removed in a future major release.

#### `ai_docs` — Lightweight category index files

Each category now generates a `{slug}-light.md` file alongside the full `{slug}.md` bundle. The light file contains titles, resolved markdown URLs, content previews, and section headings for every page in the category — without full page content. This gives a compact, navigable index suited for smaller context windows. Light files are listed in the AI resources table alongside their full bundle counterparts.

#### `ai_docs` — MCP connection section on AI Resources page

When `mcp_name` and `mcp_url` are configured in the `project` section of `llms_config.json`, the AI Resources page now includes a **Connect via MCP** section with:

- One-click install buttons for **Cursor** and **VS Code** (deeplinks)
- Copy-able terminal commands for **Claude Code CLI** and **Codex CLI**
- A setup guide link for **Claude Desktop**

#### `ai_docs` — Token estimates in AI resources table

The AI resources table now includes a **Token Estimate** column. Category bundle counts are read from each bundle's front matter (the authoritative value written at build time). Counts for `llms.txt`, `site-index.json`, and `llms-full.jsonl` are estimated from their built content using the same heuristic estimator applied elsewhere.

### Breaking Changes

#### `resolve_md` — Resolved markdown files moved to page-level paths

Resolved markdown files are no longer written to a dedicated `/ai/pages/` directory. They now live **at the same URL path as their corresponding HTML pages**, with a `.md` extension.

**Before:**
```
docs.example.com/ai/pages/smart-contracts-overview.md
```

**After:**
```
docs.example.com/smart-contracts/overview.md
```

**Impact:**
- Any external links, scripts, or integrations that reference the old `/ai/pages/{slug}.md` URL pattern will break and must be updated.
- The `repository.ai_artifacts_path` and `outputs.files.pages_dir` config options in `llms_config.json` no longer control where individual page `.md` files are written. The `outputs.public_root` setting still controls where category bundles, the site index, and `llms.txt` are written (defaulting to `/ai/`).
- The `raw_md_url` field in `ai-site-index.json` and the links in category bundles and `llms.txt` now point to the new paths.

### Changes

#### `ai_page_actions` — Widget URL construction changed

The per-page AI actions widget now constructs the resolved markdown URL directly from the page's URL path rather than from a dash-joined slug and the old `/ai/pages/` prefix. No configuration changes required — the widget will automatically point to the new co-located `.md` paths.

#### `ai_file_utils` — Removed unused helper methods

The following static methods have been removed from `AIFileUtils` as they are no longer used internally:

| Method | Reason |
| :--- | :--- |
| `build_slug(page_url)` | No longer used; URLs are now derived directly from `page.url` |
| `build_toggle_slug(page_url, data_filename)` | Same as above |
| `build_ai_page_url(slug)` | Hardcoded `/ai/pages/` prefix no longer applies |
