# Resolve Markdown Plugin

The Resolve Markdown plugin for MkDocs collects the documentation page Markdown files, processes them to replace variable and code snippet placeholders with their intended values, strips HTML comments, and outputs these resolved Markdown files to a target directory inside your built site output. This is useful for serving Markdown files alongside your documentation, for example as downloadable resources or for use by other tools and systems.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml` and specify the desired configuration file:

```yaml
plugins:
  - resolve_md:
      llms_config: llms_config.json
```

The plugin reads its settings from the `llms_config.json` file, resolves every placeholder (variables and snippets), and writes the resolved artifacts directly into your build output directory (`site_dir`) under the path specified by `repository.ai_artifacts_path` (defaulting to `ai/pages`). If you set a custom `site_dir` in `mkdocs.yml`, the resolved files—and their accompanying bundles, indexes, and `llms.txt`—will simply appear under that directory’s configured AI path.

## 🔹 Configuration

- **`llms_config` (required)**: Should point to the JSON file that describes your project, repository, content filters, and output paths. Use a relative path when the file lives next to `mkdocs.yml`, or an absolute path if you store it elsewhere.

| Section      | Required keys                                                                                                   | Notes                                                                                                  |
|--------------|-----------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------|
| `project`    | `name`, `docs_base_url` (optional but recommended)                                                              | Used for `llms.txt` metadata and canonical URLs.                                                       |
| `repository` | `org`, `repo`, `default_branch`, `ai_artifacts_path`                                                            | `ai_artifacts_path` controls where resolved Markdown lands inside `site_dir` (defaults to `ai/pages`). |
| `content`    | `docs_dir`, `exclusions.skip_basenames`, `exclusions.skip_paths`, `categories_order`, `base_context_categories` | Drives which Markdown files are processed, category grouping, and base-context bundles.                |
| `outputs`    | `public_root`, `files.pages_dir`, `files.llms_full`, `files.site_index` (optional)                              | Controls where secondary artifacts (bundle files, site-index, JSONL) are written under `site_dir`.     |
| `snippets`   | `allow_remote` (optional)                                                                                       | Allows/disables HTTP snippet fetches.                                                                  |


## 🔹 Notes

- The plugin will overwrite the target directory on each build to avoid stale files.
- Once `llms_config.json` is in place and referenced from `mkdocs.yml`, `resolve_md` picks up everything automatically—no additional YAML needed.
- This plugin includes the functionality originally provided by `copy_md` 

