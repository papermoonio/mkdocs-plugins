# Agent Tasks Plugin

The Agent Tasks plugin for MkDocs generates structured, agent-ready task files from a JSON configuration. Each task is rendered as a Markdown file with YAML front matter and written to your site's build output directory. An accompanying `index.json` summarizes all available tasks. This is useful for providing AI coding agents with step-by-step instructions, reference code links, and error recovery guidance.

## Usage

Enable the plugin in your `mkdocs.yml` and specify the configuration file:

```yaml
plugins:
  - agent_tasks:
      agent_tasks_config: agent_tasks_config.json
```

The plugin reads its settings from the specified JSON file and writes rendered task files into the site output directory under the path configured in `outputs` (defaulting to `ai/tasks`).

## Configuration

- **`agent_tasks_config` (required)**: Path to the JSON file that describes your project, reference repositories, and tasks. Use a relative path when the file lives next to `mkdocs.yml`.

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
    <li>"tasks_dir": subdirectory name for task files (default: "tasks")</li>
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
  <summary>"tasks"</summary>
  <p>An array of task objects. Each task supports:</p>
  <ul>
    <li>"id": unique task identifier (used as the output filename)</li>
    <li>"title": human-readable task title</li>
    <li>"objective": short description of what the task accomplishes</li>
    <li>"prerequisites": grouped prerequisite items (e.g., "tools", "accounts")</li>
    <li>"env_vars": environment variables the task requires, each with "name", "description", and "required" fields</li>
    <li>"steps": ordered execution steps, each with "order", "action", "description", "commands", "reference_file", and "expected_output"</li>
    <li>"reference_code": links to a reference repository and lists relevant files with descriptions</li>
    <li>"error_patterns": common errors with "pattern", "cause", and "resolution"</li>
    <li>"supplementary_context": additional documentation pages relevant to the task</li>
  </ul>
</details>

## Output

For each task defined in the configuration, the plugin generates:

- **`{task_id}.md`** — A Markdown file containing YAML front matter (task ID, title, objective, prerequisites, step count, reference repo, and generation timestamp) followed by structured sections for prerequisites, environment variables, execution steps, reference code index, error recovery, and supplementary context.
- **`index.json`** — A JSON index listing all tasks with their ID, title, objective, filename, and step count, along with project metadata and a generation timestamp.

## Notes

- The plugin runs in the `on_post_build` hook, so task files are generated after the full site build completes.
- The output directory is cleaned and recreated on each build to avoid stale files.
- Reference file URLs are constructed automatically from the `reference_repos` and `reference_code` configuration, pointing to raw file content for easy agent retrieval.
