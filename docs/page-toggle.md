# Page Toggle Plugin

The Page Toggle plugin for MkDocs allows you to create variant pages for the same content and display them with an interactive toggle interface. This is useful when you need to present the same documentation in different formats, frameworks, or languages while keeping everything on a single canonical page.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml`:

```yaml
plugins:
  - page_toggle
```

Then define toggle groups in your page frontmatter. For each toggle group, you need:

- **One canonical page**: The main page that will display the toggle interface.
- **One or more variant pages**: Alternative versions that will be embedded in the toggle.

### Example: Framework Variants

Create multiple pages for the same content with different implementations:

**docs/quickstart-react.md** (canonical):
```yaml
---
toggle:
  group: quickstart
  variant: react
  label: React
  canonical: true
---

# Quickstart

Here's how to get started with React...
```

**docs/quickstart-vue.md**:
```yaml
---
toggle:
  group: quickstart
  variant: vue
  label: Vue
---

# Quickstart

Here's how to get started with Vue...
```

The plugin will:

- Render all variants on the canonical page with toggle buttons.
- Remove the standalone variant pages from the built site.
- Preserve unique anchor IDs for each variant's content.
- Handle tabbed content blocks properly for each variant.

## 🔹 Configuration

### Frontmatter Options

Each page in a toggle group must define the following in its YAML frontmatter:

- **`toggle.group` (required)**: The name of the toggle group. All pages with the same group name will be combined.

- **`toggle.variant` (required)**: A unique identifier for this variant within the group (e.g., `react`, `vue`, `python3`).

- **`toggle.label`** (optional): Display text for the toggle button. Defaults to the `variant` value if not specified.

- **`toggle.canonical`** (optional): Set to `true` to mark this as the canonical page where all variants will be displayed. Defaults to `false`.
  - Only one page per group should have `canonical: true`
  - The canonical page determines the URL and navigation entry

## 🔹 Features

### Toggle Interface

The canonical page displays:

- **Toggle buttons** at the top for switching between variants.
- **All variant content** embedded in the page, with only the active variant visible.
- **Synchronized table of contents** that updates based on the selected variant.

### URL Handling

- The canonical page is accessible at its normal URL.
- Variant pages are removed from the site output to avoid duplicate content.
- The canonical page URL remains unchanged when switching variants.

### Anchor ID Prefixing

For non-canonical variants, all anchor IDs are automatically prefixed with the variant name to prevent conflicts. For example:

- **Canonical**: `#installation`
- **React variant**: `#react-installation`
- **Vue variant**: `#vue-installation`

This ensures deep linking works correctly for all variants.

### Tabbed Content Handling

The plugin automatically fixes tabbed content blocks (from the [PyMdown Extensions Tabbed](https://facelessuser.github.io/pymdown-extensions/extensions/tabbed/) extension) in non-canonical variants by:

- Prefixing all radio input IDs and names with the variant identifier.
- Updating label `for` attributes to match the new IDs.
- Ensuring each variant's tabs work independently.

## 🔹 Notes

- All pages in a toggle group must define both `group` and `variant` in their frontmatter.
- Each group must have exactly one canonical page; defining multiple canonical pages will raise an error.
- Non-canonical variant pages will not appear in the site navigation or as standalone pages.
- The plugin preserves the full content and structure of each variant, including code blocks, images, and other Markdown features.
- Toggle state is preserved when navigating within the same page (via table of contents links).

## 🔹 Example Use Cases

- **Multi-language tutorials**: Show the same tutorial in Python, JavaScript, and Go.
- **Framework comparisons**: Display equivalent code for React, Vue, and Angular.
- **Platform-specific guides**: Provide separate instructions for Windows, macOS, and Linux.
- **Version variants**: Show documentation for different versions of an API or library.
