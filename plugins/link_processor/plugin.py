from urllib.parse import urlparse, urlunparse

from bs4 import BeautifulSoup
from mkdocs.config import config_options
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page


class LinkProcessorPlugin(BasePlugin):
    config_scheme = (
        ("skip_internal_path_prefixes", config_options.Type(list, default=[])),
    )

    def on_page_content(
        self, html: str, page: Page, config: MkDocsConfig, files: Files
    ) -> str:
        soup = BeautifulSoup(html, "html.parser")

        for a in soup.find_all("a", href=True):
            href = a["href"]

            if href.startswith(("http://", "https://")):
                self._process_external(a)
            elif not href.startswith("#") and not href.startswith("mailto:"):
                self._process_internal(a, href)

        return str(soup)

    def _process_external(self, a) -> None:
        a["target"] = "_blank"
        existing = a.get("rel") or []
        rel_set = set(existing)
        rel_set.update(["noopener", "noreferrer"])
        a["rel"] = sorted(rel_set)

    def _process_internal(self, a, href: str) -> None:
        skip_prefixes = self.config.get("skip_internal_path_prefixes", [])
        parsed = urlparse(href)
        path = parsed.path

        if not path:
            return

        if any(path.startswith(prefix) for prefix in skip_prefixes):
            return

        if path.endswith("/"):
            return

        last_segment = path.split("/")[-1]
        if "." in last_segment:
            return

        a["href"] = urlunparse(parsed._replace(path=path + "/"))
