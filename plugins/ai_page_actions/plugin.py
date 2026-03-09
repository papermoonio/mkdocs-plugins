import json
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup, Tag
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page
from mkdocs.utils import log

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils


class AiPageActionsPlugin(BasePlugin):
    """MkDocs plugin that injects the AI actions widget next to each
    page's H1 heading at build time.

    Uses :class:`AIFileUtils` (the same shared library behind the
    table widget) for slug resolution, URL building, and HTML
    generation.  This plugin only handles *where* to inject — all
    the *what* lives in the shared utility.

    Page exclusions are driven by ``llms_config.json`` (the same
    ``skip_basenames`` and ``skip_paths`` that ``resolve_md`` uses)
    so the widget is never rendered for pages that have no AI
    artifact files.  Dot-directories are always excluded.

    Runs in the ``on_post_page`` hook so it operates on fully rendered
    HTML *after* all content hooks (including ``page_toggle``) have
    finished.
    """

    def __init__(self):
        super().__init__()
        self._file_utils = AIFileUtils()
        self._skip_basenames: List[str] = []
        self._skip_paths: List[str] = []
        self._config_loaded = False

    # ------------------------------------------------------------------
    # Config
    # ------------------------------------------------------------------

    def _ensure_config_loaded(self, config: MkDocsConfig) -> None:
        """Load exclusion rules from llms_config.json (once per build)."""
        if self._config_loaded:
            return
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        llms_config = self._load_llms_config(project_root)

        exclusions = llms_config.get("content", {}).get("exclusions", {})
        self._skip_basenames = exclusions.get("skip_basenames", [])
        self._skip_paths = exclusions.get("skip_paths", [])
        self._config_loaded = True

    @staticmethod
    def _load_llms_config(project_root: Path) -> dict:
        """Load llms_config.json from the project root."""
        config_path = project_root / "llms_config.json"
        if not config_path.exists():
            log.warning(f"[ai_page_actions] llms_config.json not found at {config_path}")
            return {}
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            log.warning(f"[ai_page_actions] Failed to load llms_config.json: {e}")
            return {}

    # ------------------------------------------------------------------
    # H1 wrapping
    # ------------------------------------------------------------------

    def _wrap_h1(self, h1: Tag, slug: str, soup: BeautifulSoup, site_url: str = "") -> None:
        """Wrap an H1 element and the AI actions widget in a flex container."""
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""
        url = f"{base_path}/ai/pages/{slug}.md"
        filename = f"{slug}.md"

        widget_html = self._file_utils.generate_dropdown_html(
            url=url,
            filename=filename,
            primary_label="Copy page",
            site_url=site_url,
            label_replace={"file": "page"},
        )

        wrapper = soup.new_tag("div")
        wrapper["class"] = "h1-ai-actions-wrapper"

        h1.wrap(wrapper)
        widget = BeautifulSoup(widget_html, "html.parser")
        wrapper.append(widget)

    # ------------------------------------------------------------------
    # Hook
    # ------------------------------------------------------------------

    def on_post_page(
        self, output: str, *, page: Page, config: MkDocsConfig
    ) -> Optional[str]:
        # Load exclusion config on first page (same hook where config is reliable)
        self._ensure_config_loaded(config)

        # Always skip the homepage (root index.md)
        if page.is_homepage:
            return output

        # Skip excluded pages (driven by llms_config.json + dot-dirs + front matter)
        if self._file_utils.is_page_excluded(
            page.file.src_path,
            page.meta,
            skip_basenames=self._skip_basenames,
            skip_paths=self._skip_paths,
        ):
            return output

        site_url = config.get("site_url", "")

        soup = BeautifulSoup(output, "html.parser")
        md_content = soup.select_one(".md-content")
        if not md_content:
            return output

        modified = False

        # --- Toggle pages ---
        toggle_containers = md_content.select(".toggle-container")
        if toggle_containers:
            for container in toggle_containers:
                header_spans = container.select(
                    ".toggle-header > span[data-variant]"
                )
                for span in header_spans:
                    h1 = span.find("h1")
                    if not h1:
                        continue
                    variant = span.get("data-variant", "")
                    btn = container.select_one(
                        f'.toggle-btn[data-variant="{variant}"]'
                    )
                    data_filename = btn.get("data-filename", "") if btn else ""
                    slug = AIFileUtils.build_toggle_slug(page.url, data_filename)
                    self._wrap_h1(h1, slug, soup, site_url=site_url)
                    modified = True

        # --- Normal pages (no toggle) ---
        if not toggle_containers:
            h1 = md_content.find("h1")
            if h1:
                slug = AIFileUtils.build_slug(page.url)
                self._wrap_h1(h1, slug, soup, site_url=site_url)
                modified = True

        if not modified:
            return output

        return str(soup)
