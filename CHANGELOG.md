# Changelog

## 0.1.0a9

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

#### `ai_page_actions` — Widget URL construction changed

The per-page AI actions widget now constructs the resolved markdown URL directly from the page's URL path rather than from a dash-joined slug and the old `/ai/pages/` prefix.

**Impact:**
- No configuration changes required. The widget will automatically point to the new co-located `.md` paths.
- If you have custom JavaScript that reads the `data-url` attribute from the widget and expects the old `/ai/pages/{slug}.md` format, update it to expect the new path format.

#### `ai_file_utils` — Removed helper methods

The following static methods have been removed from `AIFileUtils`:

| Method | Reason |
| :--- | :--- |
| `build_slug(page_url)` | No longer used; URLs are now derived directly from `page.url` |
| `build_toggle_slug(page_url, data_filename)` | Same as above |
| `build_ai_page_url(slug)` | Hardcoded `/ai/pages/` prefix no longer applies |

**Impact:**
- Any code that calls these methods will raise `AttributeError` and must be updated. Replace calls with direct path construction from the page URL (e.g., `page.url.strip("/") + ".md"`).

### Bug Fixes

#### `resolve_md` — Category matching now slug-normalized

`select_pages_for_category` previously used a plain case-insensitive string comparison, causing multi-word categories to silently produce empty bundles and light files when the `categories_info` key format (e.g., `smart-contracts`) differed from the page front-matter value (e.g., `smart contracts`). Both sides are now normalized through `slugify_category` before comparison, so hyphens, spaces, and underscores are treated as equivalent.

### New Features

#### Category light files

Each `categories/<slug>-light.md` is a compact navigational index for a category. It contains only the pages explicitly tagged with that category (no base-category union) and is intended as a fast discovery reference for humans and LLMs alike.

**Front matter** — aggregated from the category's page set:

```yaml
---
category: Smart Contracts
description: Guides and references for writing, deploying, and auditing smart contracts.
page_count: 12
token_estimate: 3800
updated: 2026-03-17T14:36:50Z
---
```

**Per-page entry** — one block per page, separated by `---`:

```markdown
## Smart Contract Overview
https://docs.example.org/smart-contracts/overview/

An introduction to smart contracts, how they work, and when to use them...

### Sections
- What Is a Smart Contract `#what-is-a-smart-contract`
- Lifecycle of a Contract `#lifecycle-of-a-contract`
- Security Considerations `#security-considerations`
```

The `### Sections` block is omitted for pages that have no outline headings.

#### `ai_resources_page` — Category light files added to AI resources table

Each category now has two rows in the AI resources table — the full bundle (`<slug>.md`) followed by its lightweight index (`<slug>-light.md`).