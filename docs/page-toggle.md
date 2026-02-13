# Page Toggle Plugin

The Page Toggle plugin for MkDocs allows you to create variant pages for the same content and display them with an interactive toggle interface. This is useful when you need to present the same documentation in different formats, frameworks, or languages while keeping everything on a single canonical page.

## 🔹 Usage

To use this plugin, you'll need to take the following steps:

1. Enable the plugin in your `mkdocs.yml`:

    ```yaml
    plugins:
      - page_toggle
    ```

2. [Define toggle groups](#-configuration) in your page frontmatter. For each toggle group, you need:

    - **One canonical page**: The main page that will display the toggle interface.
    - **One or more variant pages**: Alternative versions that will be embedded in the toggle.

3. Add the [extra JavaScript and CSS](#-extra-js-and-css) required to make the toggle work.

4. Customize the JavaScript and CSS as needed.

## 🔹 Configuration

Each page in a toggle group must define the following in its YAML frontmatter:

- **`toggle.group` (required)**: The name of the toggle group. All pages with the same group name will be combined.

- **`toggle.variant` (required)**: A unique identifier for this variant within the group (e.g., `react`, `vue`, `python3`).

- **`toggle.label`** (optional): Display text for the toggle button. Defaults to the `variant` value if not specified.

- **`toggle.canonical`** (optional): Set to `true` to mark this as the canonical page where all variants will be displayed. Defaults to `false`.
  - Only one page per group should have `canonical: true`.
  - The canonical page determines the URL and navigation entry.

### Example: Framework Variants

Create multiple pages for the same content with different implementations:

**docs/quickstart.md** (canonical):

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

## 🔹 Extra JS and CSS

The toggle functionality requires the following JavaScript and CSS files to work properly.

### JavaScript

<details>
<summary>toggle-pages.js</summary>

```javascript
function updateToggleSlider(container) {
  const buttons = container.querySelectorAll('.toggle-btn');
  if (!buttons.length) return;

  // Create the slider element if it doesn't exist
  let sliderEl = container.querySelector('.toggle-slider');
  if (!sliderEl) {
    sliderEl = document.createElement('div');
    sliderEl.className = 'toggle-slider';
    container.querySelector('.toggle-buttons').prepend(sliderEl);
  }

  const activeBtn = container.querySelector('.toggle-btn.active');
  if (!activeBtn) return;

  // Calculate position relative to the container
  const btnRect = activeBtn.getBoundingClientRect();
  const containerRect = container
    .querySelector('.toggle-buttons')
    .getBoundingClientRect();

  sliderEl.style.width = btnRect.width + 'px';
  sliderEl.style.transform = `translateX(${
    btnRect.left - containerRect.left
  }px)`;
}

document.addEventListener('DOMContentLoaded', () => {
  const containers = document.querySelectorAll('.toggle-container');
  const containerStates = new Map(); // Store setState functions for each container

  containers.forEach((container) => {
    // Initial slider update
    updateToggleSlider(container);

    const buttons = container.querySelectorAll('.toggle-btn');
    const panels = container.querySelectorAll('.toggle-panel');
    const h1Headers = container.querySelectorAll('.toggle-header > span');

    if (!buttons.length || !panels.length || !h1Headers.length) return;

    // Determine canonical variant
    const canonicalButton = Array.from(buttons).find(
      (b) => b.dataset.canonical === 'true'
    );
    const canonicalVariant = canonicalButton
      ? canonicalButton.dataset.variant
      : buttons[0].dataset.variant;

    // -----------------------------
    // Assign normalized IDs
    // -----------------------------
    const setHeaderId = (header, text, variant) => {
      const baseId = text.trim()
        .toLowerCase()
        .replace(/\s+/g, '-')
        .replace(/[^\w\-]/g, '');
      
      const isCanonical = variant === canonicalVariant;
      const fullId = isCanonical ? baseId : `${variant}-${baseId}`
      header.id = fullId;

      const link = header.querySelector('a, .headerlink');
      if (link) {
        link.setAttribute('href', `#${fullId}`);
      }
    };

    // Process headers inside panels
    panels.forEach((panel) => {
      const variant = panel.dataset.variant;

      const headers = panel.querySelectorAll('h1, h2, h3, h4, h5, h6');
      headers.forEach((h) => {
        // Get text content excluding child elements like .headerlink
        const text = Array.from(h.childNodes)
          .filter((n) => n.nodeType === Node.TEXT_NODE)
          .map((n) => n.textContent)
          .join('');

        setHeaderId(h, text, variant);
      });
    });

    // Process h1 headers outside panels (.toggle-header > span)
    h1Headers.forEach((span) => {
      const variant = span.dataset.variant;
      if (!variant) return;
      
      const h1 = span.querySelector('h1');
      if (!h1) return;
      
      setHeaderId(h1, h1.textContent, variant);
    });

    // -----------------------------
    // TOC injection
    // -----------------------------
    const originalCanonicalTOC = document.querySelector(
      'nav.md-nav.md-nav--secondary'
    )?.outerHTML;

    function swapTOC(variant) {
      const allSidebars = document.querySelectorAll(
        'nav.md-nav.md-nav--secondary'
      );

      if (!allSidebars.length) {
        console.error('[toggle] No sidebar found');
        return;
      }

      // If switching to canonical, restore original TOC
      if (variant === canonicalVariant) {
        if (originalCanonicalTOC) {
          allSidebars.forEach((sidebar) => {
            const temp = document.createElement('div');
            temp.innerHTML = originalCanonicalTOC;
            const clone = temp.firstElementChild;
            if (clone) {
              sidebar.parentNode.replaceChild(clone, sidebar);
            }
          });
        }
        return;
      }

      const panel = container.querySelector(
        `.toggle-panel[data-variant="${variant}"]`
      );
      if (!panel || !panel.dataset.tocHtml) return;

      // Replace all matching sidebars
      allSidebars.forEach((sidebar) => {
        const temp = document.createElement('div');
        temp.innerHTML = panel.dataset.tocHtml;
        const newSidebar = temp.firstElementChild;

        if (newSidebar) {
          sidebar.parentNode.replaceChild(newSidebar, sidebar);
        }
      });
    }

    // -----------------------------
    // State management
    // -----------------------------
    function getInitialVariant() {
      const hash = window.location.hash.slice(1);
      
      // Check if hash is a variant name directly
      const isValidVariant = [...buttons].some(
        (b) => b.dataset.variant === hash
      );
      if (isValidVariant) return hash;
      
      // Check if hash is a section ID that starts with a variant prefix
      for (const button of buttons) {
        const variant = button.dataset.variant;
        if (variant !== canonicalVariant && hash.startsWith(`${variant}-`)) {
          return variant;
        }
      }
      
      // Default to canonical
      return canonicalVariant;
    }

    let currentVariant = getInitialVariant();

    function setState(variant, updateUrl = true) {
      currentVariant = variant;

      // Update all UI based on state
      buttons.forEach((b) =>
        b.classList.toggle('active', b.dataset.variant === variant)
      );
      panels.forEach((p) =>
        p.classList.toggle('active', p.dataset.variant === variant)
      );
      h1Headers.forEach((h) =>
        h.classList.toggle('active', h.dataset.variant === variant)
      );

      swapTOC(variant);
      updateToggleSlider(container);

      // Only update URL if requested (to preserve section hashes)
      if (updateUrl) {
        if (variant === canonicalVariant) {
          history.replaceState(null, '', window.location.pathname);
        } else {
          window.location.hash = variant;
        }
      }
    }

    // Initialize state without changing the URL (preserve section links)
    setState(currentVariant, false);

    // Store the setState function and related data for this container
    containerStates.set(container, {
      setState,
      getInitialVariant,
      canonicalVariant
    });

    // -----------------------------
    // Toggle click handler
    // -----------------------------
    buttons.forEach((btn) => {
      btn.addEventListener('click', () => {
        setState(btn.dataset.variant);
      });
    });
  });

  // -----------------------------
  // Handle browser back/forward and URL changes (global listener)
  // -----------------------------
  window.addEventListener('hashchange', () => {
    // Re-check all containers to see if variant should change
    containerStates.forEach(({ setState, getInitialVariant, canonicalVariant }, container) => {
      const newVariant = getInitialVariant();

      // Get the current active button to determine current state
      const activeBtn = container.querySelector('.toggle-btn.active');
      const currentVariant = activeBtn?.dataset.variant || canonicalVariant;

      // Only update if variant actually changed, preserve the section hash
      if (newVariant !== currentVariant) {
        setState(newVariant, false);
        
        // After state updates, manually scroll to the hash target
        const hash = window.location.hash.slice(1);
        if (hash) {
          requestAnimationFrame(() => {
            const target = document.getElementById(hash);
            if (target) {
              target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
          });
        }
      }
    });
  });
});
```

</details>

### CSS

<details>
<summary>toggle-pages.css</summary>

```css
/* Container layout */
.toggle-container {
  display: flex;
  flex-direction: column;
}

