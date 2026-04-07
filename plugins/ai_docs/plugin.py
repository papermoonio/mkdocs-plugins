import hashlib
import html
import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from urllib import error as urllib_error
from urllib import request as urllib_request
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag

import yaml
from mkdocs.config.config_options import Type
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page
from mkdocs.utils import log

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils

# Module scope regex variables

FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
SNIPPET_TOKEN_REGEX = re.compile(r"-{1,}8<-{2,}\s*['\"]([^'\"]+)['\"]")
SNIPPET_LINE_REGEX = re.compile(
    r"(?m)^(?P<indent>[ \t]*)-{1,}8<-{2,}\s*['\"](?P<ref>[^'\"]+)['\"]\s*$"
)
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*#*\s*$")
SNIPPET_SECTION_REGEX = re.compile(
    r"""^\s*(?:#|//|;|<!--)?\s*--8<--\s*\[(?P<kind>start|end):(?P<name>[^\]]+)\]\s*(?:-->)*\s*$""",
    re.IGNORECASE,
)
SNIPPET_DOUBLE_RANGE_RE = re.compile(r"^(?P<path>.+?)::(?P<end>-?\d+)$")
SNIPPET_RANGE_RE = re.compile(r"^(?P<path>.+?):(?P<start>-?\d+):(?P<end>-?\d+)$")
SNIPPET_SINGLE_RANGE_RE = re.compile(r"^(?P<path>.+?):(?P<start>-?\d+)$")


