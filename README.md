# MkDocs Plugins Collection

A collection of custom [MkDocs](https://www.mkdocs.org/) plugins designed to extend [Material for MkDocs](https://squidfunk.github.io/mkdocs-material/).

Currently included:

- **[AI Docs](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/ai-docs.md)**: Unified AI documentation plugin. 
    - Generates AI-ready artifacts (resolved markdown, category bundles, site index, `llms.txt`), injects a per-page actions widget, and generates an AI resources page. 
    - Generates structured, agent-ready skill files from a JSON configuration.
- **[Copy Markdown](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/copy-md.md)**: Serve raw Markdown files by copying them directly to your site's build folder.
- **[Minify](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/minify.md)**: Minify HTML, JS, and CSS files globally or by scope to optimize your site's performance.
- **[Page Toggle](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/page-toggle.md)**: Create variant pages for the same content and display them with an interactive toggle interface.
- **[Agent Skills](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/agent-skills.md)**: Generate structured, agent-ready skill files from a JSON configuration.
- **[Link Processing](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/link-processor.md)**: Opens external links in a new tab and adds trailing slashes to internal paths at build time.

> **Deprecated** (kept for backward compatibility, will be removed in a future major release): [`resolve_md`](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/resolve-md.md), [`ai_page_actions`](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/ai-page-actions.md), [`ai_resources_page`](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/ai-resources-page.md). Use `ai_docs` instead.

Helper utilities and libraries: 

- **[AI File Actions](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/helper_library/ai-file-actions.md)** *(shared library)*: Convenience wrapper around `ai_file_utils` for generating AI file action dropdowns.
- **[AI File Utils](https://github.com/papermoonio/mkdocs-plugins/blob/main/docs/helper_library/ai-file-utils.md)** *(shared library)*: Resolves action definitions from JSON and generates split-button dropdown HTML for copy, download, view, and LLM tool actions.

## Installation

Install the plugins using pip from PyPI:

```bash
pip install papermoon-mkdocs-plugins
```

## Usage

Enable one or more plugins in your `mkdocs.yml`:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      agent_skills_config: agent_skills_config.json
  - copy_md:
      source_dir: docs/.example
      target_dir: example
  - minify:
      minify_html: true
      minify_css: true
      minify_js: true
  - page_toggle
  - link_processor:
      skip_internal_path_prefixes:
        - /api/
```
## License

This repository is licensed under the [BSD-2-Clause License](LICENSE).
