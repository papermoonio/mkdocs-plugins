from pathlib import Path
from unittest.mock import MagicMock

from bs4 import BeautifulSoup, Tag

from plugins.ai_page_actions.plugin import AiPageActionsPlugin
from plugins.instant_preview_compat.plugin import InstantPreviewCompatPlugin
from plugins.page_toggle.plugin import TogglePagesPlugin


def _make_page(
    *,
    url: str,
    src_path: str,
    abs_dest_path: str | None = None,
    meta: dict | None = None,
):
    page = MagicMock()
    page.url = url
    page.file.src_path = src_path
    page.file.abs_dest_path = abs_dest_path or "/tmp/unused.html"
    page.is_homepage = False
    page.meta = meta or {}
    page.toc = []
    return page


def _wrap_document(content: str) -> str:
    return (
        "<html><body>"
        '<div class="md-content">'
        "<article>"
        f"{content}"
        "</article>"
        "</div>"
        "</body></html>"
    )


def _extract_preview_fragment(html: str, anchor: str | None = None) -> str:
    soup = BeautifulSoup(html, "html.parser")
    selector = f'article [id="{anchor}"]' if anchor else "article h1"
    target = soup.select_one(selector)
    if target is None:
        return ""

    parts = [f"<h3>{target.decode_contents()}</h3>"]
    sibling = target.next_sibling
    while sibling is not None:
        current = sibling
        sibling = sibling.next_sibling
        if not isinstance(current, Tag):
            continue
        if current.name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            break
        parts.append(str(current))
    return "".join(parts)


