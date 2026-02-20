from typing import Optional

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

    Runs in the ``on_post_page`` hook so it operates on fully rendered
    HTML *after* all content hooks (including ``page_toggle``) have
    finished.
    """

    def __init__(self):
        super().__init__()
        self._file_utils = AIFileUtils()

    # ------------------------------------------------------------------
    # H1 wrapping
    # ------------------------------------------------------------------

    def _wrap_h1(self, h1: Tag, slug: str, soup: BeautifulSoup, site_url: str = "") -> None:
        """Wrap an H1 element and the AI actions widget in a flex container."""
        url = AIFileUtils.build_ai_page_url(slug)
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
        # Skip excluded pages (configured in ai_file_actions.json)
        if self._file_utils.is_page_excluded(page.file.src_path, page.meta):
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
