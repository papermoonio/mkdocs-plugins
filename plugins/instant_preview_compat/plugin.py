from __future__ import annotations

from pathlib import Path

from mkdocs.config.config_options import Type
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from helper_lib.instant_preview_compat import list_html_files, process_page_html


class InstantPreviewCompatPlugin(BasePlugin):
    """Patch built HTML so Material instant previews start at useful content."""

    config_scheme = (
        ("exclude_selectors", Type(list, default=[])),
        ("rewrite_internal_links", Type(bool, default=True)),
    )

    def on_post_page(
        self,
        output: str,
        *,
        page: Page,
        config: MkDocsConfig,
    ) -> str:
        output_path = self._resolve_output_path(page, config)
        return process_page_html(
            output,
            output_path=output_path,
            exclude_selectors=list(self.config.get("exclude_selectors", [])),
        )

    def on_post_build(self, config: MkDocsConfig) -> None:
        site_dir = Path(config["site_dir"]).resolve()
        html_files = list_html_files(site_dir)

        for html_path in html_files:
            output_path = html_path.relative_to(site_dir).as_posix()
            original_html = html_path.read_text(encoding="utf-8")
            processed_html = process_page_html(
                original_html,
                output_path=output_path,
                exclude_selectors=list(self.config.get("exclude_selectors", [])),
            )
            if processed_html != original_html:
                html_path.write_text(processed_html, encoding="utf-8")

    @staticmethod
    def _resolve_output_path(page: Page, config: MkDocsConfig) -> str:
        site_dir = Path(config["site_dir"]).resolve()
        abs_dest_path = getattr(page.file, "abs_dest_path", "")
        if abs_dest_path:
            try:
                return Path(abs_dest_path).resolve().relative_to(site_dir).as_posix()
            except ValueError:
                pass

        route = page.url.strip("/")
        if not route:
            return "index.html"
        if route.endswith(".html"):
            return route
        return f"{route}/index.html"
