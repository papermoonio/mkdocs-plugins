import json
import os
from datetime import datetime, timezone
from pathlib import Path

from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin
from mkdocs.utils import log

LOG_PREFIX = "[agent_tasks]"


class AgentTasksPlugin(BasePlugin):
    config_scheme = (("agent_tasks_config", Type(str, required=True)),)

    def on_post_build(self, config):
        # Locate project root and load config
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        site_dir = Path(config["site_dir"]).resolve()

        tasks_config = self._load_config(project_root)
        if not tasks_config:
            return

        # Resolve output directory
        outputs = tasks_config.get("outputs", {})
        public_root = outputs.get("public_root", "/ai/").strip("/")
        tasks_dir_name = outputs.get("tasks_dir", "tasks")
        tasks_output_dir = site_dir / public_root / tasks_dir_name

        # Clean and recreate
        if tasks_output_dir.exists():
            import shutil

            shutil.rmtree(tasks_output_dir)
        tasks_output_dir.mkdir(parents=True, exist_ok=True)

        project = tasks_config.get("project", {})
        reference_repos = tasks_config.get("reference_repos", {})
        tasks = tasks_config.get("tasks", [])

        if not tasks:
            log.warning(f"{LOG_PREFIX} no tasks defined in config")
            return

        log.info(f"{LOG_PREFIX} generating {len(tasks)} task file(s)")

        for task in tasks:
            task_id = task.get("id", "unknown")
            try:
                content = self._render_task(task, project, reference_repos)
                output_path = tasks_output_dir / f"{task_id}.md"
                output_path.write_text(content, encoding="utf-8")
                log.info(f"{LOG_PREFIX} wrote {output_path}")
            except Exception as e:
                log.error(f"{LOG_PREFIX} failed to generate task '{task_id}': {e}")

        # Generate task index
        self._write_index(tasks, project, tasks_output_dir)

    def _load_config(self, project_root):
        config_path = project_root / self.config["agent_tasks_config"]
        if not config_path.exists():
            log.error(f"{LOG_PREFIX} config not found: {config_path}")
            return None
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"{LOG_PREFIX} failed to load config: {e}")
            return None

    def _render_task(self, task, project, reference_repos):
        lines = []

        # --- Frontmatter ---
        lines.append("---")
        lines.append(f"task_id: {task['id']}")
        lines.append(f"title: \"{task['title']}\"")
        lines.append(f"objective: \"{task['objective']}\"")

        lines.append(f"estimated_steps: {len(task.get('steps', []))}")

        ref_code = task.get("reference_code", {})
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})
        if repo_info:
            lines.append(f"reference_repo: {repo_info.get('url', '')}")

        lines.append(
            f"generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )
        lines.append("---")
        lines.append("")

        # --- Objective ---
        lines.append(f"# {task['title']}")
        lines.append("")
        lines.append(f"**Objective:** {task['objective']}")
        lines.append("")

        # --- Prerequisites ---
        prereqs = task.get("prerequisites", {})
        if prereqs:
            lines.append("## Prerequisites")
            lines.append("")
            for group_name, items in prereqs.items():
                lines.append(f"**{group_name.replace('_', ' ').title()}:**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        # --- Environment Variables ---
        env_vars = task.get("env_vars", [])
        if env_vars:
            lines.append("## Environment Variables")
            lines.append("")
            lines.append("Create a `.env` file in your project root:")
            lines.append("")
            lines.append("```env")
            for var in env_vars:
                required = " (required)" if var.get("required") else " (optional)"
                lines.append(f"# {var['description']}{required}")
                lines.append(f"{var['name']}=")
            lines.append("```")
            lines.append("")

        # --- Execution Steps ---
        steps = task.get("steps", [])
        if steps:
            lines.append("## Execution Steps")
            lines.append("")
            for step in steps:
                order = step.get("order", "?")
                action = step.get("action", "")
                lines.append(f"### Step {order}: {action}")
                lines.append("")

                desc = step.get("description")
                if desc:
                    lines.append(desc)
                    lines.append("")

                commands = step.get("commands")
                if commands:
                    lines.append("```bash")
                    for cmd in commands:
                        lines.append(cmd)
                    lines.append("```")
                    lines.append("")

                ref_file = step.get("reference_file")
                if ref_file:
                    raw_url = self._build_raw_url(reference_repos, ref_code, ref_file)
                    lines.append(f"**Reference file:** [`{ref_file}`]({raw_url})")
                    lines.append("")
                    lines.append("Fetch this file for use in your project.")
                    lines.append("")
                    lines.append(
                        "See the Reference Code Index below for a description of what this file does."
                    )
                    lines.append("")

                expected = step.get("expected_output")
                if expected:
                    lines.append(f"**Expected output:** {expected}")
                    lines.append("")

        # --- Reference Code Index ---
        files = ref_code.get("files", [])
        if files:
            lines.append("## Reference Code Index")
            lines.append("")
            if repo_info:
                lines.append(
                    f"These files are from [{repo_id}]({repo_info.get('url', '')}) "
                    f"(`{ref_code.get('base_path', '')}` directory). "
                    f"Fetch them as needed — do not download all files upfront."
                )
                lines.append("")

            lines.append("| File | Description | Raw URL |")
            lines.append("|---|---|---|")
            for file_entry in files:
                path = file_entry["path"]
                desc = file_entry.get("description", "")
                raw_url = self._build_raw_url(reference_repos, ref_code, path)
                lines.append(f"| `{path}` | {desc} | [Fetch]({raw_url}) |")
            lines.append("")

        # --- Error Recovery ---
        error_patterns = task.get("error_patterns", [])
        if error_patterns:
            lines.append("## Error Recovery")
            lines.append("")
            for err in error_patterns:
                lines.append(f"**`{err['pattern']}`**")
                lines.append(f"- **Cause:** {err['cause']}")
                lines.append(f"- **Resolution:** {err['resolution']}")
                lines.append("")

        # --- Supplementary Context ---
        supp = task.get("supplementary_context")
        if supp:
            lines.append("## Supplementary Context")
            lines.append("")
            lines.append(supp.get("description", ""))
            lines.append("")
            pages = supp.get("pages", [])
            for page in pages:
                slug = page.get("slug", "")
                url = page.get("url", "")
                relevance = page.get("relevance", "")
                lines.append(f"- [{slug}]({url}) — {relevance}")
            lines.append("")

        return "\n".join(lines)

    def _build_raw_url(self, reference_repos, ref_code, file_path):
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})
        raw_base = repo_info.get("raw_base_url", "")
        base_path = ref_code.get("base_path", "")
        return f"{raw_base}/{base_path}/{file_path}"

    def _write_index(self, tasks, project, tasks_output_dir):
        index = {
            "project": project,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tasks": [],
        }
        for task in tasks:
            index["tasks"].append(
                {
                    "id": task["id"],
                    "title": task["title"],
                    "objective": task["objective"],
                    "file": f"{task['id']}.md",
                    "steps": len(task.get("steps", [])),
                }
            )
        index_path = tasks_output_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(f"{LOG_PREFIX} wrote task index: {index_path}")
