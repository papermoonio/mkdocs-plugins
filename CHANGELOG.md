# Changelog

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
- The `resolved_md_url` field in `ai-site-index.json` and the links in category bundles and `llms.txt` now point to the new paths.

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
