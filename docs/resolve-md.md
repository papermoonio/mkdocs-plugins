# Resolve Markdown Plugin

The Resolve Markdown plugin for MkDocs collects the documentation page Markdown files, processes them to replace variable and code snippet placeholders with their intended values, strips HTML comments, and outputs these resolved Markdown files to a target directory inside your built site output. This is useful for serving Markdown files alongside your documentation, for example as downloadable resources or for use by other tools and systems.

## 🔹 Usage

Enable the plugin in your `mkdocs.yml` and specify the desired configuration file:

```yaml
plugins:
  - resolve_md:
      llms_config: llms_config.json
```

The plugin reads its settings from the `llms_config.json` file, resolves every placeholder (variables and snippets), and writes the resolved markdown files directly into your build output directory (`site_dir`) at the same path as their corresponding HTML pages (e.g., `directory/page.md` alongside `directory/page/index.html`). Category bundles, indexes, and `llms.txt` are written under the AI artifacts root (defaulting to `ai/`).

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
  <details>
    <summary>"repository"</summary>
    <ul>
      <li>"host": "github" (site where docs repo lives)</li>
      <li>"org": GitHub organization name for docs repo</li>
      <li>"repo": repo name on GitHub</li>
      <li>"default_branch": branch where deployed docs live (main, dev, etc.)</li>
      <li>"docs_path": allows you to designate a custom path for docs</li>
      <li>"ai_artifacts_path": output location for AI artifact files</li>
    </ul>
  </details>
  <details>
    <summary>"content"</summary>
    <ul>
      <li>"docs_dir": allows you to specify a custom directory for docs</li>
      <li>"base_context_categories": an array of categories to include in base context</li>
      <li>"categories_info": a dictionary of category metadata; key order controls display order</li>
      <li>"exclusions": "skip_basenames" and "skip_paths" arrays to exclude files and paths from processing. Dot-directories and dot-files (names starting with <code>.</code>) are always excluded automatically</li>
    </ul>
  </details>
  <details>
    <summary>"outputs":</summary>
    <ul>
      <li>"public_root": output directory for AI artifacts (category bundles, indexes, llms.txt)</li>
      <li>"files": defines filenames for the full-site JSONL index</li>
    </ul>
  </details>

  The following is an example of a completed `llms_config.json` file for reference:

  ``` json
  {
    "schema_version": "1.2",

    "project": {
        "id": "polkadot",
        "name": "Polkadot",
        "project_url": "https://polkadot.network/",
        "docs_base_url": "https://docs.polkadot.com/"
    },

    "repository": {
        "host": "github",
        "org": "polkadot-developers",
        "repo": "polkadot-docs",
        "default_branch": "master",
        "docs_path": "."
    },

    "content": {
        "docs_dir": ".",
        "base_context_categories": ["basics", "reference"],
        "categories_info": {
            "basics": {
                "name": "Basics",
                "description": "General knowledge base and overview content."
            },
            "reference": {
                "name": "Reference",
                "description": "API references and glossary."
            }
        },
        "exclusions": {
            "skip_basenames": [
                "README.md",
                ".CONTRIBUTING.md",
                "pull-request-template.md",
                "cookie-policy.md",
                "LICENSE.md",
                "ai-chatbot-policy.md",
                "terms-of-use.md",
                "privacy-policy.md"
            ],
            "skip_paths": ["venv"]
        }
    },

    "outputs": {
        "public_root": "/ai/",
        "files": {
            "llms_full": "llms-full.jsonl"
        }
    }
  }
  ```

## 🔹 Notes

- The plugin will overwrite the target directory on each build to avoid stale files.
- Once `llms_config.json` is in place and referenced from `mkdocs.yml`, `resolve_md` picks up everything automatically—no additional YAML needed.
- This plugin includes the functionality originally provided by `copy_md`, so you no longer need to enable `copy_md` separately.