# Define plugin class
class AIDocsPlugin(BasePlugin):
    # Define value for `llms_config` in the project mkdocs.yml file
    config_scheme = (
        ("llms_config", Type(str, default="llms_config.json")),
        ("ai_resources_page", Type(bool, default=True)),
        ("ai_page_actions", Type(bool, default=True)),
        ("agent_skills_config", Type(str, default="")),
        ("agent_skills", Type(bool, default=True)),
    )

    def __init__(self):
        super().__init__()
        self._llms_config: dict = {}

        # Resolve MD vars
        self.allow_remote_snippets = True
        self.allowed_domains = []
        self._remote_snippet_cache: dict[str, str | None] = {}

        # AI page actions vars
        self._file_utils = AIFileUtils()
        self._skip_basenames: List[str] = []
        self._skip_paths: List[str] = []
        self._config_loaded = False

        # Agent skills vars
        self._skills_config: dict = {}
        self._page_skill_map: dict = {}
        self._skills_public_root: str = "ai"
        self._skills_dir_name: str = "skills"

    # ------------------------------------------------------------------
    # Internal functions
    # ------------------------------------------------------------------

    def _ensure_config_loaded(self, config: MkDocsConfig) -> None:
        """Load llms_config.json once per build and cache the result."""
        if self._config_loaded:
            return
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        self._llms_config = self._load_llms_config(project_root)

        exclusions = self._llms_config.get("content", {}).get("exclusions", {})
        self._skip_basenames = exclusions.get("skip_basenames", [])
        self._skip_paths = exclusions.get("skip_paths", [])
        self._config_loaded = True

    def _load_llms_config(self, project_root: Path) -> dict:
        """Load the LLM config file from the configured path."""
        config_filename = self.config.get("llms_config", "llms_config.json")
        config_path = (project_root / config_filename).resolve()
        if not config_path.exists():
            raise FileNotFoundError(f"[ai_docs] llms_config not found at {config_path}")
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[ai_docs] Failed to load LLM config: {e}")
            return {}

    def _wrap_h1(
        self, h1: Tag, md_path: str, soup: BeautifulSoup, site_url: str = ""
    ) -> None:
        """Append the AI actions widget to the page-meta-chips row below the H1."""
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""
        url = f"{base_path}/{md_path}"
        filename = md_path.rsplit("/", 1)[-1]

        widget_html = self._file_utils.generate_dropdown_html(
            url=url,
            filename=filename,
            primary_label="Copy page",
            site_url=site_url,
            label_replace={"file": "page"},
        )

        chips_div = h1.find_next_sibling("div", class_="page-meta-chips")
        if not chips_div:
            chips_div = soup.new_tag("div")
            chips_div["class"] = "page-meta-chips"
            h1.insert_after(chips_div)

        widget = BeautifulSoup(widget_html, "html.parser")
        chips_div.append(widget)

    # ------------------------------------------------------------------
    # Agent skills helpers
    # ------------------------------------------------------------------

    def _load_skills_config(self, project_root: Path) -> dict:
        """Load agent_skills_config.json from the configured path."""
        config_filename = self.config.get("agent_skills_config", "")
        if not config_filename:
            return {}
        config_path = (project_root / config_filename).resolve()
        if not config_path.exists():
            log.error(f"[ai_docs] agent_skills_config not found: {config_path}")
            return {}
        try:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.error(f"[ai_docs] failed to load agent_skills_config: {e}")
            return {}

    _TERMINAL_ICON = (
        '<svg class="agent-skill-widget__icon" xmlns="http://www.w3.org/2000/svg" '
        'viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">'
        '<path d="M0 2.75C0 1.784.784 1 1.75 1h12.5c.966 0 1.75.784 1.75 1.75v10.5'
        "A1.75 1.75 0 0 1 14.25 15H1.75A1.75 1.75 0 0 1 0 13.25Zm1.75-.25a.25.25 0 0 0"
        "-.25.25v10.5c0 .138.112.25.25.25h12.5a.25.25 0 0 0 .25-.25V2.75a.25.25 0 0 0"
        "-.25-.25ZM7.25 8a.749.749 0 0 1-.22.53l-2.25 2.25a.749.749 0 0 1-1.275-.326"
        ".749.749 0 0 1 .215-.734L5.44 8 3.72 6.28a.749.749 0 0 1 .326-1.275.749.749 0 0 1"
        ".734.215l2.25 2.25c.141.14.22.331.22.53Zm1.5 1.5h3a.75.75 0 0 1 0 1.5h-3"
        'a.75.75 0 0 1 0-1.5Z"></path></svg>'
    )

    def _render_skill_widgets(self, skills: list, site_url: str) -> str:
        """Render the agent skill widget HTML for a list of skills."""
        items = []
        for skill in skills:
            path = (
                f"/{self._skills_public_root}/{self._skills_dir_name}/{skill['id']}.md"
            )
            url = f"{site_url}{path}" if site_url else path
            title = html.escape(skill.get("title", ""))
            items.append(
                f'<div class="agent-skill-widget">'
                f"{self._TERMINAL_ICON}"
                f'<span class="agent-skill-widget__label" title="{title}">Agent skill</span>'
                f'<span class="agent-skill-widget__divider" aria-hidden="true"></span>'
                f'<a href="{url}" class="agent-skill-widget__action"'
                f' target="_blank" rel="noopener"'
                f' aria-label="View {title}">View</a>'
                f'<span class="agent-skill-widget__dot" aria-hidden="true">·</span>'
                f'<a href="{url}" class="agent-skill-widget__action" download'
                f' aria-label="Download {title}">Download</a>'
                f"</div>"
            )
        return '<div class="agent-skill-widgets">' + "".join(items) + "</div>"

    def _build_raw_url(
        self, reference_repos: dict, ref_code: dict, file_path: str
    ) -> str:
        """Build a raw URL for a reference file."""
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})
        raw_base = repo_info.get("raw_base_url", "")
        base_path = ref_code.get("base_path", "")
        return f"{raw_base}/{base_path}/{file_path}"

    def _render_skill(self, skill: dict, project: dict, reference_repos: dict) -> str:
        """Render a single skill as a markdown string with YAML frontmatter."""
        lines = []

        ref_code = skill.get("reference_code", {})
        repo_id = ref_code.get("repo", "")
        repo_info = reference_repos.get(repo_id, {})

        fm: dict = {
            "name": skill["id"],
            "description": skill["objective"],
        }
        if skill.get("license"):
            fm["license"] = skill["license"]
        if skill.get("compatibility"):
            fm["compatibility"] = skill["compatibility"]

        source_pages = skill.get("source_pages", [])
        metadata: dict = {
            "title": skill["title"],
            "estimated_steps": len(skill.get("steps", [])),
        }
        if repo_info:
            metadata["reference_repo"] = repo_info.get("url", "")
        if source_pages:
            metadata["source_pages"] = source_pages
        metadata["generated"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        fm["metadata"] = metadata

        lines.append("---")
        lines.append(yaml.safe_dump(fm, sort_keys=False, allow_unicode=True).rstrip())
        lines.append("---")
        lines.append("")

        lines.append(f"# {skill['title']}")
        lines.append("")
        lines.append(f"**Objective:** {skill['objective']}")
        lines.append("")

        prereqs = skill.get("prerequisites", {})
        if prereqs:
            lines.append("## Prerequisites")
            lines.append("")
            for group_name, items in prereqs.items():
                lines.append(f"**{group_name.replace('_', ' ').title()}:**")
                for item in items:
                    lines.append(f"- {item}")
                lines.append("")

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

        error_patterns = skill.get("error_patterns", [])
        if error_patterns:
            lines.append("## Error Recovery")
            lines.append("")
            for err in error_patterns:
                lines.append(f"**`{err['pattern']}`**")
                lines.append(f"- **Cause:** {err['cause']}")
                lines.append(f"- **Resolution:** {err['resolution']}")
                lines.append("")

        supp = skill.get("supplementary_context")
        if supp:
            lines.append("## Supplementary Context")
            lines.append("")
            lines.append(supp.get("description", ""))
            lines.append("")
            for p in supp.get("pages", []):
                slug = p.get("slug", "")
                url = p.get("url", "")
                relevance = p.get("relevance", "")
                lines.append(f"- [{slug}]({url}) — {relevance}")
            lines.append("")

        return "\n".join(lines)

    def _write_skills_index(
        self, skills: list, project: dict, skills_output_dir: Path
    ) -> None:
        """Write index.json summarising all skills to the skills output directory."""
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
        log.info(f"[ai_docs] wrote skill index: {index_path}")

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------

    def on_config(self, config):
        """Load agent_skills_config and build page-to-skill reverse mapping."""
        if not self.config.get("agent_skills", True):
            return config

        agent_skills_config_path = self.config.get("agent_skills_config", "")
        if not agent_skills_config_path:
            return config

        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent

        self._skills_config = self._load_skills_config(project_root)
        self._page_skill_map = {}

        if not self._skills_config:
            return config

        outputs = self._skills_config.get("outputs", {})
        public_root = outputs.get("public_root", "/ai/").strip("/")
        skills_dir = outputs.get("skills_dir", "skills")

        if not public_root or not skills_dir:
            log.error(
                "[ai_docs] agent_skills_config outputs.public_root and "
                "outputs.skills_dir must not be empty — skipping skill generation"
            )
            self._skills_config = {}
            return config

        self._skills_public_root = public_root
        self._skills_dir_name = skills_dir

        for skill in self._skills_config.get("skills", []):
            for page_path in skill.get("source_pages", []):
                self._page_skill_map.setdefault(page_path, []).append(
                    {"id": skill["id"], "title": skill["title"]}
                )

        return config

    def _generate_mcp_section(
        self, project_name: str, mcp_name: str, mcp_url: str
    ) -> str:
        """Return the full MCP Markdown section (heading, intro, table)."""
        utils = self._file_utils

        cursor_btn = utils.mcp_install_button(
            utils.build_cursor_deeplink(mcp_name, mcp_url)
        )
        vscode_btn = utils.mcp_install_button(
            utils.build_vscode_deeplink(mcp_name, mcp_url)
        )
        claude_cmd = utils.mcp_copy_code(
            f"claude mcp add --transport http {mcp_name} {mcp_url}"
        )
        codex_cmd = utils.mcp_copy_code(f"codex mcp add {mcp_name} --url {mcp_url}")
        claude_desktop_btn = utils.mcp_install_button(
            "https://modelcontextprotocol.io/docs/develop/connect-remote-servers#connecting-to-a-remote-mcp-server",
            ":simple-claude: Claude",
        )
        chatgpt_icon = utils.twemoji_icon(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><path d="M22.282 9.821a5.985 5.985 0 0 0-.516-4.91 6.046 6.046 0 0 0-6.51-2.9A6.065 6.065 0 0 0 4.981 4.18a5.985 5.985 0 0 0-3.998 2.9 6.046 6.046 0 0 0 .743 7.097 5.98 5.98 0 0 0 .51 4.911 6.051 6.051 0 0 0 6.515 2.9A5.985 5.985 0 0 0 13.26 24a6.056 6.056 0 0 0 5.772-4.206 5.99 5.99 0 0 0 3.997-2.9 6.056 6.056 0 0 0-.747-7.073zM13.26 22.43a4.476 4.476 0 0 1-2.876-1.04l.141-.081 4.779-2.758a.795.795 0 0 0 .392-.681v-6.737l2.02 1.168a.071.071 0 0 1 .038.052v5.583a4.504 4.504 0 0 1-4.494 4.494zM3.6 18.304a4.47 4.47 0 0 1-.535-3.014l.142.085 4.783 2.759a.771.771 0 0 0 .78 0l5.843-3.369v2.332a.08.08 0 0 1-.033.062L9.74 19.95a4.5 4.5 0 0 1-6.14-1.646zM2.34 7.896a4.485 4.485 0 0 1 2.366-1.973V11.6a.766.766 0 0 0 .388.676l5.815 3.355-2.02 1.168a.076.076 0 0 1-.071 0L4.1 14.3A4.501 4.501 0 0 1 2.34 7.896zm16.597 3.855l-5.843-3.375 2.02-1.164a.076.076 0 0 1 .071 0l4.724 2.727a4.5 4.5 0 0 1-.676 8.123v-5.68a.79.79 0 0 0-.396-.63zm2.007-3.023l-.141-.085-4.774-2.782a.776.776 0 0 0-.785 0L9.409 9.23V6.897a.066.066 0 0 1 .028-.061l4.723-2.727a4.5 4.5 0 0 1 6.689 4.661zm-12.73 4.28l-2.02-1.167a.08.08 0 0 1-.038-.057V6.197a4.5 4.5 0 0 1 7.375-3.453l-.142.08L8.62 5.585a.795.795 0 0 0-.393.681zm1.097-2.365l2.602-1.5 2.607 1.5v2.999l-2.597 1.5-2.607-1.5z"/></svg>'
        )
        chatgpt_desktop_btn = utils.mcp_install_button(
            "https://help.openai.com/en/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt-beta",
            "ChatGPT",
            html_icon=chatgpt_icon,
        )
        return f"""## Connect via MCP

Use the [Model Context Protocol (MCP)](https://modelcontextprotocol.io) to connect your AI tools directly to {project_name} documentation.

```md
{mcp_url}
```

<div class="grid cards install-mcp" markdown>

- **Install via IDE**
    
    {cursor_btn}
    {vscode_btn}
    
- **Install via Desktop App**
    
    {claude_desktop_btn}
    {chatgpt_desktop_btn}
    
</div>

<div class="grid cards install-mcp" markdown>

- **Install via CLI**

    | Client  | Command |
    |:---|:---|
    | Claude Code CLI | {claude_cmd} |
    | Codex CLI  | {codex_cmd} |
    
</div>

!!! note
    For Claude Code, add `--scope user` to make the MCP server available across all projects.
"""

    def on_page_markdown(self, markdown, page, config, files):
        """
        Add an AI Resources page at /ai-resources.md with links to the LLM files and category bundles.
        The content is generated dynamically based on the current llms_config.json and the categories defined therein.
        """

        if not self.config.get("ai_resources_page", True):
            return markdown

        # Target only the AI Resources page
        if not page.file.src_path.endswith("ai-resources.md"):
            return markdown

        log.info(f"[ai_docs] Generating content for {page.file.src_path}")

        self._ensure_config_loaded(config)

        # Get project name
        project_cfg = self._llms_config.get("project", {})
        project_name = project_cfg.get("name")
        if not project_name:
            raise KeyError("[ai_docs] 'project.name' is missing in llms_config.json")

        # Category headings are emitted here so MkDocs includes them in the TOC.
        # The tables are injected with token estimates in on_post_build via
        # _patch_ai_resources_page, after all artifact files have been written.
        content_cfg = self._llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info", {}) or {}

        category_sections = ""
        if categories_info:
            category_sections = "\n\n### Category Files\n"
            for cat_id, cat_info in categories_info.items():
                slug = self.slugify_category(cat_id)
                display_name = cat_info.get("name", cat_id)
                description = cat_info.get(
                    "description", f"Resources for {display_name}."
                )
                category_sections += (
                    f"\n#### {display_name}\n\n"
                    f"{description}\n\n"
                    f"<!-- ai-category-{slug}-table -->\n"
                )

        # MCP install section (only when both mcp_url and mcp_name are configured)
        mcp_name = project_cfg.get("mcp_name")
        mcp_url = project_cfg.get("mcp_url")
        mcp_section = ""
        if mcp_url and mcp_name:
            mcp_section = self._generate_mcp_section(project_name, mcp_name, mcp_url)

        return f"""# AI Resources

{project_name} provides files to make documentation content available in a structure optimized for use with large language models (LLMs) and AI tools. These resources help build AI assistants, power code search, or enable custom tooling trained on {project_name}'s documentation.

{mcp_section}

## Access LLM Files

- **Quick navigation**: Use `llms.txt` to give models a high-level map of the site.
- **Lightweight context**: Use `site-index.json` for smaller context windows or when you only need targeted retrieval.
- **Full content**: Use `llms-full.jsonl` for large-context models or preparing data for RAG pipelines.
- **Focused bundles**: Use category files (e.g., `basics.md`, `reference.md`) to limit content to a specific theme or task for more focused responses.

These AI-ready files do not include any persona or system prompts. They are purely informational and can be used without conflicting with your existing agent or tool prompting.

### Full Site Files

<!-- ai-resources-aggregate-table -->

!!! note
    The `llms-full.jsonl` file may exceed the input limits of some language models due to its size. If you encounter limitations, consider using the smaller `site-index.json` or category bundle files instead.
{category_sections}
"""

    def _build_aggregate_table_html(
        self,
        base_path: str,
        public_root_stripped: str,
        site_url: str,
        aggregate_tokens: dict[str, int],
    ) -> str:
        """Render the aggregate AI resources table (llms.txt, site-index.json, llms-full.jsonl)."""

        def th(text: str) -> str:
            return f"<th>{text}</th>"

        def td(content: str) -> str:
            return f"<td>{content}</td>"

        def fmt_tokens(n: int) -> str:
            return f"{n:,}" if n else "—"

        def make_table(rows: list[str]) -> str:
            header = (
                "<thead><tr>"
                + th("File")
                + th("Description")
                + th("Token Estimate")
                + th("Actions")
                + "</tr></thead>"
            )
            return (
                "<table>\n"
                + header
                + "\n"
                + "<tbody>\n"
                + "\n".join(rows)
                + "\n"
                + "</tbody>\n"
                + "</table>"
            )

        actions_llms = self._file_utils.generate_dropdown_html(
            url=f"{base_path}/llms.txt", filename="llms.txt", site_url=site_url
        )
        actions_site_index = self._file_utils.generate_dropdown_html(
            url=f"{base_path}{public_root_stripped}/site-index.json",
            filename="site-index.json",
            site_url=site_url,
        )
        actions_full = self._file_utils.generate_dropdown_html(
            url=f"{base_path}{public_root_stripped}/llms-full.jsonl",
            filename="llms-full.jsonl",
            exclude=["view-markdown"],
            site_url=site_url,
        )
        return make_table(
            [
                "<tr>"
                + td('<code style="white-space: nowrap;">llms.txt</code>')
                + td(
                    "Markdown URL index for documentation pages, links to essential repos, and additional resources in the llms.txt standard format."
                )
                + td(fmt_tokens(aggregate_tokens.get("llms_txt", 0)))
                + td(actions_llms)
                + "</tr>",
                "<tr>"
                + td('<code style="white-space: nowrap;">site-index.json</code>')
                + td(
                    "Lightweight site index of JSON objects (one per page) with metadata and content previews."
                )
                + td(fmt_tokens(aggregate_tokens.get("site_index", 0)))
                + td(actions_site_index)
                + "</tr>",
                "<tr>"
                + td('<code style="white-space: nowrap;">llms-full.jsonl</code>')
                + td("Full content of documentation site enhanced with metadata.")
                + td(fmt_tokens(aggregate_tokens.get("llms_full", 0)))
                + td(actions_full)
                + "</tr>",
            ]
        )

    def _build_category_table_html(
        self,
        cat_id: str,
        base_path: str,
        public_root_stripped: str,
        site_url: str,
        category_tokens: dict[str, int],
        category_light_tokens: dict[str, int],
    ) -> str:
        """Render the table for a single category (full bundle + light file rows)."""

        def th(text: str) -> str:
            return f"<th>{text}</th>"

        def td(content: str) -> str:
            return f"<td>{content}</td>"

        def fmt_tokens(n: int) -> str:
            return f"{n:,}" if n else "—"

        def make_table(rows: list[str]) -> str:
            header = (
                "<thead><tr>"
                + th("File")
                + th("Description")
                + th("Token Estimate")
                + th("Actions")
                + "</tr></thead>"
            )
            return (
                "<table>\n"
                + header
                + "\n"
                + "<tbody>\n"
                + "\n".join(rows)
                + "\n"
                + "</tbody>\n"
                + "</table>"
            )

        slug = self.slugify_category(cat_id)
        filename = f"{slug}.md"
        light_filename = f"{slug}-light.md"
        url = f"{base_path}{public_root_stripped}/categories/{filename}"
        light_url = f"{base_path}{public_root_stripped}/categories/{light_filename}"
        actions = self._file_utils.generate_dropdown_html(
            url=url, filename=filename, site_url=site_url
        )
        light_actions = self._file_utils.generate_dropdown_html(
            url=light_url, filename=light_filename, site_url=site_url
        )
        return make_table(
            [
                "<tr>"
                + td(f'<code style="white-space: nowrap;">{filename}</code>')
                + td("Full bundle — complete page content for all tagged pages.")
                + td(fmt_tokens(category_tokens.get(cat_id, 0)))
                + td(actions)
                + "</tr>",
                "<tr>"
                + td(f'<code style="white-space: nowrap;">{light_filename}</code>')
                + td(
                    "Lightweight index — titles, URLs, previews, and section headings."
                )
                + td(fmt_tokens(category_light_tokens.get(cat_id, 0)))
                + td(light_actions)
                + "</tr>",
            ]
        )

    def _patch_ai_resources_page(self, site_dir: Path, config: MkDocsConfig) -> None:
        """Inject the AI resources table (with token estimates) into the built HTML page."""
        use_directory_urls = config.get("use_directory_urls", True)
        if use_directory_urls:
            html_path = site_dir / "ai-resources" / "index.html"
        else:
            html_path = site_dir / "ai-resources.html"

        if not html_path.exists():
            log.warning(
                f"[ai_docs] ai-resources HTML not found at {html_path}, skipping table injection"
            )
            return

        site_url = config.get("site_url", "")
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""
        outputs_cfg = self._llms_config.get("outputs", {})
        public_root_stripped = "/" + outputs_cfg.get("public_root", "/ai/").strip("/")
        public_root = public_root_stripped.strip("/")
        content_cfg = self._llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info", {})

        # Estimate tokens for the three aggregate artifact files from their built content
        def _file_tokens(path: Path) -> int:
            return (
                self.estimate_tokens(path.read_text(encoding="utf-8"))
                if path.exists()
                else 0
            )

        # Read token estimates for category bundles and light files from their front matter
        categories_dir = site_dir / public_root / "categories"
        category_tokens: dict[str, int] = {}
        category_light_tokens: dict[str, int] = {}
        for cat_id in categories_info:
            slug = self.slugify_category(cat_id)
            for path, target in [
                (categories_dir / f"{slug}.md", category_tokens),
                (categories_dir / f"{slug}-light.md", category_light_tokens),
            ]:
                if path.exists():
                    fm, _ = self.split_front_matter(path.read_text(encoding="utf-8"))
                    target[cat_id] = int(fm.get("token_estimate", 0) or 0)

        # Read token estimates for the three aggregate artifact files from their content
        aggregate_tokens = {
            "llms_txt": _file_tokens(site_dir / "llms.txt"),
            "site_index": _file_tokens(site_dir / public_root / "site-index.json"),
            "llms_full": _file_tokens(site_dir / public_root / "llms-full.jsonl"),
        }

        page_html = html_path.read_text(encoding="utf-8")

        # Replace aggregate table placeholder
        aggregate_placeholder = "<!-- ai-resources-aggregate-table -->"
        if aggregate_placeholder not in page_html:
            log.warning(
                "[ai_docs] ai-resources-aggregate-table placeholder not found in built HTML"
            )
            return
        aggregate_html = self._build_aggregate_table_html(
            base_path, public_root_stripped, site_url, aggregate_tokens
        )
        page_html = page_html.replace(aggregate_placeholder, aggregate_html, 1)

        # Replace per-category table placeholders
        for cat_id in categories_info:
            slug = self.slugify_category(cat_id)
            cat_placeholder = f"<!-- ai-category-{slug}-table -->"
            if cat_placeholder not in page_html:
                log.warning(f"[ai_docs] placeholder not found for category '{cat_id}'")
                continue
            cat_html = self._build_category_table_html(
                cat_id,
                base_path,
                public_root_stripped,
                site_url,
                category_tokens,
                category_light_tokens,
            )
            page_html = page_html.replace(cat_placeholder, cat_html, 1)

        html_path.write_text(page_html, encoding="utf-8")
        log.info(
            f"[ai_docs] injected resources tables with token estimates into {html_path}"
        )

    def on_post_page(
        self, output: str, *, page: Page, config: MkDocsConfig
    ) -> Optional[str]:
        """Inject the AI actions widget and/or agent skill widgets next to each page's H1."""
        ai_page_actions = self.config.get("ai_page_actions", True)
        agent_skills_enabled = self.config.get("agent_skills", True) and bool(
            self._skills_config
        )

        if not ai_page_actions and not agent_skills_enabled:
            return output

        skills_for_page = (
            self._page_skill_map.get(page.file.src_path, [])
            if agent_skills_enabled
            else []
        )

        # Determine whether to inject the actions widget for this page
        inject_widget = ai_page_actions and not page.is_homepage
        if inject_widget:
            self._ensure_config_loaded(config)
            if self._file_utils.is_page_excluded(
                page.file.src_path,
                page.meta,
                skip_basenames=self._skip_basenames,
                skip_paths=self._skip_paths,
            ):
                inject_widget = False

        if not inject_widget and not skills_for_page:
            return output

        site_url = config.get("site_url", "")

        soup = BeautifulSoup(output, "html.parser")
        md_content = soup.select_one(".md-content")
        if not md_content:
            return output

        modified = False

        # Normalize page URL: strip .html suffix (present when use_directory_urls=false)
        # so the derived .md path always matches the co-located artifact path.
        route = page.url.strip("/")
        if route.endswith(".html"):
            route = route[: -len(".html")]

        # --- Actions widget: toggle pages ---
        toggle_containers = md_content.select(".toggle-container")
        if inject_widget and toggle_containers:
            for container in toggle_containers:
                header_spans = container.select(".toggle-header > span[data-variant]")
                for span in header_spans:
                    h1 = span.find("h1")
                    if not h1:
                        continue
                    variant = span.get("data-variant", "")
                    btn = container.select_one(f'.toggle-btn[data-variant="{variant}"]')
                    data_filename = btn.get("data-filename", "") if btn else ""
                    if data_filename:
                        segments = route.split("/")
                        md_path = "/".join(segments[:-1] + [f"{data_filename}.md"])
                    else:
                        md_path = f"{route}.md"
                    self._wrap_h1(h1, md_path, soup, site_url=site_url)
                    modified = True

        # --- Actions widget: normal pages (no toggle) ---
        if inject_widget and not toggle_containers:
            h1 = md_content.find("h1")
            if h1:
                md_path = f"{route}.md"
                self._wrap_h1(h1, md_path, soup, site_url=site_url)
                modified = True

        # --- Agent skill widgets ---
        # Prepended into the page-meta-chips row below the H1, before the actions widget.
        if skills_for_page:
            h1 = md_content.find("h1")
            if h1:
                widgets_html = self._render_skill_widgets(skills_for_page, site_url)
                widget_soup = BeautifulSoup(widgets_html, "html.parser")
                chips_div = h1.find_next_sibling("div", class_="page-meta-chips")
                if not chips_div:
                    chips_div = soup.new_tag("div")
                    chips_div["class"] = "page-meta-chips"
                    h1.insert_after(chips_div)
                chips_div.insert(0, widget_soup)
                modified = True

        if not modified:
            return output

        return str(soup)

    # Process will start after site build is complete
    def on_post_build(self, config):
        """Generate resolved Markdown files for AI consumption, plus category bundles and site index artifacts."""
        self._ensure_config_loaded(config)
        snippet_cfg = self._llms_config.get("snippets", {})
        self.allow_remote_snippets = snippet_cfg.get("allow_remote", True)
        self.allowed_domains = snippet_cfg.get("allowed_domains", [])

        # Resolve docs_dir from MkDocs config (already parsed/resolved by MkDocs)
        docs_dir = Path(config["docs_dir"]).resolve()
        site_dir = Path(config["site_dir"]).resolve()

        # Snippet directory defaults to docs/.snippets
        snippet_dir = docs_dir / ".snippets"
        if not snippet_dir.exists():
            log.debug(f"[ai_docs] snippet directory not found at {snippet_dir}")

        # Load shared variables (variables.yml sits inside docs_dir)
        variables_path = docs_dir / "variables.yml"
        variables = self.load_yaml(str(variables_path))
        if not variables:
            log.warning(f"[ai_docs] no variables loaded from {variables_path}")

        # Determine docs_base_url for canonical URLs
        project_cfg = self._llms_config.get("project", {})
        docs_base_url = (project_cfg.get("docs_base_url", "") or "").rstrip("/") + "/"

        # Determine AI artifacts root (categories, index, llms files)
        outputs_cfg = self._llms_config.get("outputs", {})
        public_root = outputs_cfg.get("public_root", "/ai/").strip("/")
        ai_root = site_dir / public_root
        ai_root.mkdir(parents=True, exist_ok=True)
        log.info(f"[ai_docs] writing resolved pages alongside HTML in {site_dir}")

        # Loop through docs_dir MD files, filter for exclusions defined in llms_config.json
        content_cfg = self._llms_config.get("content", {})
        exclusions = content_cfg.get("exclusions", {})
        skip_basenames = exclusions.get("skip_basenames", [])
        skip_paths = exclusions.get("skip_paths", [])
        markdown_files = self.get_all_markdown_files(
            docs_dir, skip_basenames, skip_paths
        )

        log.info(f"[ai_docs] found {len(markdown_files)} markdown files")

        build_timestamp = datetime.now(timezone.utc).isoformat()

        # One-time check: are we inside a git repo?
        try:
            _check = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=5,
                cwd=str(docs_dir),
            )
            has_git = _check.returncode == 0
        except (subprocess.SubprocessError, OSError):
            has_git = False

        # Batch-fetch git timestamps in a single subprocess call.
        if has_git:
            git_timestamps = self.batch_git_last_updated(markdown_files, str(docs_dir))
        else:
            git_timestamps = {}

        processed = 0

        ai_pages: list[dict] = []

        # For each file in markdown_files
        for md_path in markdown_files:
            text = Path(md_path).read_text(encoding="utf-8")
            # Separate, filter, map, and return desired front matter
            front_matter, body = self.split_front_matter(text)
            reduced_fm = self.map_front_matter(front_matter)
            categories = self.normalize_categories(reduced_fm.get("categories"))
            if categories:
                reduced_fm["categories"] = categories
            elif "categories" in reduced_fm:
                reduced_fm.pop("categories")
            # Resolve snippet placeholders first
            snippet_body = self.replace_snippet_placeholders(
                body, snippet_dir, variables
            )
            if snippet_body != body:
                log.debug(f"[ai_docs] resolved snippets in {md_path}")
            body = snippet_body
            # Resolve variable placeholders against variables.yml definitions
            resolved_body = self.resolve_markdown_placeholders(body, variables)
            if resolved_body != body:
                log.debug(f"[ai_docs] resolved placeholders in {md_path}")
            # Remove HTML comments after substitutions
            cleaned_body = self.remove_html_comments(resolved_body)
            if cleaned_body != resolved_body:
                log.debug(f"[ai_docs] stripped HTML comments in {md_path}")
            # Remove pymdownx attribute blocks from inline links
            cleaned_body = self.remove_attribute_syntax(cleaned_body)
            # Convert path to slug and canonical URLs
            rel_path = Path(md_path).relative_to(docs_dir)
            rel_no_ext = str(rel_path.with_suffix(""))
            slug, url = self.compute_slug_and_url(rel_no_ext, docs_base_url)
            # Calculate word count, token estimate, version hash, and last-updated timestamp
            word_count = self.word_count(cleaned_body)
            token_estimate = self.estimate_tokens(cleaned_body)
            version_hash = self.sha256_text(cleaned_body)
            last_updated = git_timestamps.get(md_path)
            if not last_updated:
                last_updated = self.get_git_last_updated(md_path, has_git)

            # Output resolved Markdown file to AI artifacts directory
            header = dict(reduced_fm)
            header["url"] = url
            header["word_count"] = word_count
            header["token_estimate"] = token_estimate
            header["version_hash"] = version_hash
            header["last_updated"] = last_updated
            route = rel_no_ext.replace(os.sep, "/")
            if route.endswith("/index"):
                route = route[: -len("/index")]
            self.write_ai_page(site_dir / (route + ".md"), header, cleaned_body)
            processed += 1
            # Creates list used later for category file creation
            cats = reduced_fm.get("categories") or []
            if isinstance(cats, str):
                cats_value = [cats]
            else:
                cats_value = cats

            ai_pages.append(
                {
                    "slug": slug,
                    "path": Path(md_path),
                    "title": header.get("title") or slug,
                    "description": header.get("description") or "",
                    "categories": cats_value,
                    "url": url,
                    "word_count": word_count,
                    "token_estimate": token_estimate,
                    "version_hash": version_hash,
                    "last_updated": last_updated,
                    "body": cleaned_body,
                }
            )

            log.debug(f"[ai_docs] {md_path} FM keys: {list(front_matter.keys())}")
            log.debug(f"[ai_docs] {md_path} mapped FM: {reduced_fm}")

        log.info(f"[ai_docs] processed {processed} AI pages")
        if ai_pages:
            log.debug(
                f"[ai_docs] sample AI page metadata: slug={ai_pages[0]['slug']} cats={ai_pages[0].get('categories')}"
            )

        # Build category bundles based on current AI pages
        self.build_category_bundles(ai_pages, ai_root, build_timestamp)
        # Build site index + llms JSONL artifacts
        enriched = self.build_site_index(ai_pages, ai_root, build_timestamp)
        # Build per-category lightweight index files
        self.build_category_light(enriched, ai_root, build_timestamp)
        # Build llms.txt for downstream LLM usage directly into the site output
        self.build_llms_txt(ai_pages, site_dir, build_timestamp)
        # Inject resources table with token estimates into the built ai-resources HTML
        # (must run after all artifact files are written so their sizes can be estimated)
        if self.config.get("ai_resources_page", True):
            self._patch_ai_resources_page(site_dir, config)

        # --- Agent skills file generation ---
        if self.config.get("agent_skills", True) and self._skills_config:
            skills = self._skills_config.get("skills", [])
            if skills:
                project = self._skills_config.get("project", {})
                reference_repos = self._skills_config.get("reference_repos", {})
                skills_output_dir = (
                    site_dir / self._skills_public_root / self._skills_dir_name
                )
                if (
                    skills_output_dir == site_dir
                    or not skills_output_dir.is_relative_to(site_dir)
                ):
                    log.error(
                        f"[ai_docs] skills_output_dir '{skills_output_dir}' is not "
                        f"safely nested under site_dir '{site_dir}' — "
                        "skipping skill generation"
                    )
                    return
                if skills_output_dir.exists():
                    shutil.rmtree(skills_output_dir)
                skills_output_dir.mkdir(parents=True, exist_ok=True)
                log.info(f"[ai_docs] generating {len(skills)} skill file(s)")
                rendered_skills = []
                for skill in skills:
                    skill_id = skill.get("id", "unknown")
                    try:
                        content = self._render_skill(skill, project, reference_repos)
                        output_path = skills_output_dir / f"{skill_id}.md"
                        output_path.write_text(content, encoding="utf-8")
                        log.info(f"[ai_docs] wrote {output_path}")
                        rendered_skills.append(skill)
                    except Exception as e:
                        log.error(
                            f"[ai_docs] failed to generate skill '{skill_id}': {e}"
                        )
                self._write_skills_index(rendered_skills, project, skills_output_dir)
            else:
                log.warning(
                    "[ai_docs] agent_skills_config loaded but no skills defined"
                )

    # ------------------------------------------------------------------
    # Helper static functions
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_git_timestamp(ts: str) -> str:
        """Normalize a git ISO-8601 timestamp to UTC isoformat."""
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone(timezone.utc).isoformat()

    @staticmethod
    def batch_git_last_updated(file_paths: list[str], repo_dir: str) -> dict[str, str]:
        """Retrieve the last-commit timestamp for many files in a single git call.

        Returns a dict mapping each absolute file path to its ISO-8601 UTC
        timestamp.  Files not found in git history are omitted from the result.
        """
        if not file_paths:
            return {}

        # Build relative paths from the repo root for the git query.
        abs_repo = os.path.abspath(repo_dir)
        rel_paths = []
        abs_by_rel: dict[str, str] = {}
        for fp in file_paths:
            rel = os.path.relpath(fp, abs_repo).replace(os.sep, "/")
            rel_paths.append(rel)
            abs_by_rel[rel] = fp

        try:
            result = subprocess.run(
                [
                    "git",
                    "log",
                    "--pretty=format:%cI",
                    "--name-only",
                    "--diff-filter=ACMR",
                    "--",
                    *rel_paths,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=abs_repo,
            )
            if result.returncode != 0:
                return {}
        except (subprocess.SubprocessError, OSError):
            return {}

        # Parse output: alternating lines of timestamp then changed file names,
        # separated by blank lines between commits.
        timestamps: dict[str, str] = {}
        current_ts = ""
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                current_ts = ""
                continue
            # Timestamp lines match ISO-8601 format from --pretty=format:%cI.
            if current_ts == "" and re.match(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", line
            ):
                current_ts = line
            elif current_ts:
                # This is a file path — only record the first (most recent) ts.
                norm = line.replace("\\", "/")
                if norm not in timestamps:
                    timestamps[norm] = current_ts

        # Map back to absolute paths.
        result_map: dict[str, str] = {}
        for rel, ts in timestamps.items():
            abs_path = abs_by_rel.get(rel)
            if abs_path:
                try:
                    result_map[abs_path] = AIDocsPlugin._parse_git_timestamp(ts)
                except (ValueError, OSError):
                    pass
        return result_map

    @staticmethod
    def get_git_last_updated(file_path: str, has_git: bool = True) -> str:
        """Return the ISO-8601 UTC timestamp of the last git commit that touched *file_path*.

        Falls back to the file's filesystem mtime when git history is
        unavailable (e.g. outside a repo, or a file not yet committed).

        When *has_git* is False the git subprocess is skipped entirely,
        avoiding repeated spawn-and-fail overhead in non-git environments.
        """
        if not has_git:
            mtime = os.path.getmtime(file_path)
            return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
        try:
            result = subprocess.run(
                ["git", "log", "-1", "--format=%cI", "--", os.path.basename(file_path)],
                capture_output=True,
                text=True,
                timeout=10,
                cwd=os.path.dirname(file_path) or ".",
            )
            ts = result.stdout.strip()
            if ts:
                return AIDocsPlugin._parse_git_timestamp(ts)
        except (subprocess.SubprocessError, OSError):
            pass
        # Fallback: filesystem modification time
        mtime = os.path.getmtime(file_path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()

    # File discovery and filtering per skip names/paths in llms_config.json
    @staticmethod
    def get_all_markdown_files(docs_dir, skip_basenames, skip_paths):
        """Collect *.md|*.mdx, skipping dot-files, dot-directories, manual skip_paths, and skip_basenames.

        The root index.md (homepage) is always excluded. To skip all
        index.md files site-wide, add ``index.md`` to ``skip_basenames``
        in ``llms_config.json``.
        """
        docs_dir_norm = os.path.normpath(str(docs_dir))
        results = []
        for root, dirs, files in os.walk(docs_dir):
            # Always skip hidden (dot) directories
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            # Skip manually specified paths (substring match)
            if any(x in root for x in skip_paths):
                continue
            for file in files:
                if not file.endswith((".md", ".mdx")):
                    continue
                # Always skip hidden (dot) files
                if file.startswith("."):
                    continue
                if file in skip_basenames:
                    continue
                # Always skip the root index.md (homepage)
                if file == "index.md" and os.path.normpath(root) == docs_dir_norm:
                    continue
                results.append(os.path.join(root, file))
        return sorted(results)

    @staticmethod
    def load_yaml(yaml_file: str):
        """Load a YAML file; return {} if missing/empty."""
        if not os.path.exists(yaml_file):
            return {}
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            log.warning(f"[ai_docs] unable to parse YAML file {yaml_file}: {exc}")
            return {}
        return data or {}

    # Front-matter helpers

    @staticmethod
    def split_front_matter(source_text: str):
        """
        Return (front_matter_dict, body_text). If no FM, dict={} and body=source_text.
        """
        m = FM_PATTERN.match(source_text)
        if not m:
            return {}, source_text
        fm_text = m.group(1)
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
        body = source_text[m.end() :]
        return fm, body

    @staticmethod
    def map_front_matter(fm: dict) -> dict:
        """
        Emit front matter fields:
        - title (as-is)
        - description (as-is)
        - categories (as-is)
        """
        out = {}
        if "title" in fm:
            out["title"] = fm["title"]
        if "description" in fm:
            out["description"] = fm["description"]
        if "categories" in fm:
            out["categories"] = fm["categories"]
        return out

    @staticmethod
    def normalize_categories(raw) -> list[str]:
        """Normalize categories value into a list of non-empty strings."""
        if raw is None:
            return []
        result: list[str] = []
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, str):
            val = raw.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = yaml.safe_load(val)
                    candidates = parsed if isinstance(parsed, list) else [val]
                except Exception:
                    candidates = [val]
            else:
                candidates = val.split(",")
        else:
            candidates = [raw]
        for item in candidates:
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    # Resolve variables and placeholders

    @staticmethod
    def get_value_from_path(data, path):
        """Simple dotted lookup (dicts only, no arrays)."""
        if not path:
            return None
        keys = [k.strip() for k in path.split(".") if k.strip()]
        value = data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    @staticmethod
    def resolve_markdown_placeholders(content: str, variables: dict) -> str:
        """Replace {{ dotted.keys }} using variables dict; leave unknowns intact."""

        def replacer(match):
            key_path = match.group(1)
            value = AIDocsPlugin.get_value_from_path(variables, key_path)
            return str(value) if value is not None else match.group(0)

        return PLACEHOLDER_PATTERN.sub(replacer, content)

    # Replace snippet placeholders with code blocks

    @staticmethod
    def parse_line_range(snippet_path: str):
        """Split snippet reference into filename and optional start/end line numbers."""
        ref = snippet_path.strip()
        if not ref:
            return "", None, None, None

        double_match = SNIPPET_DOUBLE_RANGE_RE.match(ref)
        if double_match:
            file_only = double_match.group("path")
            line_end = AIDocsPlugin._parse_line_number(double_match.group("end"))
            return file_only, 1, line_end, None

        range_match = SNIPPET_RANGE_RE.match(ref)
        if range_match:
            file_only = range_match.group("path")
            line_start = AIDocsPlugin._parse_line_number(range_match.group("start"))
            line_end = AIDocsPlugin._parse_line_number(range_match.group("end"))
            return file_only, line_start, line_end, None

        single_match = SNIPPET_SINGLE_RANGE_RE.match(ref)
        if single_match:
            file_only = single_match.group("path")
            line_start = AIDocsPlugin._parse_line_number(single_match.group("start"))
            return file_only, line_start, None, None

        idx = AIDocsPlugin._find_selector_colon(ref)
        if idx is not None:
            section = ref[idx + 1 :].strip()
            file_only = ref[:idx]
            return file_only, None, None, section

        return ref, None, None, None

    @staticmethod
    def _parse_line_number(value: str) -> int | None:
        """Parse a signed integer string; return None if invalid/empty."""
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        if text[0] in "+-":
            sign = -1 if text[0] == "-" else 1
            digits = text[1:]
            if not digits.isdigit():
                return None
            return sign * int(digits)
        if text.isdigit():
            return int(text)
        return None

    @staticmethod
    def _find_selector_colon(reference: str) -> int | None:
        """Return index of the last ':' separator that is not part of a scheme like 'http://'."""
        for idx in range(len(reference) - 1, -1, -1):
            if reference[idx] != ":":
                continue
            # Skip if part of '://'
            if reference[idx : idx + 3] == "://":
                continue
            # Skip Windows drive letters (:'\' or :'/')
            if idx + 1 < len(reference) and reference[idx + 1] in ("/", "\\"):
                continue
            # Skip double-colon sequences (handled elsewhere)
            if idx > 0 and reference[idx - 1] == ":":
                continue
            return idx
        return None

    def apply_snippet_selectors(
        self,
        content: str,
        line_start: int | None,
        line_end: int | None,
        section: str | None,
        snippet_ref: str,
    ) -> str | None:
        """Apply section or line slicing to snippet content."""
        selected = content
        if section:
            section_content = self.extract_snippet_section(
                selected, section, snippet_ref
            )
            if section_content is None:
                return None
            selected = section_content
        if line_start is not None or line_end is not None:
            lines = selected.split("\n")
            total = len(lines)
            if total == 0:
                return ""
            start_idx = self._normalize_line_index(line_start, total, default=1)
            end_idx = self._normalize_line_index(line_end, total, default=total)
            if end_idx < start_idx:
                log.warning(
                    f"[ai_docs] invalid line range ({line_start}:{line_end}) in {snippet_ref}"
                )
                return ""
            selected = "\n".join(lines[start_idx - 1 : end_idx])
        return selected

    @staticmethod
    def _normalize_line_index(index: int | None, total: int, default: int) -> int:
        """Convert possible negative/zero indexes into 1-based inclusive bounds."""
        if index is None:
            value = default
        else:
            value = index
            if value == 0:
                value = 1
            if value < 0:
                value = total + value + 1
        value = max(1, min(value, total)) if total else 1
        return value

    @staticmethod
    def extract_snippet_section(
        content: str, section: str, snippet_ref: str
    ) -> str | None:
        """Return the text between --8<-- [start:section] and [end:section] markers."""
        target = section.strip().lower()
        if not target:
            return None
        lines = content.split("\n")
        start_idx = None
        for idx, line in enumerate(lines):
            match = SNIPPET_SECTION_REGEX.match(line.strip())
            if not match:
                continue
            name = (match.group("name") or "").strip().lower()
            if name != target:
                continue
            kind = (match.group("kind") or "").strip().lower()
            if kind == "start":
                start_idx = idx + 1
            elif kind == "end" and start_idx is not None:
                return "\n".join(lines[start_idx:idx])
        if start_idx is not None:
            log.warning(
                f"[ai_docs] snippet section '{section}' missing end marker in {snippet_ref}"
            )
        else:
            log.warning(
                f"[ai_docs] snippet section '{section}' not found in {snippet_ref}"
            )
        return None

    def fetch_local_snippet(self, snippet_ref: str, snippet_directory: Path) -> str:
        """Load snippet content from docs/.snippets (optionally slicing by line range)."""
        file_only, line_start, line_end, section = self.parse_line_range(snippet_ref)
        snippet_directory_root = Path(snippet_directory).resolve()
        absolute_snippet_path = (snippet_directory_root / file_only).resolve()

        # Ensure the resolved path is still within the snippet directory to prevent traversal
        try:
            absolute_snippet_path.relative_to(snippet_directory_root)
        except ValueError:
            log.warning(
                f"[ai_docs] invalid local snippet path (outside snippet directory): {snippet_ref}"
            )
            return f"<!-- INVALID LOCAL SNIPPET PATH {snippet_ref} -->"
        if not absolute_snippet_path.exists():
            log.warning(f"[ai_docs] missing local snippet {snippet_ref}")
            return f"<!-- MISSING LOCAL SNIPPET {snippet_ref} -->"

        snippet_content = absolute_snippet_path.read_text(encoding="utf-8")
        snippet_content = self.apply_snippet_selectors(
            snippet_content, line_start, line_end, section, snippet_ref
        )
        if snippet_content is None:
            return f"<!-- MISSING SNIPPET SECTION {snippet_ref} -->"
        return self.strip_snippet_section_markers(snippet_content)

    def _validate_url(self, url: str) -> str | None:
        """Validate a URL against SSRF attacks.

        Returns an error message if the URL is blocked, or None if it is safe.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname

        if not hostname:
            return "missing hostname"

        if parsed.scheme not in ("http", "https"):
            return f"disallowed scheme: {parsed.scheme}"

        if self.allowed_domains:
            if not any(
                hostname == domain or hostname.endswith(f".{domain}")
                for domain in self.allowed_domains
            ):
                return f"hostname {hostname} not in allowed_domains"

        try:
            resolved_ips = socket.getaddrinfo(hostname, None)
        except socket.gaierror:
            return f"cannot resolve hostname: {hostname}"

        for _family, _type, _proto, _canonname, sockaddr in resolved_ips:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_reserved or ip.is_loopback or ip.is_link_local:
                return f"hostname {hostname} resolves to blocked address {ip}"

        return None

    def fetch_remote_snippet(self, snippet_ref: str) -> str:
        """Retrieve remote snippet via HTTP unless remote fetching is disabled."""
        if not self.allow_remote_snippets:
            return f"<!-- REMOTE SNIPPET SKIPPED (disabled): {snippet_ref} -->"
        url, line_start, line_end, section = self.parse_line_range(snippet_ref)
        if not url.startswith("http"):
            log.warning(f"[ai_docs] invalid remote snippet ref {snippet_ref}")
            return f"<!-- INVALID REMOTE SNIPPET {snippet_ref} -->"

        block_reason = self._validate_url(url)
        if block_reason:
            log.warning(
                f"[ai_docs] blocked remote snippet {snippet_ref}: {block_reason}"
            )
            return f"<!-- BLOCKED REMOTE SNIPPET {snippet_ref} -->"

        if url in self._remote_snippet_cache:
            snippet_content = self._remote_snippet_cache[url]
            if snippet_content is None:
                return f"<!-- ERROR FETCHING REMOTE SNIPPET {snippet_ref} -->"
        else:
            try:
                _MAX_SNIPPET_BYTES = 10 * 1024 * 1024  # 10 MB
                with urllib_request.urlopen(url, timeout=10) as response:
                    content_length = response.headers.get("Content-Length")
                    if (
                        content_length
                        and content_length.isdigit()
                        and int(content_length) > _MAX_SNIPPET_BYTES
                    ):
                        log.warning(
                            f"[ai_docs] remote snippet too large ({content_length} bytes): {snippet_ref}"
                        )
                        self._remote_snippet_cache[url] = None
                        return f"<!-- REMOTE SNIPPET TOO LARGE {snippet_ref} -->"
                    raw = response.read(_MAX_SNIPPET_BYTES + 1)
                    if len(raw) > _MAX_SNIPPET_BYTES:
                        log.warning(
                            f"[ai_docs] remote snippet exceeded {_MAX_SNIPPET_BYTES} bytes: {snippet_ref}"
                        )
                        self._remote_snippet_cache[url] = None
                        return f"<!-- REMOTE SNIPPET TOO LARGE {snippet_ref} -->"
                    snippet_content = raw.decode("utf-8")
                self._remote_snippet_cache[url] = snippet_content
            except (urllib_error.URLError, urllib_error.HTTPError) as exc:
                log.warning(
                    f"[ai_docs] error fetching remote snippet {snippet_ref}: {exc}"
                )
                self._remote_snippet_cache[url] = None
                return f"<!-- ERROR FETCHING REMOTE SNIPPET {snippet_ref} -->"

        snippet_content = self.apply_snippet_selectors(
            snippet_content, line_start, line_end, section, snippet_ref
        )
        if snippet_content is None:
            return f"<!-- MISSING REMOTE SNIPPET SECTION {snippet_ref} -->"
        snippet_content = snippet_content.strip()
        return self.strip_snippet_section_markers(snippet_content)

    def replace_snippet_placeholders(
        self, markdown: str, snippet_directory: Path, variables: dict
    ) -> str:
        """
        Recursively replace --8<-- snippet placeholders until none remain.
        Snippet references can include {{variables}} which are resolved first.
        """

        def fetch_snippet(snippet_ref: str) -> str:
            resolved_path = self.resolve_markdown_placeholders(snippet_ref, variables)
            if resolved_path.startswith("http"):
                return self.fetch_remote_snippet(resolved_path)
            return self.fetch_local_snippet(resolved_path, snippet_directory)

        def replace_line_match(match: re.Match) -> str:
            indent = match.group("indent") or ""
            snippet_ref = match.group("ref")
            snippet_content = fetch_snippet(snippet_ref).replace("\r\n", "\n")
            if not indent:
                return snippet_content
            indented = [
                f"{indent}{line}" if line else ""
                for line in snippet_content.split("\n")
            ]
            return "\n".join(indented)

        def replace_inline_match(match: re.Match) -> str:
            snippet_ref = match.group(1)
            return fetch_snippet(snippet_ref)

        max_depth = 100
        previous = None
        iterations = 0
        while previous != markdown:
            iterations += 1
            if iterations > max_depth:
                log.warning(
                    "[ai_docs] snippet expansion exceeded %d iterations — "
                    "possible circular reference, stopping expansion",
                    max_depth,
                )
                break
            previous = markdown
            markdown = SNIPPET_LINE_REGEX.sub(replace_line_match, markdown)
            markdown = SNIPPET_TOKEN_REGEX.sub(replace_inline_match, markdown)
        return markdown

    # Remove HTML comments from Markdown

    @staticmethod
    def remove_html_comments(content: str) -> str:
        """Remove <!-- ... --> comments (multiline)."""
        return re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)

    @staticmethod
    def remove_attribute_syntax(content: str) -> str:
        r"""Remove pymdownx attribute blocks from inline links e.g. [text](url){target=\_blank}."""
        return re.sub(r"(?<=\))\s*\{[^}]+\}", "", content)

    @staticmethod
    def strip_snippet_section_markers(content: str) -> str:
        """Remove snippet section markers (# --8<-- [start:end]) from snippet content."""
        lines = content.splitlines()
        cleaned = [ln for ln in lines if not SNIPPET_SECTION_REGEX.match(ln.strip())]
        return "\n".join(cleaned)

    # Word count & token estimation

    @staticmethod
    def word_count(content: str) -> int:
        return len(re.findall(r"\b\w+\b", content, flags=re.UNICODE))

    @staticmethod
    def estimate_tokens(content: str) -> int:
        return len(re.findall(r"\w+|[^\s\w]", content, flags=re.UNICODE))

    @staticmethod
    def sha256_text(content: str) -> str:
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def extract_outline_and_sections(
        self, body: str, max_depth: int = 3
    ) -> tuple[list[dict], list[dict]]:
        lines = body.splitlines(keepends=True)
        in_code = False
        fence = None

        starts = [0]
        for ln in lines[:-1]:
            starts.append(starts[-1] + len(ln))

        outline: list[dict] = []
        sections_meta: list[tuple[int, int, str, str]] = []
        anchors_seen: dict[str, int] = {}

        for idx, line in enumerate(lines):
            m_fence = re.match(r"^(\s*)(`{3,}|~{3,})", line)
            if m_fence:
                token = m_fence.group(2)
                if not in_code:
                    in_code, fence = True, token
                elif token == fence:
                    in_code, fence = False, None
                continue

            if in_code:
                continue

            m = HEADING_RE.match(line)
            if not m:
                continue
            hashes, text = m.group(1), m.group(2).strip()
            depth = len(hashes)
            if depth < 2 or depth > max_depth:
                continue
            anchor = self.slugify_anchor(text, anchors_seen)
            outline.append({"depth": depth, "title": text, "anchor": anchor})
            sections_meta.append((depth, idx, text, anchor))

        sections: list[dict] = []
        for idx, (depth, line_idx, title, anchor) in enumerate(sections_meta):
            start_char = starts[line_idx]
            next_start = len(body)
            if idx + 1 < len(sections_meta):
                next_start = starts[sections_meta[idx + 1][1]]
            section_text = body[start_char:next_start].strip()
            sections.append(
                {
                    "index": idx,
                    "depth": depth,
                    "title": title,
                    "anchor": anchor,
                    "start_char": start_char,
                    "end_char": next_start,
                    "text": section_text,
                }
            )

        return outline, sections

    def extract_preview(self, body: str, max_chars: int = 500) -> str:
        lines = body.splitlines()
        in_code = False
        para: list[str] = []

        def bad_start(s: str) -> bool:
            s = s.lstrip()
            return (
                not s
                or s.startswith("#")
                or s.startswith(">")
                or s.startswith("- ")
                or s.startswith("* ")
                or re.match(r"^\d+\.\s", s) is not None
            )

        def finish(buf: list[str]) -> str:
            text = " ".join(" ".join(buf).split())
            return text[:max_chars].rstrip()

        for line in lines:
            if re.match(r"^(\s*)(`{3,}|~{3,})", line):
                in_code = not in_code
                if para:
                    break
                continue
            if in_code:
                continue
            if line.strip() == "":
                if para:
                    break
                continue
            if not para and bad_start(line):
                continue
            para.append(line)

        return finish(para) if para else ""

    # Convert file path to slug, create markdown file URL

    @staticmethod
    def compute_slug_and_url(rel_path_no_ext: str, docs_base_url: str):
        """
        rel_path_no_ext: docs-relative path without extension, using OS separators.
        - If endswith '/index', drop the trailing 'index' for the URL and slug base.
        - Slug = path segments joined by '-', lowercased.
        - URL = docs_base_url + route + '/'
        """
        # Normalize to forward slashes
        route = rel_path_no_ext.replace(os.sep, "/")
        if route.endswith("/index"):
            route = route[: -len("/index")]
        # slug
        slug = route.replace("/", "-").lower()
        # url (ensure one trailing slash)
        if not route.endswith("/"):
            route = f"{route}/"
        url = f"{docs_base_url}{route}"
        return slug, url

    def get_ai_output_dir(self, base_dir: Path) -> Path:
        """Resolve target directory for resolved markdown files."""
        repo_cfg = self._llms_config.get("repository", {})
        ai_path = repo_cfg.get("ai_artifacts_path")
        if ai_path:
            ai_path = Path(ai_path)
            if not ai_path.is_absolute():
                ai_path = base_dir / ai_path
        else:
            outputs_cfg = self._llms_config.get("outputs", {})
            public_root = outputs_cfg.get("public_root", "/ai/").strip("/")
            pages_dir = outputs_cfg.get("files", {}).get("pages_dir", "pages")
            ai_path = base_dir / public_root / pages_dir

        base_dir_resolved = base_dir.resolve()
        ai_path = ai_path.resolve()
        try:
            # Ensure the resolved artifacts directory stays within the site base directory.
            ai_path.relative_to(base_dir_resolved)
        except ValueError:
            raise ValueError(
                "Configured ai_artifacts_path resolves outside of the site directory"
            ) from None

        return ai_path

    def reset_directory(self, output_dir: Path) -> None:
        """Remove existing artifacts before writing fresh files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for entry in output_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()

    def write_ai_page(self, out_path: Path, header: dict, body: str):
        """Write resolved markdown with YAML front matter."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        fm_obj = {}
        for key in (
            "title",
            "description",
            "categories",
            "url",
            "word_count",
            "token_estimate",
            "version_hash",
            "last_updated",
        ):
            val = header.get(key)
            if val not in (None, "", []):
                fm_obj[key] = val

        fm_yaml = yaml.safe_dump(
            fm_obj, sort_keys=False, allow_unicode=True, width=4096
        ).strip()
        content = f"---\n{fm_yaml}\n---\n\n{body.strip()}\n"
        with out_path.open("w", encoding="utf-8") as fh:
            fh.write(content)
        log.debug(f"[ai_docs] wrote {out_path}")

    # Category and slug helper functions
    @staticmethod
    def slugify_category(name: str) -> str:
        s = name.strip().lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "category"

    @staticmethod
    def slugify_anchor(text: str, seen: dict[str, int]) -> str:
        value = text.strip().lower()
        value = re.sub(r"`+", "", value)
        value = re.sub(r"[^\w\s\-]", "", value, flags=re.UNICODE)
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        if not value:
            value = "section"
        if value in seen:
            seen[value] += 1
            value = f"{value}-{seen[value]}"
        else:
            seen[value] = 1
        return value

    @staticmethod
    def select_pages_for_category(category: str, pages: list[dict]) -> list[dict]:
        cat_slug = AIDocsPlugin.slugify_category(category)
        selected = []
        for page in pages:
            cats = page.get("categories") or []
            if isinstance(cats, str):
                cats_iter = [cats]
            else:
                cats_iter = cats
            if any(
                AIDocsPlugin.slugify_category(str(c)) == cat_slug for c in cats_iter
            ):
                selected.append(page)
        return selected

    @staticmethod
    def union_pages(sets: list[list[dict]]) -> list[dict]:
        seen = set()
        out: list[dict] = []
        for lst in sets:
            for p in lst:
                slug = p.get("slug")
                if slug in seen:
                    continue
                seen.add(slug)
                out.append(p)
        return out

    def write_category_bundle(
        self,
        out_path: Path,
        category: str,
        includes_base: bool,
        base_categories: list[str],
        pages: list[dict],
        build_timestamp: str = "",
    ) -> None:
        """Concatenate pages into a single Markdown bundle."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        total_words = sum(p.get("word_count", 0) for p in pages)
        total_tokens = sum(p.get("token_estimate", 0) for p in pages)

        fm_obj = {
            "category": category,
            "includes_base_categories": bool(includes_base),
            "base_categories": base_categories if includes_base else [],
            "word_count": total_words,
            "token_estimate": total_tokens,
            "page_count": len(pages),
        }
        if build_timestamp:
            fm_obj["build_timestamp"] = build_timestamp

        # Build body content first so we can hash it for the front matter
        body_lines: list[str] = []
        body_lines.append(f"# Begin New Bundle: {category}")
        if includes_base and base_categories:
            body_lines.append(
                f"Includes shared base categories: {', '.join(base_categories)}"
            )
        body_lines.append("")

        for page in pages:
            body_lines.append("\n---\n")
            title = page.get("title") or page["slug"]
            body_lines.append(f"Page Title: {title}\n")
            resolved_url = page.get("url", "").rstrip("/") + ".md"
            body_lines.append(f"- Resolved Markdown: {resolved_url}")
            html_url = page.get("url")
            if html_url:
                body_lines.append(f"- Canonical (HTML): {html_url}")
            description = page.get("description")
            if description:
                body_lines.append(f"- Summary: {description}")
            body_lines.append(
                f"- Word Count: {page.get('word_count', 0)}; Token Estimate: {page.get('token_estimate', 0)}"
            )
            body_lines.append(f"- Last Updated: {page.get('last_updated', '')}")
            body_lines.append(f"- Version Hash: {page.get('version_hash', '')}")
            body_lines.append("")
            body_lines.append(page.get("body", "").strip())
            body_lines.append("")

        bundle_body = "\n".join(body_lines)
        fm_obj["version_hash"] = self.sha256_text(bundle_body)

        fm_yaml = yaml.safe_dump(
            fm_obj, sort_keys=False, allow_unicode=True, width=4096
        ).strip()

        content = f"---\n{fm_yaml}\n---\n\n{bundle_body}"
        out_path.write_text(content, encoding="utf-8")

    def build_category_bundles(
        self, pages: list[dict], ai_root: Path, build_timestamp: str = ""
    ) -> None:
        """Generate per-category bundle files based on AI pages."""
        content_cfg = self._llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info") or {}
        if not categories_info:
            log.info("[ai_docs] no categories configured; skipping bundles")
            return
        base_cats = content_cfg.get("base_context_categories") or []

        categories_dir = ai_root / "categories"
        self.reset_directory(categories_dir)

        base_sets = []
        for cat_id in base_cats:
            base_sets.append(self.select_pages_for_category(cat_id, pages))
        base_union = self.union_pages(base_sets) if base_sets else []

        log.debug(
            f"[ai_docs] building category bundles for {len(categories_info)} categories; sample page cats: {pages[0].get('categories') if pages else 'none'}"
        )

        for category_id, cat_info in categories_info.items():
            cat_slug = self.slugify_category(category_id)
            out_path = categories_dir / f"{cat_slug}.md"
            is_base = category_id in base_cats

            display_name = cat_info.get("name", category_id)

            category_pages = self.select_pages_for_category(category_id, pages)

            if is_base:
                bundle_pages = sorted(
                    category_pages, key=lambda p: p.get("title", "").lower()
                )
                log.debug(
                    f"[ai_docs] base bundle {display_name} ({category_id}): {len(bundle_pages)} pages"
                )
                self.write_category_bundle(
                    out_path,
                    display_name,
                    False,
                    base_cats,
                    bundle_pages,
                    build_timestamp,
                )
            else:
                combined = self.union_pages([base_union, category_pages])
                bundle_pages = sorted(
                    combined, key=lambda p: p.get("title", "").lower()
                )
                log.debug(
                    f"[ai_docs] category bundle {display_name} ({category_id}): base={len(base_union)} cat-only={len(category_pages)} total={len(bundle_pages)}"
                )
                self.write_category_bundle(
                    out_path,
                    display_name,
                    True,
                    base_cats,
                    bundle_pages,
                    build_timestamp,
                )

        log.info(f"[ai_docs] category bundles written to {categories_dir}")

    # Create full-site content related AI artifact files
    def build_site_index(
        self, pages: list[dict], ai_root: Path, build_timestamp: str = ""
    ) -> list[dict]:
        """Generate site-index.json and llms_full.jsonl from AI pages."""
        if not pages:
            return []
        outputs = self._llms_config.get("outputs", {})
        files_cfg = outputs.get("files", {})
        site_index_name = files_cfg.get("site_index", "site-index.json")
        llms_full_name = files_cfg.get("llms_full", "llms-full.jsonl")
        preview_chars = outputs.get("preview_chars", 500)
        max_depth = outputs.get("outline_max_depth", 3)
        token_estimator = "heuristic-v1"

        index_path = ai_root / site_index_name
        llms_path = ai_root / llms_full_name
        index_path.parent.mkdir(parents=True, exist_ok=True)
        llms_path.parent.mkdir(parents=True, exist_ok=True)

        site_index_entries: list[dict] = []
        jsonl_lines: list[str] = []

        for page in pages:
            body = page.get("body", "")
            outline, sections = self.extract_outline_and_sections(
                body, max_depth=max_depth
            )
            preview = page.get("description", "") or self.extract_preview(
                body, max_chars=preview_chars
            )
            page_version_hash = page.get("version_hash", self.sha256_text(body))
            page_last_updated = page.get("last_updated", "")

            total_section_tokens = 0
            for sec in sections:
                sec_tokens = self.estimate_tokens(sec["text"])
                total_section_tokens += sec_tokens
                jsonl_lines.append(
                    json.dumps(
                        {
                            "page_id": page["slug"],
                            "page_title": page.get("title"),
                            "index": sec["index"],
                            "depth": sec["depth"],
                            "title": sec["title"],
                            "anchor": sec["anchor"],
                            "start_char": sec["start_char"],
                            "end_char": sec["end_char"],
                            "estimated_token_count": sec_tokens,
                            "token_estimator": token_estimator,
                            "page_version_hash": page_version_hash,
                            "last_updated": page_last_updated,
                            "text": sec["text"],
                        },
                        ensure_ascii=False,
                    )
                )

            stats = {
                "word_count": page.get("word_count", 0),
                "token_estimate": page.get("token_estimate", total_section_tokens),
                "headings": len(outline),
                "sections_indexed": len(sections),
            }

            entry = {
                "id": page["slug"],
                "title": page.get("title"),
                "slug": page["slug"],
                "categories": page.get("categories", []),
                "raw_md_url": page.get("url", "").rstrip("/") + ".md",
                "html_url": page.get("url"),
                "preview": preview,
                "outline": outline,
                "stats": stats,
                "version_hash": page_version_hash,
                "last_updated": page_last_updated,
                "token_estimator": token_estimator,
            }
            site_index_entries.append(entry)

        # Wrap entries in a top-level object with build metadata
        index_content = json.dumps(site_index_entries, ensure_ascii=False, indent=2)
        site_index_obj = {
            "version_hash": self.sha256_text(index_content),
            "page_count": len(site_index_entries),
            "pages": site_index_entries,
        }
        if build_timestamp:
            site_index_obj["build_timestamp"] = build_timestamp

        index_path.write_text(
            json.dumps(site_index_obj, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with llms_path.open("w", encoding="utf-8") as fh:
            for line in jsonl_lines:
                fh.write(line + "\n")

        log.info(
            f"[ai_docs] site index written to {index_path} (pages={len(site_index_entries)})"
        )
        log.info(
            f"[ai_docs] llms full JSONL written to {llms_path} (sections={len(jsonl_lines)})"
        )
        return site_index_entries

    def build_category_light(
        self, enriched: list[dict], ai_root: Path, build_timestamp: str = ""
    ) -> None:
        """Generate per-category lightweight index files (<slug>-light.md)."""
        if not enriched:
            return
        content_cfg = self._llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info") or {}
        if not categories_info:
            log.info("[ai_docs] no categories configured; skipping light files")
            return

        categories_dir = ai_root / "categories"
        categories_dir.mkdir(parents=True, exist_ok=True)

        for category_id, cat_info in categories_info.items():
            cat_slug = self.slugify_category(category_id)
            display_name = cat_info.get("name", category_id)
            description = cat_info.get("description", "")

            cat_pages = sorted(
                self.select_pages_for_category(category_id, enriched),
                key=lambda p: (p.get("title") or "").lower(),
            )

            blocks: list[str] = []
            for page in cat_pages:
                lines: list[str] = []
                title = page.get("title") or page.get("id", "")
                lines.append(f"## {title}")
                md_url = page.get("raw_md_url", "")
                if md_url:
                    lines.append(md_url)
                preview = page.get("preview", "")
                if preview:
                    lines.append("")
                    lines.append(preview)
                outline = page.get("outline", [])
                if outline:
                    lines.append("")
                    lines.append("### Sections")
                    for heading in outline:
                        lines.append(f"- {heading['title']} `#{heading['anchor']}`")
                blocks.append("\n".join(lines))

            body = "\n\n---\n\n".join(blocks)
            fm_obj = {
                "category": display_name,
                "description": description,
                "page_count": len(cat_pages),
                "token_estimate": self.estimate_tokens(body),
            }
            if build_timestamp:
                fm_obj["updated"] = build_timestamp

            fm_yaml = yaml.safe_dump(
                fm_obj, sort_keys=False, allow_unicode=True, width=4096
            ).strip()
            content = f"---\n{fm_yaml}\n---\n\n{body}\n"

            out_path = categories_dir / f"{cat_slug}-light.md"
            out_path.write_text(content, encoding="utf-8")
            log.debug(f"[ai_docs] light file {out_path.name}: {len(cat_pages)} pages")

        log.info(f"[ai_docs] category light files written to {categories_dir}")

    def build_llms_txt(
        self, pages: list[dict], docs_dir: Path, build_timestamp: str = ""
    ) -> None:
        """Generate llms.txt listing resolved markdown links grouped by category."""
        if not pages:
            return
        project_cfg = self._llms_config.get("project", {})
        project_name = project_cfg.get("name", "Documentation")
        summary_line = project_cfg.get("project_url") or project_cfg.get(
            "docs_base_url", ""
        )

        content_cfg = self._llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info", {}) or {}

        docs_root = docs_dir.resolve()
        output_rel = self._llms_config.get("llms_txt_output_path", "llms.txt")
        out_path = Path(output_rel)
        if not out_path.is_absolute():
            out_path = (docs_root / out_path).resolve()
        else:
            out_path = out_path.resolve()

        try:
            out_path.relative_to(docs_root)
        except ValueError as exc:
            raise ValueError(
                f"Configured llms_txt_output_path '{output_rel}' must be within docs_dir '{docs_root}'"
            ) from exc
        out_path.parent.mkdir(parents=True, exist_ok=True)

        metadata_section = self.format_llms_metadata_section(pages, build_timestamp)
        docs_section = self.format_llms_docs_section(
            pages, list(categories_info.keys()), categories_info
        )
        summary_line = summary_line.strip()

        content_lines = [
            f"# {project_name}",
            f"\n> {summary_line}\n" if summary_line else "",
            "## How to Use This File",
            (
                "This file lists URLs for resolved Markdown pages that complement the rendered pages on the documentation site. "
                "Use these Markdown files when prompting models to retain semantic context without HTML noise."
            ),
            "",
            metadata_section,
            docs_section,
        ]

        llms_txt_content = "\n".join(line for line in content_lines if line is not None)
        out_path.write_text(llms_txt_content, encoding="utf-8")
        log.info(f"[ai_docs] llms.txt written to {out_path}")

    @staticmethod
    def format_llms_metadata_section(
        pages: list[dict], build_timestamp: str = ""
    ) -> str:
        distinct_categories = {
            cat for page in pages for cat in (page.get("categories") or [])
        }
        all_content = "".join(p.get("body", "") for p in pages)
        version_hash = AIDocsPlugin.sha256_text(all_content)
        lines = [
            "## Metadata",
            f"- Documentation pages: {len(pages)}",
            f"- Categories: {len(distinct_categories)}",
        ]
        if build_timestamp:
            lines.append(f"- Build Timestamp: {build_timestamp}")
        lines.append(f"- Version Hash: {version_hash}")
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def format_llms_docs_section(
        pages: list[dict],
        category_order: list[str],
        categories_info: dict | None = None,
    ) -> str:
        categories_info = categories_info or {}
        grouped: dict[str, list[str]] = {}
        for page in pages:
            resolved_url = page.get("url", "").rstrip("/") + ".md"
            title = page.get("title") or page["slug"]
            description = page.get("description") or ""
            cats = page.get("categories") or ["Uncategorized"]
            line = f"- [{title}]({resolved_url}): {description}"
            for cat in cats:
                grouped.setdefault(cat, []).append(line)

        lines = [
            "## Docs",
            "This section lists documentation pages by category. Each entry links to the resolved markdown version of the page and includes a short description.",
        ]
        seen = set()
        for cat_id in category_order:
            cat_info = categories_info.get(cat_id, {})
            display_name = cat_info.get("name", cat_id)

            entries = grouped.get(cat_id)
            if not entries:
                continue
            lines.append(f"\nDocs: {display_name}")
            lines.extend(entries)
            seen.add(cat_id)

        remaining = sorted(cat for cat in grouped if cat not in seen)
        for cat in remaining:
            lines.append(f"\nDocs: {cat}")
            lines.extend(grouped[cat])

        return "\n".join(lines)
