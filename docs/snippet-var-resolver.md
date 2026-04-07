# Snippet Var Resolver Plugin

The Snippet Var Resolver plugin resolves `{{ variable }}` placeholders that survive into the rendered HTML of a page after pymdownx.snippets has injected snippet content.

The problem it solves: mkdocs-macros resolves Jinja2 variables during the `on_page_markdown` event, but pymdownx.snippets injects snippet file content later during markdown-to-HTML conversion — after macros has already run. Any `{{ variable }}` references inside snippet files therefore appear unresolved in the final HTML.

This plugin runs on the `on_page_content` event (after snippets have been injected) and replaces any remaining `{{ variable }}` patterns using the `include_yaml` files listed in the macros plugin config.

## 🔹 Usage

Add the plugin **after `macros`** in your `mkdocs.yml`:

```yaml
plugins:
  - macros:
      include_yaml:
        - polkadot-docs/variables.yml
  - snippet_var_resolver
```

No additional configuration is required. The plugin reads its variable sources directly from the macros plugin config.

## 🔹 Configuration

This plugin has no configuration options. It self-configures from the surrounding plugin setup.

## 🔹 Notes

- Variable lookup supports dotted paths — e.g. `{{ dependencies.zombienet.version }}` resolves into nested YAML structures.
- Unknown placeholders (keys not found in any variable source) are left untouched, so unrelated Jinja2 syntax in the HTML is not affected.
- If multiple `include_yaml` files define the same top-level key, the last file wins (same behaviour as mkdocs-macros).
- The plugin runs on the `on_page_content` event, so it processes the rendered HTML of each page rather than the Markdown source.
