# Instant Preview Plugin

The Instant Preview plugin generates build-time preview data for internal links. It is independent from Material for MkDocs' `navigation.instant` and works with normal full-page navigation.

The plugin reads the final built HTML, extracts preview-safe fragments, and injects a hidden manifest plus `<template>` elements into each page. A consuming site must provide the JavaScript and CSS that render those previews.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml`:

```yaml
plugins:
  - instant_preview
```

Add your site's preview runtime as a normal MkDocs asset:

```yaml
extra_javascript:
  - js/instant-preview.js
```

The plugin does not ship or inject runtime JavaScript or CSS. It only generates the data that the runtime consumes.

## 🔹 Configuration

Most sites can use the default configuration. The optional settings are:

- **`exclude_selectors`**:
  - Optional.
  - Adds site-specific CSS selectors to the plugin's built-in exclusion rules.
  - Use it for custom widgets or controls that should never appear in previews.

- **`preserve_selectors`**:
  - Optional.
  - Adds site-specific CSS selectors to the plugin's built-in preservation rules.
  - Use it for stable custom blocks that already render correctly inside the preview shell.

Example with site-specific customization:

```yaml
plugins:
  - instant_preview:
      exclude_selectors:
        - .my-site-widget
      preserve_selectors:
        - .my-site-summary
```

## 🔹 Preview Content

The plugin generates previews keyed by clean internal URLs:

- Page root: `/page/`
- Heading: `/page/#heading`
- Toggle variant root: `/page/#variant`
- Toggle variant heading: `/page/#variant-heading`

Root previews include the page `h1`, useful prelude content, and the first useful section. Section previews are shorter and start from the target heading.

The extractor keeps previews static and safe. It excludes non-portable UI such as AI action widgets, feedback controls, source footers, toggle buttons, forms, scripts, styles, and copy controls. It preserves common documentation blocks such as `page-header-row`, `status-badge`, `button-wrapper`, admonitions, and tabbed content.

Tables, cards, code blocks, terminal output, images, and details blocks are normalized into static preview-safe markup.

## 🔹 Notes

- The plugin runs late in `on_post_build`, after other plugins and theme rendering have produced the final HTML.
- Preview link scope is fixed to `article`, which avoids breadcrumbs, navigation, headers, and sidebars.
- Do not enable `navigation.instant` or `navigation.instant.preview` for this plugin. They are not required.
