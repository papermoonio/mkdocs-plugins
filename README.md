# MkDocs Plugins Collection

A collection of custom [MkDocs](https://www.mkdocs.org/) plugins designed to extend [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

Currently included:

- **[Copy Markdown](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/copy-md.md)**: Serve raw Markdown files by copying them directly to your site's build folder.
- **[Minify](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/minify.md)**: Minify HTML, JS, and CSS files globally or by scope to optimize your site's performance.
- **[Page Toggle](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/page-toggle.md)**: Create variant pages for the same content and display them with an interactive toggle interface.
- **[Resolve Markdown](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/resolve-md.md)**: Resolve variable and code snippet placeholders and serve resolved Markdown files directly from your site's build folder.
- **[AI File Utils](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/ai-file-utils.md): Serves as a centralized "contract" and utility service for defining and resolving actions related to AI artifacts.

## Installation

Install the plugins using pip from PyPI:

```bash
pip install papermoon-mkdocs-plugins
```

## Usage

Enable one or more plugins in your `mkdocs.yml`:

```yaml
plugins:
  - copy_md:
      source_dir: docs/.example
      target_dir: example
  - minify:
      minify_html: true
      minify_css: true
      minify_js: true
  - page_toggle
  - resolve_md:
      llms_config: example_config.json
  - ai_file_utils
```
## License

This repository is licensed under the [BSD-2-Clause License](LICENSE).
