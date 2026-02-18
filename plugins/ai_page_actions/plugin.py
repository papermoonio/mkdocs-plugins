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
    table widget) to generate the split-button HTML, then wraps the
    H1 + widget in a flex container for layout.

    Runs in the ``on_post_page`` hook so it operates on fully rendered
    HTML *after* all content hooks (including ``page_toggle``) have
    finished.
    """

    def __init__(self):
        super().__init__()
        self._file_utils = AIFileUtils()

    # ------------------------------------------------------------------
    # Slug helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_slug(page_url: str) -> str:
        """Convert a page URL to the slug used by resolve_md.

        Mirrors ``resolve_md.compute_slug_and_url`` and the client-side
        ``buildSlugFromPath`` in copy-to-llm.js.
        """
        route = page_url.strip("/")
        if not route:
            return "index"
        return route.replace("/", "-")

    @staticmethod
    def _build_toggle_slug(page_url: str, data_filename: str) -> str:
        """Build a slug for a toggle-page variant.

        For the canonical variant (empty ``data_filename``), uses the
        base slug.  For non-canonical variants, drops the last path
        segment and appends the variant filename.
        """
        route = page_url.strip("/")
        if not data_filename:
            return route.replace("/", "-") if route else "index"
        segments = route.split("/")
        base = "-".join(segments[:-1]) if len(segments) > 1 else ""
        return f"{base}-{data_filename}" if base else data_filename

    # ------------------------------------------------------------------
    # H1 wrapping
    # ------------------------------------------------------------------

    def _wrap_h1(self, h1: Tag, slug: str, soup: BeautifulSoup) -> None:
        """Wrap an H1 element and the AI actions widget in a flex container."""
        url = f"/ai/pages/{slug}.md"
        filename = f"{slug}.md"

        widget_html = self._file_utils.generate_dropdown_html(
            url=url, filename=filename, primary_label="Copy page"
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
        # Skip excluded pages
        src = page.file.src_path
        if src == "404.html" or src.endswith("ai-resources.md"):
            return output
        if page.meta.get("hide_ai_actions"):
            return output

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
                    slug = self._build_toggle_slug(page.url, data_filename)
                    self._wrap_h1(h1, slug, soup)
                    modified = True

        # --- Normal pages (no toggle) ---
        if not toggle_containers:
            h1 = md_content.find("h1")
            if h1:
                slug = self._build_slug(page.url)
                self._wrap_h1(h1, slug, soup)
                modified = True

        if not modified:
            return output

        return str(soup)
