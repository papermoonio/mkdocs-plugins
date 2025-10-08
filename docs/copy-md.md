# Copy Markdown Plugin

The Copy Markdown plugin for MkDocs copies raw Markdown files from a source directory into a target directory inside your built site output. This is useful for serving unprocessed Markdown files alongside your documentation, for example as downloadable resources or for use by other tools and systems.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml` and specify the source and target directories:

```yaml
plugins:
  - copy_md:
      source_dir: docs/raw_markdown
      target_dir: raw
```

This will copy all files from `docs/raw_markdown` into a folder inside your build output directory (by default `site/raw`). If you have set a custom `site_dir` in your `mkdocs.yml`, the files will be copied to `<your_site_dir>/raw` instead.

## 🔹 Configuration

- **`source_dir` (required)**: The directory containing Markdown files to copy. Should be a relative path in your project (e.g., `docs/raw_markdown`).
- **`target_dir` (required)**: The directory (relative to the build output directory, which defaults to `site/` but can be changed with `site_dir` in your `mkdocs.yml`) where Markdown files will be copied (e.g., `raw`).

## 🔹 Notes

- The plugin will overwrite the target directory on each build to avoid stale files.
- If the source directory does not exist, the plugin will skip copying and print a warning.
- Only files and folders inside `source_dir` are copied; no processing or conversion is performed.
