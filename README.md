# MkDocs Plugins Collection

A collection of custom [MkDocs](https://www.mkdocs.org/) plugins designed to extend [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

Currently included:

- **[Copy Markdown](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/copy-md.md)**: Serve raw Markdown files by copying them directly to your site's build folder.
- **[Minify](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/minify.md)**: Minify HTML, JS, and CSS files globally or by scope to optimize your site's performance.

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
```
## License

This repository is licensed under the [BSD-2-Clause License](LICENSE).
