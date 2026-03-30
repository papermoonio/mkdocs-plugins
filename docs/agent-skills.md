# Agent Skills Plugin

The Agent Skills plugin for MkDocs generates structured, agent-ready skill files from a JSON configuration. Each skill is rendered as a Markdown file with YAML front matter and written to your site's build output directory. An accompanying `index.json` summarizes all available skills. This is useful for providing AI coding agents with step-by-step instructions, reference code links, and error recovery guidance.

## Usage

Enable the plugin in your `mkdocs.yml` and specify the configuration file:

```yaml
plugins:
  - agent_skills:
      agent_skills_config: agent_skills_config.json
```

The plugin reads its settings from the specified JSON file and writes rendered skill files into the site output directory under the path configured in `outputs` (defaulting to `ai/skills`).

## Configuration

- **`agent_skills_config` (required)**: Path to the JSON file that describes your project, reference repositories, and skills. Use a relative path when the file lives next to `mkdocs.yml`.

The configuration file supports the following top-level objects:

<details>
  <summary>"project"</summary>
  <ul>
    <li>"id": internal identifier for the project</li>
    <li>"name": display name of the project</li>
  </ul>
</details>
<details>
  <summary>"outputs"</summary>
  <ul>
    <li>"public_root": base output path within the site directory (default: "/ai/")</li>
    <li>"skills_dir": subdirectory name for skill files (default: "skills")</li>
  </ul>
</details>
<details>
  <summary>"reference_repos"</summary>
  <p>A dictionary keyed by repository ID. Each entry contains:</p>
  <ul>
    <li>"url": repository URL (for display links)</li>
    <li>"raw_base_url": base URL for fetching raw file content</li>
  </ul>
</details>
<details>
  <summary>"skills"</summary>
  <p>An array of skill objects. Each skill supports:</p>
  <ul>
    <li>"id": unique skill identifier (used as the output filename and the frontmatter <code>name</code> field)</li>
    <li>"title": human-readable skill title</li>
    <li>"objective": short description of what the skill accomplishes (written to frontmatter as <code>description</code>)</li>
    <li>"license": (optional) license name or file reference, written to frontmatter if present</li>
    <li>"compatibility": (optional) environment requirements such as required runtimes or network access, written to frontmatter if present</li>
    <li>"prerequisites": grouped prerequisite items (e.g., "tools", "accounts")</li>
    <li>"env_vars": environment variables the skill requires, each with "name", "description", and "required" fields</li>
    <li>"steps": ordered execution steps, each with "order", "action", "description", "commands", "reference_file", and "expected_output"</li>
    <li>"reference_code": links to a reference repository and lists relevant files with descriptions</li>
    <li>"error_patterns": common errors with "pattern", "cause", and "resolution"</li>
    <li>"supplementary_context": additional documentation pages relevant to the skill</li>
  </ul>
</details>

## Output

For each skill defined in the configuration, the plugin generates:

- **`{skill_id}.md`** — A Markdown file with YAML front matter aligned to the [Agent Skills specification](https://agentskills.io/specification){target=\_blank}: required `name` (skill ID) and `description` (objective) fields; optional `license` and `compatibility` fields; and a `metadata` block containing the title, step count, reference repo (if applicable), and generation timestamp. The body contains structured sections for prerequisites, environment variables, execution steps, reference code index, error recovery, and supplementary context.
- **`index.json`** — A JSON index listing all skills with their ID, title, description, filename, and step count, along with project metadata and a generation timestamp.

## Notes

- The plugin runs in the `on_post_build` hook, so skill files are generated after the full site build completes.
- The output directory is cleaned and recreated on each build to avoid stale files.
- Reference file URLs are constructed automatically from the `reference_repos` and `reference_code` configuration, pointing to raw file content for easy agent retrieval.
