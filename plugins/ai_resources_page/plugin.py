import json
import re
from pathlib import Path

from mkdocs.plugins import BasePlugin
from mkdocs.utils import log

from lib.ai_file_utils.ai_file_utils import AIFileUtils


class AiResourcesPagePlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.llms_config = {}
        self._file_utils = AIFileUtils()

    def load_llms_config(self, project_root: Path) -> dict:
        config_path = project_root / "llms_config.json"
        if not config_path.exists():
            log.warning(f"[ai_resources_page] Config file not found at {config_path}")
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[ai_resources_page] Failed to load config: {e}")
            return {}

    def slugify_category(self, name: str) -> str:
        s = name.strip().lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"[\s_]+", "-", s)  # Replace spaces AND underscores with hyphens
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "category"

    def sanitize_table_content(self, text: str) -> str:
        """
        Escapes characters that would break the Markdown table layout.
        Mainly pipes `|` and newlines.
        """
        if not text:
            return ""
        # Replace pipe with escaped pipe or HTML entity
        text = text.replace("|", "&#124;")
        # Replace newlines with space to keep it in one cell
        text = text.replace("\n", " ").replace("\r", "")
        return text

    def on_page_markdown(self, markdown, page, config, files):
        # Target only the AI Resources page
        if not page.file.src_path.endswith("ai-resources.md"):
            return markdown

        log.info(f"[ai_resources_page] Generating content for {page.file.src_path}")

        # Load configuration
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        self.llms_config = self.load_llms_config(project_root)

        content_cfg = self.llms_config.get("content", {})
        categories_info = content_cfg.get("categories_info", {})

        # Determine public root (e.g. "/ai/")
        outputs_cfg = self.llms_config.get("outputs", {})
        public_root = outputs_cfg.get("public_root", "/ai/")
        # Ensure it has leading/trailing slashes for path construction if we want consistency
        # But we'll strip trailing to perform clean joins
        public_root_stripped = public_root.rstrip("/")

        # Get project name
        project_cfg = self.llms_config.get("project", {})
        project_name = project_cfg.get("name")
        if not project_name:
            raise KeyError(
                "[ai_resources_page] 'project.name' is missing in llms_config.json"
            )

        # Construct the page content
        output = []

        # Overview Text
        overview = f"""# AI Resources

{project_name} provides files to make documentation content available in a structure optimized for use with large language models (LLMs) and AI tools. These resources help build AI assistants, power code search, or enable custom tooling trained on {project_name}'s documentation.

## How to Use These Files

- **Quick navigation**: Use `llms.txt` to give models a high-level map of the site.
- **Lightweight context**: Use `site-index.json` for smaller context windows or when you only need targeted retrieval.
- **Full content**: Use `llms-full.jsonl` for large-context models or preparing data for RAG pipelines.
- **Focused bundles**: Use category files (e.g., `basics.md`, `reference.md`) to limit content to a specific theme or task for more focused responses.

These AI-ready files do not include any persona or system prompts. They are purely informational and can be used without conflicting with your existing agent or tool prompting.

## Access LLM Files

| Category | Description | File | Actions |
|:---|:---|:---|:---|"""
        output.append(overview)

        # 1. llms.txt (Root File)
        # Note: llms.txt usually lives at root, so path is "/llms.txt"
        actions_llms = self._file_utils.generate_dropdown_html(
            url="/llms.txt", filename="llms.txt"
        )
        row_llms = f'| Index | Markdown URL index for documentation pages, links to essential repos, and additional resources in the llms.txt standard format. | <code style="white-space: nowrap;">llms.txt</code> | {actions_llms} |'
        output.append(row_llms)

        # 2. site-index.json
        actions_site_index = self._file_utils.generate_dropdown_html(
            url=f"{public_root_stripped}/site-index.json",
            filename="site-index.json",
        )
        row_site_index = f'| Site index (JSON) | Lightweight site index of JSON objects (one per page) with metadata and content previews. | <code style="white-space: nowrap;">site-index.json</code> | {actions_site_index} |'
        output.append(row_site_index)

        # 3. llms-full.jsonl
        # Typically no "View" for large JSONL
        actions_full = self._file_utils.generate_dropdown_html(
            url=f"{public_root_stripped}/llms-full.jsonl",
            filename="llms-full.jsonl",
            exclude=["view-markdown"],
        )
        row_full = f'| Full site contents (JSONL) | Full content of documentation site enhanced with metadata. | <code style="white-space: nowrap;">llms-full.jsonl</code> | {actions_full} |'
        output.append(row_full)

        # 4. Categories (key order in categories_info controls display order)
        for cat_id, cat_info in categories_info.items():
            slug = self.slugify_category(cat_id)

            display_name = cat_info.get("name", cat_id)
            description = cat_info.get("description", f"Resources for {display_name}.")

            # Sanitize for markdown table
            display_name = self.sanitize_table_content(display_name)
            description = self.sanitize_table_content(description)

            filename = f"{slug}.md"
            url = f"{public_root_stripped}/categories/{filename}"

            actions = self._file_utils.generate_dropdown_html(
                url=url, filename=filename
            )

            row = f'| {display_name} | {description} | <code style="white-space: nowrap;">{filename}</code> | {actions} |'
            output.append(row)

        # Add Note
        note = """
!!! note
    The `llms-full.jsonl` file may exceed the input limits of some language models due to its size. If you encounter limitations, consider using the smaller `site-index.json` or category bundle files instead.
"""
        output.append(note)

        return "\n".join(output)