/* Panel layout */
.toggle-panel,
.toggle-header > span,
.toggle-header > span .h1-copy-wrapper {
  display: none;
}

.toggle-panel.active,
.toggle-header > span.active {
  display: block;
}

.toggle-header > span.active .h1-copy-wrapper {
  display: flex;
  margin-bottom: 0.5rem;
}

/* Button container */
.toggle-buttons {
  display: inline-flex;
  position: relative;
  background: INSERT_BACKGROUND_COLOR;
  border-radius: 9999px;
  padding: 4px;
  border: 1px solid INSERT_BORDER_COLOR;
  width: fit-content;
}

/* Buttons */
.toggle-btn {
  z-index: 2;
  padding: 4px 12px;
  border-radius: 9999px;
  font-weight: 500;
  color: var(--md-default-fg-color);
  cursor: pointer;
  transition: color 0.25s ease;
}

/* Active text color */
.toggle-btn.active {
  color: var(--md-default-bg-color);
}

/* Slider background */
.toggle-slider {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 0;
  background: INSERT_SECONDARY_B;
  border-radius: 9999px;
  z-index: 1;
  transition: all 0.25s ease;
}

/* --- Required if using the per-page LLMs dropdown --- */
/* Update the copy-to-llm container margin when used alongside page-level toggle */
@media screen and (max-width: 768px) {
  .copy-to-llm-split-container {
    margin-top: 0;
  }

  .toggle-buttons {
    margin-top: 0.2rem;
  }
}
```

</details>

### Adding Files to mkdocs.yml

To include these JavaScript and CSS files in your MkDocs project, add them to the `extra_javascript` and `extra_css` sections in your `mkdocs.yml`:

```yaml
extra_javascript:
  - INSERT_PATH_TO_JS_DIR/toggle-pages.js
  # Example:
  # - js/toggle-pages.js

extra_css:
  - INSERT_PATH_TO_STYLESHEETS_DIR/toggle-pages.css
  # Example:
  # - assets/stylesheets/toggle-pages.css
```

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

- **Canonical (React)**: `#installation`
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
