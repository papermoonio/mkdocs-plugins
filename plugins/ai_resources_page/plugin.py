import json
import re
from pathlib import Path
from urllib.parse import urlparse

from mkdocs.plugins import BasePlugin
from mkdocs.utils import log

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils


class AiResourcesPagePlugin(BasePlugin):
    # Placeholder prefix used in on_page_markdown, replaced in on_post_build
    _TOKEN_PLACEHOLDER_PREFIX = "<!-- token-estimate:"
    _TOKEN_PLACEHOLDER_SUFFIX = " -->"

    def __init__(self):
        super().__init__()
        self.llms_config = {}
        self._file_utils = AIFileUtils()

    def load_token_counts(self, project_root: Path) -> dict:
        """Load token estimates from ai-resources-token-count.json."""
        token_path = project_root / "ai-resources-token-count.json"
        if not token_path.exists():
            log.debug(
                f"[ai_resources_page] Token counts not found at {token_path}"
            )
            return {}
        try:
            with open(token_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                log.warning(
                    "[ai_resources_page] Token counts file is not a JSON object; ignoring"
                )
                return {}
            return {k: v for k, v in data.items() if isinstance(v, int)}
        except Exception as e:
            log.warning(f"[ai_resources_page] Failed to load token counts: {e}")
            return {}

    @staticmethod
    def format_token_count(count: int) -> str:
        """Format a token count into a human-readable abbreviated string."""
        if count >= 1_000_000:
            value = count / 1_000_000
            return f"~{value:.1f}M tokens" if value % 1 else f"~{int(value)}M tokens"
        if count >= 1_000:
            value = count / 1_000
            return f"~{value:.1f}K tokens" if value % 1 else f"~{int(value)}K tokens"
        return f"~{count} tokens"

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

    def _build_file_cell(self, filename: str, file_key: str) -> str:
        """Build the File column cell with filename and a token estimate placeholder.

        The placeholder is an HTML comment that survives Markdown-to-HTML conversion.
        It gets replaced with real values in on_post_build once resolve_md has
        written the token manifest.
        """
        code = f'<code style="white-space: nowrap;">{filename}</code>'
        placeholder = (
            f"{self._TOKEN_PLACEHOLDER_PREFIX}{file_key}{self._TOKEN_PLACEHOLDER_SUFFIX}"
        )
        return f"{code}{placeholder}"

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

        # Get the site URL for fully-qualified prompt URLs
        site_url = config.get("site_url", "")

        # Extract base path for sites deployed under a subpath (e.g., /docs/)
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""

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
- **Token estimates**: Each file includes an approximate token count based on Unicode word-and-punctuation tokenization. These estimates trend slightly higher than BPE-based tokenizer counts (e.g., `tiktoken`). For precise budgeting, run the file through your model's tokenizer.

These AI-ready files do not include any persona or system prompts. They are purely informational and can be used without conflicting with your existing agent or tool prompting.

## Access LLM Files

| Category | Description | File | Actions |
|:---|:---|:---|:---|"""
        output.append(overview)

        # 1. llms.txt (Root File)
        # Note: llms.txt usually lives at root, so path is "/llms.txt"
        actions_llms = self._file_utils.generate_dropdown_html(
            url=f"{base_path}/llms.txt", filename="llms.txt", site_url=site_url
        )
        file_cell_llms = self._build_file_cell("llms.txt", "llms.txt")
        row_llms = f'| Index | Markdown URL index for documentation pages, links to essential repos, and additional resources in the llms.txt standard format. | {file_cell_llms} | {actions_llms} |'
        output.append(row_llms)

        # 2. site-index.json
        actions_site_index = self._file_utils.generate_dropdown_html(
            url=f"{base_path}{public_root_stripped}/site-index.json",
            filename="site-index.json",
            site_url=site_url,
        )
        file_cell_si = self._build_file_cell("site-index.json", "site-index.json")
        row_site_index = f'| Site index (JSON) | Lightweight site index of JSON objects (one per page) with metadata and content previews. | {file_cell_si} | {actions_site_index} |'
        output.append(row_site_index)

        # 3. llms-full.jsonl
        # Typically no "View" for large JSONL
        actions_full = self._file_utils.generate_dropdown_html(
            url=f"{base_path}{public_root_stripped}/llms-full.jsonl",
            filename="llms-full.jsonl",
            exclude=["view-markdown"],
            site_url=site_url,
        )
        file_cell_full = self._build_file_cell("llms-full.jsonl", "llms-full.jsonl")
        row_full = f'| Full site contents (JSONL) | Full content of documentation site enhanced with metadata. | {file_cell_full} | {actions_full} |'
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
            url = f"{base_path}{public_root_stripped}/categories/{filename}"

            actions = self._file_utils.generate_dropdown_html(
                url=url, filename=filename, site_url=site_url
            )

            file_cell = self._build_file_cell(filename, f"categories/{filename}")
            row = f'| {display_name} | {description} | {file_cell} | {actions} |'
            output.append(row)

        # Add Note
        note = """
!!! note
    The `llms-full.jsonl` file may exceed the input limits of some language models due to its size. If you encounter limitations, consider using the smaller `site-index.json` or category bundle files instead.
"""
        output.append(note)

        return "\n".join(output)

    def on_post_build(self, config):
        """Replace token estimate placeholders with real values.

        This runs after resolve_md's on_post_build has written the token
        manifest, so the data is guaranteed to be fresh.
        """
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        token_counts = self.load_token_counts(project_root)
        if not token_counts:
            log.debug(
                "[ai_resources_page] No token counts available; "
                "placeholders will be removed"
            )

        site_dir = Path(config["site_dir"]).resolve()
        # Find the built ai-resources page HTML
        ai_resources_html = site_dir / "ai-resources" / "index.html"
        if not ai_resources_html.exists():
            log.debug(
                f"[ai_resources_page] Built page not found at {ai_resources_html}"
            )
            return

        html = ai_resources_html.read_text(encoding="utf-8")
        original_html = html

        # Replace each placeholder with a styled token count span (or remove it)
        for file_key, count in token_counts.items():
            placeholder = (
                f"{self._TOKEN_PLACEHOLDER_PREFIX}{file_key}"
                f"{self._TOKEN_PLACEHOLDER_SUFFIX}"
            )
            label = self.format_token_count(count)
            replacement = (
                f'<br><span style="font-size: 0.8em; opacity: 0.7;">'
                f"{label}</span>"
            )
            html = html.replace(placeholder, replacement)

        # Remove any remaining placeholders that had no matching token count
        html = re.sub(
            r"<!-- token-estimate:[^>]+-->",
            "",
            html,
        )

        if html != original_html:
            ai_resources_html.write_text(html, encoding="utf-8")
            log.info(
                "[ai_resources_page] Injected token estimates into ai-resources page"
            )
