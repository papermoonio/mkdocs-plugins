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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class TestInstantPreviewCompat:
    def setup_method(self):
        self.plugin = InstantPreviewCompatPlugin()
        self.plugin.config = {
            "exclude_selectors": [],
            "rewrite_internal_links": True,
        }

    def _start_build(self, tmp_path: Path) -> None:
        self.plugin.on_pre_build(config={"site_dir": str(tmp_path)})

    def _process_page_output(
        self,
        tmp_path: Path,
        *,
        output: str,
        output_path: Path,
        url: str,
        src_path: str,
        meta: dict | None = None,
    ) -> tuple[str, str]:
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
        relative_output = output_path.relative_to(tmp_path).as_posix()
        return processed, relative_output

    def test_rewrites_no_hash_and_h1_links_for_ai_action_pages(self, tmp_path):
        self._start_build(tmp_path)

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
        _, relative_guide = self._process_page_output(
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

        state = self.plugin._states[relative_guide]
        assert state.root_proxy_id is not None

        links_html = _read(links_path)
        assert f'href="../guide/#{state.root_proxy_id}"' in links_html

        guide_html = _read(guide_path)
        fragment = _extract_preview_fragment(guide_html, state.root_proxy_id)
        assert "Guide" in fragment
        assert "Useful intro." in fragment
        assert "Details" in fragment
        assert "Deep details." in fragment
        assert "ai-file-actions-container" not in fragment

    def test_rewrites_wrapped_h1_without_touching_other_plugins(self, tmp_path):
        self._start_build(tmp_path)

        guide_dir = tmp_path / "guide"
        links_dir = tmp_path / "links"
        guide_dir.mkdir()
        links_dir.mkdir()

        guide_path = guide_dir / "index.html"
        links_path = links_dir / "index.html"

        self.plugin.config["exclude_selectors"] = [".hero-actions"]
        _, relative_guide = self._process_page_output(
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
            _wrap_document(
                '<p><a id="plain" href="../guide/">Guide</a></p>'
                '<p><a id="h1" href="../guide/#overview">Overview</a></p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        state = self.plugin._states[relative_guide]
        assert state.root_proxy_id is not None

        links_html = _read(links_path)
        assert f'href="../guide/#{state.root_proxy_id}"' in links_html

        guide_html = _read(guide_path)
        fragment = _extract_preview_fragment(guide_html, state.root_proxy_id)
        assert "Overview" in fragment
        assert "Beginner" in fragment
        assert "Passing" in fragment
        assert "Introduction" in fragment
        assert "Actual intro." in fragment
        assert "Buttons" not in fragment

    def test_hoists_excluded_blocks_for_h2_and_h3_previews(self, tmp_path):
        self._start_build(tmp_path)

        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"

        self.plugin.config["exclude_selectors"] = [".status-badge"]
        processed_html, _ = self._process_page_output(
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

    def test_toggle_pages_support_root_h1_and_variant_heading_previews(self, tmp_path):
        self._start_build(tmp_path)

        quickstart_dir = tmp_path / "quickstart"
        links_dir = tmp_path / "links"
        quickstart_dir.mkdir()
        links_dir.mkdir()

        canonical_path = quickstart_dir / "index.html"
        links_path = links_dir / "index.html"
        vue_output_path = tmp_path / "quickstart-vue" / "index.html"
        vue_output_path.parent.mkdir()

        toggle = TogglePagesPlugin()
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

        toggle.on_page_content(
            '<h1 id="quickstart">Quickstart</h1>'
            "<p>Vue intro.</p>"
            '<h2 id="install">Install</h2>'
            "<p>Vue install.</p>",
            page=vue_page,
            config={"plugins": {}},
            files=[],
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

        processed_html, relative_canonical = self._process_page_output(
            tmp_path,
            output=_wrap_document(canonical_html),
            output_path=canonical_path,
            url="quickstart/",
            src_path="quickstart.md",
            meta=canonical_page.meta,
        )

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

        state = self.plugin._states[relative_canonical]
        assert state.root_proxy_id is not None

        links_html = _read(links_path)
        assert f'href="../quickstart/#{state.root_proxy_id}"' in links_html
        assert 'href="../quickstart/#install"' in links_html
        assert 'href="../quickstart/#vue-install"' in links_html

        root_fragment = _extract_preview_fragment(processed_html, state.root_proxy_id)
        canonical_fragment = _extract_preview_fragment(processed_html, "install")
        vue_fragment = _extract_preview_fragment(processed_html, "vue-install")

        assert "Quickstart" in root_fragment
        assert "React intro." in root_fragment
        assert "Install" in root_fragment
        assert "React install." in root_fragment
        assert "toggle-buttons" not in root_fragment
        assert "React install." in canonical_fragment
        assert "Vue install." in vue_fragment
        assert 'id="vue-install"' in processed_html