def _root_target_id(html: str) -> str | None:
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one("article [data-instant-preview-root-target]")
    return node.get("id") if node is not None else None


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestInstantPreviewCompat:
    def setup_method(self):
        self.plugin = InstantPreviewCompatPlugin()
        self.plugin.config = {
            "exclude_selectors": [],
            "rewrite_internal_links": True,
        }

    def _process_page_output(
        self,
        tmp_path: Path,
        *,
        output: str,
        output_path: Path,
        url: str,
        src_path: str,
        meta: dict | None = None,
    ) -> str:
        page = _make_page(
            url=url,
            src_path=src_path,
            abs_dest_path=str(output_path),
            meta=meta,
        )
        processed = self.plugin.on_post_page(
            output,
            page=page,
            config={"site_dir": str(tmp_path)},
        )
        output_path.write_text(processed, encoding="utf-8")
        return processed

    def test_keeps_plain_and_h1_links_clean_for_ai_action_pages(self, tmp_path):
        guide_dir = tmp_path / "guide"
        links_dir = tmp_path / "links"
        guide_dir.mkdir()
        links_dir.mkdir()

        guide_path = guide_dir / "index.html"
        links_path = links_dir / "index.html"

        actions = AiPageActionsPlugin()
        actions._config_loaded = True
        guide_page = _make_page(url="guide/", src_path="guide.md")
        guide_html = actions.on_post_page(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                "<p>Useful intro.</p>"
                '<h2 id="details">Details</h2>'
                "<p>Deep details.</p>"
            ),
            page=guide_page,
            config={"site_url": "https://example.com/"},
        )
        processed_guide = self._process_page_output(
            tmp_path,
            output=guide_html,
            output_path=guide_path,
            url="guide/",
            src_path="guide.md",
        )

        links_path.write_text(
            _wrap_document(
                '<p><a id="plain" href="../guide/">Guide</a></p>'
                '<p><a id="title" href="../guide/#guide">Guide title</a></p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        links_html = _read(links_path)
        assert 'href="../guide/"' in links_html
        assert 'href="../guide/#guide"' in links_html
        assert "__instant-preview__" not in links_html

        guide_html = _read(guide_path)
        root_target_id = _root_target_id(guide_html)
        assert root_target_id is not None
        assert guide_html.index("data-instant-preview-stash") < guide_html.index('id="guide"')

        root_fragment = _extract_preview_fragment(guide_html)
        h1_fragment = _extract_preview_fragment(guide_html, "guide")
        assert "Guide" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Details" in root_fragment
        assert "Deep details." in root_fragment
        assert "ai-file-actions-container" not in root_fragment
        assert "Guide" in h1_fragment
        assert root_fragment != h1_fragment
        assert _root_target_id(processed_guide) == root_target_id

    def test_builds_clean_root_preview_for_wrapped_h1(self, tmp_path):
        guide_dir = tmp_path / "guide"
        links_dir = tmp_path / "links"
        guide_dir.mkdir()
        links_dir.mkdir()

        guide_path = guide_dir / "index.html"
        links_path = links_dir / "index.html"

        self.plugin.config["exclude_selectors"] = [".hero-actions"]
        self._process_page_output(
            tmp_path,
            output=_wrap_document(
                '<div class="hero-shell">'
                '<h1 id="overview">Overview</h1>'
                '<div class="hero-actions">Buttons</div>'
                "</div>"
                '<div class="badge">Beginner</div>'
                '<div class="repo-status">Passing</div>'
                '<h2 id="intro">Introduction</h2>'
                "<p>Actual intro.</p>"
                '<h2 id="more">More</h2>'
                "<p>More text.</p>"
            ),
            output_path=guide_path,
            url="guide/",
            src_path="guide.md",
        )

        links_path.write_text(
            _wrap_document('<p><a id="plain" href="../guide/">Guide</a></p>'),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        links_html = _read(links_path)
        assert 'href="../guide/"' in links_html
        assert "__instant-preview__" not in links_html

        guide_html = _read(guide_path)
        fragment = _extract_preview_fragment(guide_html)
        assert "Overview" in fragment
        assert "Beginner" in fragment
        assert "Passing" in fragment
        assert "Introduction" in fragment
        assert "Actual intro." in fragment
        assert "Buttons" not in fragment

    def test_hoists_excluded_blocks_for_h2_and_h3_previews(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"

        self.plugin.config["exclude_selectors"] = [".status-badge"]
        processed_html = self._process_page_output(
            tmp_path,
            output=_wrap_document(
                '<h1 id="guide">Guide</h1>'
                "<p>Intro.</p>"
                '<h2 id="details">Details</h2>'
                '<div class="status-badge">Beta</div>'
                "<p>Useful details.</p>"
                '<h3 id="subdetails">Subdetails</h3>'
                '<div class="status-badge">Alpha</div>'
                "<p>Useful subdetails.</p>"
            ),
            output_path=guide_path,
            url="guide/",
            src_path="guide.md",
        )

        details_fragment = _extract_preview_fragment(processed_html, "details")
        subdetails_fragment = _extract_preview_fragment(processed_html, "subdetails")

        assert "Useful details." in details_fragment
        assert "Beta" not in details_fragment
        assert "Useful subdetails." in subdetails_fragment
        assert "Alpha" not in subdetails_fragment

        soup = BeautifulSoup(processed_html, "html.parser")
        details_heading = soup.select_one("#details")
        subdetails_heading = soup.select_one("#subdetails")
        assert details_heading is not None
        assert subdetails_heading is not None
        assert details_heading.find_previous_sibling("div", class_="status-badge") is not None
        assert (
            subdetails_heading.find_previous_sibling("div", class_="status-badge")
            is not None
        )

    def test_toggle_pages_reconcile_root_preview_without_rewriting_links(self, tmp_path):
        quickstart_dir = tmp_path / "quickstart"
        links_dir = tmp_path / "links"
        quickstart_dir.mkdir()
        links_dir.mkdir()

        canonical_path = quickstart_dir / "index.html"
        links_path = links_dir / "index.html"
        vue_output_path = tmp_path / "quickstart-vue" / "index.html"
        vue_output_path.parent.mkdir()

        toggle = TogglePagesPlugin()
        canonical_page = _make_page(
            url="quickstart/",
            src_path="quickstart.md",
            abs_dest_path=str(canonical_path),
            meta={
                "toggle": {
                    "group": "quickstart",
                    "variant": "react",
                    "canonical": True,
                }
            },
        )
        vue_page = _make_page(
            url="quickstart-vue/",
            src_path="quickstart-vue.md",
            abs_dest_path=str(vue_output_path),
            meta={
                "toggle": {
                    "group": "quickstart",
                    "variant": "vue",
                }
            },
        )

        canonical_html = toggle.on_page_content(
            '<h1 id="quickstart">Quickstart</h1>'
            "<p>React intro.</p>"
            '<h2 id="install">Install</h2>'
            "<p>React install.</p>",
            page=canonical_page,
            config={"plugins": {}},
            files=[],
        )
        self._process_page_output(
            tmp_path,
            output=_wrap_document(canonical_html),
            output_path=canonical_path,
            url="quickstart/",
            src_path="quickstart.md",
            meta=canonical_page.meta,
        )

        toggle.on_page_content(
            '<h1 id="quickstart">Quickstart</h1>'
            "<p>Vue intro.</p>"
            '<h2 id="install">Install</h2>'
            "<p>Vue install.</p>",
            page=vue_page,
            config={"plugins": {}},
            files=[],
        )
        vue_output_path.write_text("<html></html>", encoding="utf-8")
        toggle.on_post_build({"plugins": {}})

        links_path.write_text(
            _wrap_document(
                '<p><a id="plain" href="../quickstart/">Quickstart</a></p>'
                '<p><a id="h1" href="../quickstart/#quickstart">Quickstart title</a></p>'
                '<p><a id="install" href="../quickstart/#install">Install</a></p>'
                '<p><a id="vue-install" href="../quickstart/#vue-install">Vue install</a></p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        links_html = _read(links_path)
        assert 'href="../quickstart/"' in links_html
        assert 'href="../quickstart/#quickstart"' in links_html
        assert 'href="../quickstart/#install"' in links_html
        assert 'href="../quickstart/#vue-install"' in links_html
        assert "__instant-preview__" not in links_html

        quickstart_html = _read(canonical_path)
        root_fragment = _extract_preview_fragment(quickstart_html)
        canonical_fragment = _extract_preview_fragment(quickstart_html, "install")
        vue_fragment = _extract_preview_fragment(quickstart_html, "vue-install")

        assert quickstart_html.count("data-instant-preview-stash") == 1
        assert "Quickstart" in root_fragment
        assert "React intro." in root_fragment
        assert "Install" in root_fragment
        assert "React install." in root_fragment
        assert "toggle-buttons" not in root_fragment
        assert "React install." in canonical_fragment
        assert "Vue install." in vue_fragment
        assert 'id="vue-install"' in quickstart_html
