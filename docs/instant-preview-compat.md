# Instant Preview Compat Plugin

The Instant Preview Compat plugin keeps [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/) instant previews focused on useful article content when pages include extra UI near the title, such as AI page actions, toggle controls, wrappers, badges, or other project-specific blocks.

It preserves the normal page UX while patching the built HTML so previews behave more like a useful section summary.

It handles three cases:

- links without `#`
- links that target the page `h1`
- pages whose article starts with UI instead of clean content flow

## 🔹 Usage

Add the plugin to your `mkdocs.yml`:

```yaml
site_url: https://example.com

theme:
  features:
    - content.tooltips
    - navigation.instant
    - navigation.instant.preview

plugins:
  - page_toggle
  - ai_docs
  - instant_preview_compat
```

`instant_preview_compat` should run after other plugins that mutate the final article markup, because it patches the final article structure and may rewrite internal links for preview compatibility.

The plugin only affects Material instant previews. If `site_url` is missing or those `theme.features` are not enabled, the plugin can still patch the built HTML, but no preview tooltip will be shown.

```yaml
plugins:
  - page_toggle
  - ai_docs
  - instant_preview_compat:
      exclude_selectors:
        - ".hero-actions"
        - ".copy-toolbar"
```

## 🔹 Configuration

### `exclude_selectors`

Default: `[]`

Optional list of extra selectors to mark as preview-excluded.

Use this for project-specific UI that should not lead a preview, such as:

- custom hero action rows
- site-specific copy toolbars
- decorative wrappers that precede the first paragraph
- interactive blocks that are useful on the page but noisy in a tooltip

Built-in exclusions already cover the shared plugin cases handled by this repo:

- `.ai-file-actions-container`
- `.toggle-buttons`

### `rewrite_internal_links`

Default: `true`

When enabled, the plugin rewrites only the links that need preview compatibility. Links to real section headings such as `#h2` / `#h3` are left unchanged.

## 🔹 Notes

- For pages without `#` and links to the page `h1`, the plugin creates a hidden synthetic preview root inside the built article HTML.
- For heading links such as `#h2` / `#h3`, it keeps Material's normal section-based behaviour and only moves excluded UI out of the way.
- For `page_toggle`, it also rewrites non-canonical heading IDs server-side so variant-prefixed anchors exist in the built HTML.
- The plugin does not inject CSS or JavaScript.
