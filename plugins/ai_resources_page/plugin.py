import json
import logging
import re
from pathlib import Path
from mkdocs.plugins import BasePlugin

log = logging.getLogger("mkdocs.plugins.ai_resources_page")


class AiResourcesPagePlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self.llms_config = {}

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
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "category"

    def generate_actions_html(self, url: str, filename: str) -> str:
        """
        Generates the HTML for the actions column (View, Copy, Download) using pure HTML anchor tags.
        This standardizes on the class names and data attributes used by the client-side JS
        and avoids issues with Markdown parsing inside HTML blocks.
        """
        # View Button (Eye icon)
        view_btn = (
            f'<a href="#" class="llms-view" data-path="{url}" title="View" style="margin-right: 8px; text-decoration: none;">'
            f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M8 2C4.14 2 1 5.14 1 8s3.14 6 7 6 7-3.14 7-6-3.14-6-7-6m0 10.5c-2.48 0-4.5-2.02-4.5-4.5S5.52 3.5 8 3.5s4.5 2.02 4.5 4.5-2.02 4.5-4.5 4.5m0-7c-1.38 0-2.5 1.12-2.5 2.5s1.12 2.5 2.5 2.5 2.5-1.12 2.5-2.5-1.12-2.5-2.5-2.5"/></svg></span>'
            f'</a>'
        )

        # Copy Button (Copy icon)
        copy_btn = (
            f'<a href="#" class="llms-copy" data-path="{url}" title="Copy" style="margin-right: 8px; text-decoration: none;">'
            f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path fill="currentColor" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg></span>'
            f'</a>'
        )
        
        # Download Button (Download icon)
        dl_btn = (
            f'<a href="#" class="llms-dl" data-path="{url}" data-filename="{filename}" title="Download" style="text-decoration: none;">'
            f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M2.75 14A1.75 1.75 0 0 1 1 12.25v-2.5a.75.75 0 0 1 1.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 14Z"/><path fill="currentColor" d="M7.25 7.689V1a.75.75 0 0 1 1.5 0v6.689l2.22-2.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734l-3.5 3.5a.75.75 0 0 1-1.06 0l-3.5-3.5a.75.75 0 0 1 1.06-1.06Z"/></svg></span>'
            f'</a>'
        )

        return f'<div class="actions" style="display: flex; align-items: center;"> {view_btn} {copy_btn} {dl_btn} </div>'

    def generate_global_actions_html(self, url: str, filename: str, view=True) -> str:
        """
        Generates actions for global files which might differ (e.g. no View for JSONL).
        """
        btns = []
        if view:
            btns.append(
                f'<a href="#" class="llms-view" data-path="{url}" title="View" style="margin-right: 8px; text-decoration: none;">'
                f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M8 2C4.14 2 1 5.14 1 8s3.14 6 7 6 7-3.14 7-6-3.14-6-7-6m0 10.5c-2.48 0-4.5-2.02-4.5-4.5S5.52 3.5 8 3.5s4.5 2.02 4.5 4.5-2.02 4.5-4.5 4.5m0-7c-1.38 0-2.5 1.12-2.5 2.5s1.12 2.5 2.5 2.5 2.5-1.12 2.5-2.5-1.12-2.5-2.5-2.5"/></svg></span>'
                f'</a>'
            )
        
        btns.append(
            f'<a href="#" class="llms-copy" data-path="{url}" title="Copy" style="margin-right: 8px; text-decoration: none;">'
            f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"/><path fill="currentColor" d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"/></svg></span>'
            f'</a>'
        )
        
        btns.append(
            f'<a href="#" class="llms-dl" data-path="{url}" data-filename="{filename}" title="Download" style="text-decoration: none;">'
            f'<span class="twemoji"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16"><path fill="currentColor" d="M2.75 14A1.75 1.75 0 0 1 1 12.25v-2.5a.75.75 0 0 1 1.5 0v2.5c0 .138.112.25.25.25h10.5a.25.25 0 0 0 .25-.25v-2.5a.75.75 0 0 1 1.5 0v2.5A1.75 1.75 0 0 1 13.25 14Z"/><path fill="currentColor" d="M7.25 7.689V1a.75.75 0 0 1 1.5 0v6.689l2.22-2.22a.749.749 0 0 1 1.275.326.749.749 0 0 1-.215.734l-3.5 3.5a.75.75 0 0 1-1.06 0l-3.5-3.5a.75.75 0 0 1 1.06-1.06Z"/></svg></span>'
            f'</a>'
        )

        return f'<div class="actions" style="display: flex; align-items: center;"> {" ".join(btns)} </div>'

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
        categories = content_cfg.get("categories_order", [])
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

{project_name} provides files to make documentation content available in a structure optimized for use with large language models (LLMs) and AI tools. These resources help build AI assistants, power code search, or enable custom tooling trained on {project_name}’s documentation.

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
        actions_llms = self.generate_global_actions_html(
            "/llms.txt", "llms.txt", view=True
        )
        row_llms = f'| Index | Markdown URL index for documentation pages, links to essential repos, and additional resources in the llms.txt standard format. | <code style="white-space: nowrap;">llms.txt</code> | {actions_llms} |'
        output.append(row_llms)

        # 2. site-index.json
        actions_site_index = self.generate_global_actions_html(
            f"{public_root_stripped}/site-index.json", "site-index.json", view=True
        )
        row_site_index = f'| Site index (JSON) | Lightweight site index of JSON objects (one per page) with metadata and content previews. | <code style="white-space: nowrap;">site-index.json</code> | {actions_site_index} |'
        output.append(row_site_index)

        # 3. llms-full.jsonl
        # Typically no "View" for large JSONL
        actions_full = self.generate_global_actions_html(
            # Sanitize for markdown table
            cat = self.sanitize_table_content(cat)
            description = self.sanitize_table_content(description)

            f"{public_root_stripped}/llms-full.jsonl", "llms-full.jsonl", view=False
        )
        row_full = f'| Full site contents (JSONL) | Full content of documentation site enhanced with metadata. | <code style="white-space: nowrap;">llms-full.jsonl</code> | {actions_full} |'
        output.append(row_full)

        # 4. Categories
        for cat in categories:
            slug = self.slugify_category(cat)

            # Use dictionary lookup for description
            cat_info = categories_info.get(cat, {})
            description = cat_info.get("description", f"Resources for {cat}.")

            filename = f"{slug}.md"
            url = f"{public_root_stripped}/categories/{filename}"

            actions = self.generate_actions_html(url, filename)

            row = f'| {cat} | {description} | <code style="white-space: nowrap;">{filename}</code> | {actions} |'
            output.append(row)

        # Add Note
        note = """
!!! note
    The `llms-full.jsonl` file may exceed the input limits of some language models due to its size. If you encounter limitations, consider using the smaller `site-index.json` or category bundle files instead.
"""
        output.append(note)

        return "\n".join(output)
