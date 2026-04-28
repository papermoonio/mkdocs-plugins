from __future__ import annotations

from pathlib import Path

from mkdocs.config.config_options import Type
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin, event_priority

from helper_lib.instant_preview import list_html_files, process_page_html


class InstantPreviewPlugin(BasePlugin):
    config_scheme = (
        ("exclude_selectors", Type(list, default=[])),
        ("link_scope_selectors", Type(list, default=["article"])),
        ("debug", Type(bool, default=False)),
    )

    @event_priority(-100)
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
                link_scope_selectors=list(
                    self.config.get("link_scope_selectors", ["article"])
                ),
            )
            if processed_html != original_html:
                html_path.write_text(processed_html, encoding="utf-8")
