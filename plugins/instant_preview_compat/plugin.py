from __future__ import annotations

from pathlib import Path

from mkdocs.config.config_options import Type
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page

from helper_lib.instant_preview_compat import (
    PreviewPageState,
    list_html_files,
    process_page_html,
    rewrite_html_links,
)


class InstantPreviewCompatPlugin(BasePlugin):
    """Post-process built HTML so Material instant preview starts at useful content."""

    def __init__(self) -> None:
        super().__init__()
        self._states: dict[str, PreviewPageState] = {}

    config_scheme = (
        ("exclude_selectors", Type(list, default=[])),
        ("rewrite_internal_links", Type(bool, default=True)),
    )

    def on_pre_build(self, *, config: MkDocsConfig) -> None:
        self._states.clear()

    def on_post_page(
        self,
        output: str,
        *,
        page: Page,
        config: MkDocsConfig,
    ) -> str:
        output_path = self._resolve_output_path(page, config)
        processed_html, state = process_page_html(
            output,
            output_path=output_path,
            exclude_selectors=list(self.config.get("exclude_selectors", [])),
        )
        if state.has_rewrites:
            self._states[output_path] = state
        else:
            self._states.pop(output_path, None)
        return processed_html

    def on_post_build(self, config: MkDocsConfig) -> None:
        if not self.config.get("rewrite_internal_links", True):
            return

        if not self._states:
            return

        site_dir = Path(config["site_dir"]).resolve()
        html_files = list_html_files(site_dir)

        for html_path in html_files:
            output_path = html_path.relative_to(site_dir).as_posix()
            original_html = html_path.read_text(encoding="utf-8")
            rewritten_html = rewrite_html_links(
                original_html,
                source_path=output_path,
                states=self._states,
            )
            if rewritten_html != original_html:
                html_path.write_text(rewritten_html, encoding="utf-8")

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
