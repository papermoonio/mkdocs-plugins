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

- **`llms_config` (required)**: Should point to the JSON file that describes your project, repository, content filters, and output paths. Use a relative path when the file lives next to `mkdocs.yml`, or an absolute path if you store it elsewhere. The following elements breakdown the key-value pairs of each JSON object found in the config:

<details>
  <summary>"project"</summary>
  <ul>
    <li>"id": internal use, all lowercase slug-style name</li>
    <li>"name": name of the project</li>
    <li>"project_url": URL for project marketing/public site</li>
    <li>"docs_base_url": base URL for deployed docs site</li>
  </ul>
</details>


## 🔹 Notes

- The plugin will overwrite the target directory on each build to avoid stale files.
- Once `llms_config.json` is in place and referenced from `mkdocs.yml`, `resolve_md` picks up everything automatically—no additional YAML needed.
- This plugin includes the functionality originally provided by `copy_md`, so you no longer need to enable `copy_md` separately.

