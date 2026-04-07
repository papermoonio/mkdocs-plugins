# AI Docs Plugin

The AI Docs plugin consolidates [`resolve_md`](resolve-md.md), [`ai_page_actions`](ai-page-actions.md), and [`ai_resources_page`](ai-resources-page.md) into a single plugin. It generates AI-ready artifacts from your documentation (resolved markdown files, category bundles, site index, and `llms.txt`) and optionally injects a per-page actions widget, generates an AI resources page, and generates structured agent skill files.

> ⚠️ **Deprecation notice:**
>
> The individual `resolve_md`, `ai_page_actions`, and `ai_resources_page` plugins are deprecated and kept only for backward compatibility. Migrate to `ai_docs` at your convenience — they will be removed in a future major release.

## Usage

Replace the three separate plugin entries in your `mkdocs.yml` with a single `ai_docs` block:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
```

Both `ai_resources_page` and `ai_page_actions` are enabled by default. To opt out of either feature:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      ai_resources_page: false
      ai_page_actions: false
```

To enable agent skill file generation, provide the path to your `agent_skills_config.json`:

```yaml
plugins:
  - ai_docs:
      llms_config: llms_config.json
      agent_skills_config: agent_skills_config.json
```

## Configuration

| Option | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `llms_config` | `string` | `llms_config.json` | Path to the LLM config file, relative to `mkdocs.yml`. |
| `ai_resources_page` | `bool` | `true` | Generate the AI resources page from `ai-resources.md`. Set to `false` to disable. |
| `ai_page_actions` | `bool` | `true` | Inject the per-page AI actions widget next to each H1. Set to `false` to disable. |
| `agent_skills_config` | `string` | _(empty)_ | Path to the agent skills config file, relative to `mkdocs.yml`. Agent skill generation is disabled when this is not set. |
| `agent_skills` | `bool` | `true` | Enable or disable agent skill generation independently. Only applies when `agent_skills_config` is set. |
| `enabled` | `bool` | `true` | Disable the entire plugin (all features). Supports `!ENV` for environment-based toggling. |

The `llms_config` file controls content filtering, category definitions, and output paths. See [Resolve Markdown](resolve-md.md#-configuration) for a full breakdown of the `llms_config.json` schema.

## Features

### Artifact generation

Always runs when the plugin is enabled. Processes every documentation markdown file to:

- Resolve variable (`{{ variable }}`) and snippet (`--8<--`) placeholders
- Strip HTML comments
- Write resolved `.md` files alongside their corresponding HTML pages in the build output
- Generate per-category bundle files under `ai/categories/`
- Generate `site-index.json` and `llms-full.jsonl` under `ai/`
- Generate `llms.txt` at the site root

### AI page actions (`ai_page_actions`)

Injects a split-button dropdown widget next to each page's H1 heading at build time. The widget lets readers copy, download, or open the page's resolved markdown in an LLM tool. Pages listed in `llms_config.json` exclusions, dot-directories, and pages with `hide_ai_actions: true` in their front matter are automatically skipped.

See [AI Page Actions](ai-page-actions.md) for details on exclusion rules, toggle page handling, and styling.

### AI resources page (`ai_resources_page`)

Automatically generates the content for a page named `ai-resources.md`, replacing it with a table listing all available LLM artifact files (global indexes and per-category bundles) with copy, view, and download actions.

See [AI Resources Page](ai-resources-page.md) for details on the generated content and `llms_config.json` requirements.

### Agent skills (`agent_skills`)

Generates structured, agent-ready skill files from a JSON configuration. Each skill is rendered as a Markdown file with YAML front matter and written to the site output under `ai/skills/`. An accompanying `index.json` summarizes all available skills. This is useful for providing AI coding agents with step-by-step instructions, reference code links, and error recovery guidance.

Skill generation requires `agent_skills_config` to be set. The plugin also injects a widget next to each page's H1 for any documentation page linked to a skill via `source_pages` in the config.

#### `agent_skills_config.json` schema

The configuration file supports the following top-level objects:

- **`project`**
    - `id`: Internal identifier for the project.
    - `name`: Display name of the project.

- **`outputs`**
    - `public_root`: Base output path within the site directory. Default: `"/ai/"`.
    - `skills_dir`: Subdirectory name for skill files. Default: `"skills"`.

- **`reference_repos`**: A dictionary keyed by repository ID. Each entry contains:
    - `url`: Repository URL for display links.
    - `raw_base_url`: Base URL for fetching raw file content.

- **`skills`**: An array of skill objects. Each skill supports:
    - `id`: Unique skill identifier, used as the output filename and the frontmatter `name` field.
    - `title`: Human-readable skill title.
    - `objective`: Short description of what the skill accomplishes, written to frontmatter as `description`.
    - `license`: (Optional) License name or file reference, written to frontmatter if present.
    - `compatibility`: (Optional) Environment requirements such as required runtimes or network access, written to frontmatter if present.
    - `prerequisites`: Grouped prerequisite items (for example, `"tools"`, `"accounts"`).
    - `env_vars`: Environment variables the skill requires, each with `name`, `description`, and `required` fields.
    - `steps`: Ordered execution steps, each with `order`, `action`, `description`, `commands`, `reference_file`, and `expected_output`.
    - `reference_code`: Links to a reference repository and lists relevant files with descriptions.
    - `error_patterns`: Common errors with `pattern`, `cause`, and `resolution`.
    - `supplementary_context`: Additional documentation pages relevant to the skill.
    - `source_pages`: List of documentation page paths relative to the docs directory, used to inject skill widgets on those pages.

#### Output

For each skill defined in the configuration, the plugin generates:

- **`{skill_id}.md`** — A Markdown file with YAML front matter aligned to the [Agent Skills specification](https://agentskills.io/specification){target=\_blank}: required `name` (skill ID) and `description` (objective) fields; optional `license` and `compatibility` fields; and a `metadata` block containing the title, step count, reference repo (if applicable), and generation timestamp. The body contains structured sections for prerequisites, environment variables, execution steps, reference code index, error recovery, and supplementary context.
- **`index.json`** — A JSON index listing all skills with their ID, title, description, filename, and step count, along with project metadata and a generation timestamp.

The output directory (`ai/skills/` by default) is cleaned and recreated on each build to avoid stale files.

## Notes

- All features share a single `llms_config.json` load — the file is read once per build and cached.
- Disabling `ai_resources_page` or `ai_page_actions` skips only those hooks; artifact generation always runs.
- Agent skill generation is independent of the other features and only runs when `agent_skills_config` is set.
- Reference file URLs in skill output are constructed automatically from `reference_repos` and `reference_code` configuration, pointing to raw file content for easy agent retrieval.
- The plugin registers under the `ai_docs` entry point. The deprecated `resolve_md`, `ai_page_actions`, and `ai_resources_page` entry points remain registered and functional until removed.
