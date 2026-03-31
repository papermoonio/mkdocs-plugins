import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin
from mkdocs.utils import log

LOG_PREFIX = "[agent_skills]"


class AgentSkillsPlugin(BasePlugin):
    config_scheme = (("agent_skills_config", Type(str, required=True)),)

    def on_config(self, config):
        """Load skills config and build page-to-skill reverse mapping."""
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent

        self._skills_config = self._load_config(project_root)
        self._page_skill_map = {}

        if not self._skills_config:
            return config

        outputs = self._skills_config.get("outputs", {})
        self._public_root = outputs.get("public_root", "/ai/").strip("/")
        self._skills_dir_name = outputs.get("skills_dir", "skills")

        for skill in self._skills_config.get("skills", []):
            for page_path in skill.get("source_pages", []):
                self._page_skill_map.setdefault(page_path, []).append(
                    {
                        "id": skill["id"],
                        "title": skill["title"],
                    }
                )

        return config

    def on_page_content(self, html, page, config, files):
        """Inject skill badge on pages that have a related skill."""
        skills = self._page_skill_map.get(page.file.src_path, [])
        if not skills:
            return html

        site_url = (config.get("site_url") or "").rstrip("/")
        badges_html = self._render_skill_badges(skills, site_url)

        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        if h1:
            badge_soup = BeautifulSoup(badges_html, "html.parser")
            h1.insert_after(badge_soup)
            return str(soup)

        return html

    def on_post_build(self, config):
        """Generate skill files and index."""
        if not self._skills_config:
            return

        site_dir = Path(config["site_dir"]).resolve()
        skills_output_dir = site_dir / self._public_root / self._skills_dir_name

        if skills_output_dir.exists():
            shutil.rmtree(skills_output_dir)
        skills_output_dir.mkdir(parents=True, exist_ok=True)

        project = self._skills_config.get("project", {})
        reference_repos = self._skills_config.get("reference_repos", {})
        skills = self._skills_config.get("skills", [])

        if not skills:
            log.warning(f"{LOG_PREFIX} no skills defined in config")
            return

        log.info(f"{LOG_PREFIX} generating {len(skills)} skill file(s)")

        for skill in skills:
            skill_id = skill.get("id", "unknown")
            try:
                content = self._render_skill(skill, project, reference_repos)
                output_path = skills_output_dir / f"{skill_id}.md"
                output_path.write_text(content, encoding="utf-8")
                log.info(f"{LOG_PREFIX} wrote {output_path}")
            except Exception as e:
                log.error(f"{LOG_PREFIX} failed to generate skill '{skill_id}': {e}")

        self._write_index(skills, project, skills_output_dir)

    def _load_config(self, project_root):
        config_path = project_root / self.config["agent_skills_config"]
        if not config_path.exists():
            log.error(f"{LOG_PREFIX} config not found: {config_path}")
            return None
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"{LOG_PREFIX} failed to load config: {e}")
            return None

    def _render_skill(self, skill, project, reference_repos):
        lines = []

        # --- Frontmatter ---
        ref_code = skill.get("reference_code", {})
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})

        lines.append("---")
        lines.append(f"name: {skill['id']}")
        lines.append(f"description: \"{skill['objective']}\"")

        if skill.get("license"):
            lines.append(f"license: {skill['license']}")
        if skill.get("compatibility"):
            lines.append(f"compatibility: {skill['compatibility']}")

        lines.append("metadata:")
        lines.append(f"  title: \"{skill['title']}\"")
        lines.append(f"  estimated_steps: \"{len(skill.get('steps', []))}\"")
        if repo_info:
            lines.append(f"  reference_repo: {repo_info.get('url', '')}")

        source_pages = skill.get("source_pages", [])
        if source_pages:
            pages_yaml = ", ".join(f'"{p}"' for p in source_pages)
            lines.append(f"  source_pages: [{pages_yaml}]")

        lines.append(
            f"  generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}"
        )

        lines.append("---")
        lines.append("")

        # --- Objective ---
        lines.append(f"# {skill['title']}")
        lines.append("")
        lines.append(f"**Objective:** {skill['objective']}")
        lines.append("")

        # --- Prerequisites ---
        prereqs = skill.get("prerequisites", {})
        if prereqs:
            lines.append("## Prerequisites")
            lines.append("")
            for group_name, items in prereqs.items():
                lines.append(f"**{group_name.replace('_', ' ').title()}:**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

        # --- Environment Variables ---
        env_vars = skill.get("env_vars", [])
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
        steps = skill.get("steps", [])
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
        error_patterns = skill.get("error_patterns", [])
        if error_patterns:
            lines.append("## Error Recovery")
            lines.append("")
            for err in error_patterns:
                lines.append(f"**`{err['pattern']}`**")
                lines.append(f"- **Cause:** {err['cause']}")
                lines.append(f"- **Resolution:** {err['resolution']}")
                lines.append("")

        # --- Supplementary Context ---
        supp = skill.get("supplementary_context")
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

    _TERMINAL_ICON = (
        '<svg class="agent-skill-badge__icon" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'
        '<path d="M0 2.75C0 1.784.784 1 1.75 1h12.5c.966 0 1.75.784 1.75 1.75v10.5'
        "A1.75 1.75 0 0 1 14.25 15H1.75A1.75 1.75 0 0 1 0 13.25Zm1.75-.25a.25.25 0 0 0"
        "-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25V2.75a.25.25 0 0 0"
        "-.25-.25ZM7.25 8a.749.749 0 0 1-.22.53l-2.25 2.25a.749.749 0 0 1-1.275-.326"
        ".749.749 0 0 1 .215-.734L5.44 8 3.72 6.28a.749.749 0 0 1 .326-1.275.749.749 0 0 1"
        ".734.215l2.25 2.25c.141.14.22.331.22.53Zm1.5 1.5h3a.75.75 0 0 1 0 1.5h-3"
        'a.75.75 0 0 1 0-1.5Z"></path></svg>'
    )

    def _render_skill_badges(self, skills, site_url):
        items = []
        for skill in skills:
            path = f"/{self._public_root}/{self._skills_dir_name}/{skill['id']}.md"
            url = f"{site_url}{path}" if site_url else path
            items.append(
                f'<div class="agent-skill-badge">'
                f"{self._TERMINAL_ICON}"
                f'<span class="agent-skill-badge__label">Agent skill</span>'
                f'<span class="agent-skill-badge__divider" aria-hidden="true"></span>'
                f'<a href="{url}" class="agent-skill-badge__action"'
                f' target="_blank" rel="noopener">View</a>'
                f'<span class="agent-skill-badge__dot" aria-hidden="true">·</span>'
                f'<a href="{url}" class="agent-skill-badge__action" download>Download</a>'
                f"</div>"
            )
        return '<div class="agent-skill-badges">' + "".join(items) + "</div>"

    def _build_raw_url(self, reference_repos, ref_code, file_path):
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})
        raw_base = repo_info.get("raw_base_url", "")
        base_path = ref_code.get("base_path", "")
        return f"{raw_base}/{base_path}/{file_path}"

    def _write_index(self, skills, project, skills_output_dir):
        index = {
            "project": project,
            "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "skills": [],
        }
        for skill in skills:
            entry = {
                "id": skill["id"],
                "title": skill["title"],
                "description": skill["objective"],
                "file": f"{skill['id']}.md",
                "steps": len(skill.get("steps", [])),
            }
            source_pages = skill.get("source_pages", [])
            if source_pages:
                entry["source_pages"] = source_pages
            index["skills"].append(entry)

        index_path = skills_output_dir / "index.json"
        index_path.write_text(
            json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        log.info(f"{LOG_PREFIX} wrote skill index: {index_path}")
