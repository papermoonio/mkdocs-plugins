import json
from pathlib import Path
from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from plugins.ai_page_actions.plugin import AiPageActionsPlugin
from plugins.instant_preview.plugin import InstantPreviewPlugin
from plugins.page_toggle.plugin import TogglePagesPlugin


def _make_page(
    *,
    url: str,
    src_path: str,
    abs_dest_path: str,
    meta: dict | None = None,
):
    page = MagicMock()
    page.url = url
    page.file.src_path = src_path
    page.file.abs_dest_path = abs_dest_path
    page.is_homepage = False
    page.meta = meta or {}
    page.toc = []
    return page


def _wrap_document(content: str) -> str:
    return (
        "<html><head></head><body>"
        '<div class="md-content">'
        "<article>"
        f"{content}"
        "</article>"
        "</div>"
        "</body></html>"
    )


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _preview_bundle(html: str) -> tuple[dict, dict[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    manifest_node = soup.select_one("script[data-instant-preview-manifest]")
    assert manifest_node is not None
    manifest = json.loads(manifest_node.string or "{}")
    templates = {
        node.get("data-instant-preview-template", ""): node.decode_contents()
        for node in soup.select("template[data-instant-preview-template]")
    }
    return manifest, templates


def _preview_fragment(html: str, key: str) -> str:
    manifest, templates = _preview_bundle(html)
    template_id = manifest["entries"][key]["template"]
    return templates[template_id]


class TestInstantPreview:
    def setup_method(self):
        self.plugin = InstantPreviewPlugin()
        self.plugin.config = {
            "exclude_selectors": [],
            "link_scope_selectors": ["article"],
            "debug": False,
        }

    def test_builds_manifest_templates_for_standard_page(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<div class="hero-shell">'
                '<h1 id="guide">Guide</h1>'
                '<div class="hero-actions">Buttons</div>'
                "</div>"
                "<p>Useful intro.</p>"
                '<h2 id="details">Details</h2>'
                "<p>Deep details.</p>"
            ),
            encoding="utf-8",
        )

        self.plugin.config["exclude_selectors"] = [".hero-actions"]
        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        html = _read(guide_path)
        root_fragment = _preview_fragment(html, "/guide/")
        details_fragment = _preview_fragment(html, "/guide/#details")
        manifest, _ = _preview_bundle(html)

        assert "Guide" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Buttons" not in root_fragment
        assert "Details" in root_fragment
        assert "Deep details." in root_fragment
        assert "Details" in details_fragment
        assert "Deep details." in details_fragment
        assert "/guide/index.html" in manifest["entries"]
        assert "/guide/#guide" in manifest["entries"]
        assert manifest["scopes"] == ["article"]

    def test_root_preview_includes_first_useful_section_when_it_exists(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<h2 id="intro">Introduction</h2>'
                '<p>Useful intro.</p>'
                '<h2 id="details">Details</h2>'
                '<p>Deep details.</p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        root_fragment = _preview_fragment(_read(guide_path), "/guide/")

        assert "Guide" in root_fragment
        assert "Introduction" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Details" not in root_fragment

    def test_root_preview_keeps_header_metadata_and_includes_first_section(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<div class="page-header-row">'
                '<span class="page-header-item">Beginner</span>'
                '<a class="page-header-item page-header-test-badge" href="https://example.com/workflow">'
                '<img src="/badge.svg" alt="passing"/>'
                "</a>"
                "</div>"
                '<h2 id="intro">Introduction</h2>'
                '<p>Useful intro.</p>'
                '<h2 id="details">Details</h2>'
                '<p>Deep details.</p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        root_fragment = _preview_fragment(_read(guide_path), "/guide/")

        assert "Guide" in root_fragment
        assert "page-header-row" in root_fragment
        assert "page-header-test-badge" in root_fragment
        assert "/badge.svg" in root_fragment
        assert "Introduction" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Details" not in root_fragment

    def test_root_preview_keeps_substantive_intro_and_still_includes_first_section(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<div class="page-header-row">'
                '<span class="page-header-item">Beginner</span>'
                "</div>"
                "<p>Useful intro.</p>"
                '<h2 id="details">Details</h2>'
                '<p>Deep details.</p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        root_fragment = _preview_fragment(_read(guide_path), "/guide/")

        assert "Guide" in root_fragment
        assert "page-header-row" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Details" in root_fragment
        assert "Deep details." in root_fragment

    def test_root_preview_keeps_admonition_and_first_section(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<div class="page-header-row">'
                '<span class="page-header-item">Beginner</span>'
                "</div>"
                '<aside class="admonition warning">'
                '<p class="admonition-title">Warning</p>'
                "<p>Read this first.</p>"
                "</aside>"
                '<h2 id="intro">Introduction</h2>'
                '<p>Useful intro.</p>'
                '<h2 id="details">Details</h2>'
                '<p>Deep details.</p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        root_fragment = _preview_fragment(_read(guide_path), "/guide/")

        assert "page-header-row" in root_fragment
        assert "admonition warning" in root_fragment
        assert "Read this first." in root_fragment
        assert "Introduction" in root_fragment
        assert "Useful intro." in root_fragment
        assert "Details" not in root_fragment

    def test_root_preview_keeps_button_wrapper_before_first_section(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<div class="page-header-row">'
                '<span class="page-header-item">Beginner</span>'
                "</div>"
                '<div class="button-wrapper">'
                '<a class="md-button" href="/foo/">Primary CTA</a>'
                '<a class="md-button" href="/bar/">Secondary CTA</a>'
                "</div>"
                "<p>Useful prelude.</p>"
                '<aside class="admonition warning">'
                '<p class="admonition-title">Warning</p>'
                "<p>Handle with care.</p>"
                "</aside>"
                '<h2 id="intro">Introduction</h2>'
                '<p>Useful intro.</p>'
                '<h2 id="details">Details</h2>'
                '<p>Deep details.</p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        root_fragment = _preview_fragment(_read(guide_path), "/guide/")

        assert "button-wrapper" in root_fragment
        assert 'class="md-button"' in root_fragment
        assert "Primary CTA" in root_fragment
        assert "Secondary CTA" in root_fragment
        assert "Useful prelude." in root_fragment
        assert "Handle with care." in root_fragment
        assert "Introduction" in root_fragment
        assert "Useful intro." in root_fragment

    def test_normalizes_complex_blocks_into_preview_safe_markup(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                "<p>Overview.</p>"
                '<h2 id="advanced">Advanced</h2>'
                "<table>"
                "<tr><th>Tool</th><th>Description</th></tr>"
                "<tr><td>Foundry</td><td>Compile and deploy contracts.</td></tr>"
                "<tr><td>Hardhat</td><td>Run tests and scripts.</td></tr>"
                "</table>"
                '<div class="grid cards"><ul>'
                "<li><p><strong>Use Foundry</strong></p><p>Use the Rust toolchain.</p></li>"
                "<li><p><strong>Use Hardhat</strong></p><p>Use the TypeScript toolchain.</p></li>"
                "</ul></div>"
                '<div class="language-bash highlight"><pre><code>'
                "line-1\nline-2\nline-3\nline-4\nline-5\n"
                "line-6\nline-7\nline-8\nline-9\nline-10\nline-11"
                "</code></pre></div>"
                '<div class="status-badge">passing</div>'
                '<div class="md-source-file">Last updated</div>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        fragment = _preview_fragment(_read(guide_path), "/guide/#advanced")

        assert "<table" not in fragment
        assert "grid cards" not in fragment
        assert "md-source-file" not in fragment
        assert "Tool: Foundry; Description: Compile and deploy contracts." in fragment
        assert "Use Foundry: Use the Rust toolchain." in fragment
        assert "<pre><code" in fragment
        assert "line-10" in fragment
        assert "line-11" not in fragment

    def test_unwraps_glightbox_images_without_interactive_wrappers(self, tmp_path):
        guide_dir = tmp_path / "guide"
        guide_dir.mkdir()
        guide_path = guide_dir / "index.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                "<p>Overview.</p>"
                '<h2 id="diagram">Diagram</h2>'
                '<p><a class="glightbox" href="/images/diagram.webp">'
                '<img src="/images/diagram.webp" alt="Diagram"/>'
                "</a></p>"
                '<div class="md-source-file">Created yesterday</div>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        fragment = _preview_fragment(_read(guide_path), "/guide/#diagram")

        assert "<img" in fragment
        assert 'src="/images/diagram.webp"' in fragment
        assert "glightbox" not in fragment
        assert "md-source-file" not in fragment

    def test_keeps_links_clean_and_handles_ai_actions_wrapper(self, tmp_path):
        guide_dir = tmp_path / "guide"
        links_dir = tmp_path / "links"
        guide_dir.mkdir()
        links_dir.mkdir()

        guide_path = guide_dir / "index.html"
        links_path = links_dir / "index.html"

        actions = AiPageActionsPlugin()
        actions._config_loaded = True
        guide_page = _make_page(
            url="guide/",
            src_path="guide.md",
            abs_dest_path=str(guide_path),
        )
        guide_html = actions.on_post_page(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                '<div class="page-header-row">'
                '<span class="page-header-item">'
                '<svg class="page-header-item-icon" viewBox="0 0 24 24">'
                '<path d="M19.5 5.5v13h-2v-13z"></path>'
                "</svg>"
                "Intermediate</span>"
                '<div class="status-badge"><img src="/badge.svg" alt="passing"/></div>'
                '<div class="ai-file-actions-container">LLM</div>'
                "</div>"
                "<p>Useful intro.</p>"
                '<h2 id="details">Details</h2>'
                "<p>Deep details.</p>"
            ),
            page=guide_page,
            config={"site_url": "https://example.com/"},
        )
        guide_path.write_text(guide_html, encoding="utf-8")
        links_path.write_text(
            _wrap_document(
                '<p><a href="../guide/">Guide</a></p>'
                '<p><a href="../guide/#guide">Guide title</a></p>'
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        guide_fragment = _preview_fragment(_read(guide_path), "/guide/")
        links_html = _read(links_path)

        assert "Guide" in guide_fragment
        assert "page-header-row" in guide_fragment
        assert "status-badge" in guide_fragment
        assert "Intermediate" in guide_fragment
        assert "/badge.svg" in guide_fragment
        assert "page-header-item-icon" in guide_fragment
        assert "<path d=" in guide_fragment
        assert "Useful intro." in guide_fragment
        assert "ai-file-actions-container" not in guide_fragment
        assert 'href="../guide/"' in links_html
        assert 'href="../guide/#guide"' in links_html

    def test_builds_toggle_previews_without_cloning_toggle_ui(self, tmp_path):
        quickstart_dir = tmp_path / "quickstart"
        quickstart_dir.mkdir()
        canonical_path = quickstart_dir / "index.html"
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
            meta={"toggle": {"group": "quickstart", "variant": "vue"}},
        )

        canonical_html = toggle.on_page_content(
            '<h1 id="quickstart">Quickstart</h1>'
            "<p>React intro.</p>"
            '<div class="status-badge">passing</div>'
            '<div class="language-bash highlight"><pre><code>'
            "react-1\nreact-2\nreact-3\nreact-4\nreact-5\n"
            "react-6\nreact-7\nreact-8\nreact-9\nreact-10\nreact-11"
            "</code></pre></div>"
            '<h2 id="install">Install</h2>'
            "<table>"
            "<tr><th>Step</th><th>Command</th></tr>"
            "<tr><td>Install</td><td>pnpm install</td></tr>"
            "<tr><td>Run</td><td>pnpm dev</td></tr>"
            "</table>",
            page=canonical_page,
            config={"plugins": {}},
            files=[],
        )
        canonical_path.write_text(_wrap_document(canonical_html), encoding="utf-8")

        toggle.on_page_content(
            '<h1 id="quickstart">Quickstart</h1>'
            "<p>Vue intro.</p>"
            '<div class="status-badge">passing</div>'
            '<div class="language-bash highlight"><pre><code>'
            "vue-1\nvue-2\nvue-3\nvue-4\nvue-5\n"
            "vue-6\nvue-7\nvue-8\nvue-9\nvue-10\nvue-11"
            "</code></pre></div>"
            '<h2 id="install">Install</h2>'
            "<table>"
            "<tr><th>Step</th><th>Command</th></tr>"
            "<tr><td>Install</td><td>pnpm install</td></tr>"
            "<tr><td>Run</td><td>pnpm dev:vue</td></tr>"
            "</table>",
            page=vue_page,
            config={"plugins": {}},
            files=[],
        )
        vue_output_path.write_text("<html></html>", encoding="utf-8")
        toggle.on_post_build({"plugins": {}})

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        html = _read(canonical_path)
        root_fragment = _preview_fragment(html, "/quickstart/")
        vue_root_fragment = _preview_fragment(html, "/quickstart/#vue")
        install_fragment = _preview_fragment(html, "/quickstart/#install")
        vue_install_fragment = _preview_fragment(html, "/quickstart/#vue-install")

        assert "Quickstart" in root_fragment
        assert "React intro." in root_fragment
        assert "toggle-buttons" not in root_fragment
        assert "status-badge" in root_fragment
        assert "<pre><code" in root_fragment
        assert "react-10" in root_fragment
        assert "react-11" not in root_fragment
        assert "Vue intro." in vue_root_fragment
        assert "status-badge" in vue_root_fragment
        assert "Step: Install; Command: pnpm install" in install_fragment
        assert "Step: Run; Command: pnpm dev:vue" in vue_install_fragment
        assert "<table" not in install_fragment
        assert "<table" not in vue_install_fragment
        assert "toggle-buttons" not in vue_root_fragment

    def test_falls_back_to_first_section_for_toggle_root_without_intro_blocks(self, tmp_path):
        hardhat_dir = tmp_path / "hardhat"
        hardhat_dir.mkdir()
        canonical_path = hardhat_dir / "index.html"
        pvm_output_path = tmp_path / "hardhat-pvm" / "index.html"
        pvm_output_path.parent.mkdir()

        toggle = TogglePagesPlugin()
        canonical_page = _make_page(
            url="hardhat/",
            src_path="hardhat.md",
            abs_dest_path=str(canonical_path),
            meta={
                "toggle": {
                    "group": "hardhat",
                    "variant": "evm",
                    "canonical": True,
                }
            },
        )
        pvm_page = _make_page(
            url="hardhat-pvm/",
            src_path="hardhat-pvm.md",
            abs_dest_path=str(pvm_output_path),
            meta={"toggle": {"group": "hardhat", "variant": "pvm"}},
        )

        canonical_html = toggle.on_page_content(
            '<h1 id="hardhat">Hardhat</h1>'
            '<h2 id="introduction">Introduction</h2>'
            '<p>EVM intro.</p>'
            '<h2 id="details">Details</h2>'
            '<p>EVM details.</p>',
            page=canonical_page,
            config={"plugins": {}},
            files=[],
        )
        canonical_path.write_text(_wrap_document(canonical_html), encoding="utf-8")

        toggle.on_page_content(
            '<h1 id="hardhat-polkadot">Hardhat Polkadot</h1>'
            '<h2 id="introduction">Introduction</h2>'
            '<p>PVM intro.</p>'
            '<h2 id="details">Details</h2>'
            '<p>PVM details.</p>',
            page=pvm_page,
            config={"plugins": {}},
            files=[],
        )
        pvm_output_path.write_text("<html></html>", encoding="utf-8")
        toggle.on_post_build({"plugins": {}})

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        html = _read(canonical_path)
        root_fragment = _preview_fragment(html, "/hardhat/")
        pvm_fragment = _preview_fragment(html, "/hardhat/#pvm")

        assert "Hardhat" in root_fragment
        assert "Introduction" in root_fragment
        assert "EVM intro." in root_fragment
        assert "Details" not in root_fragment
        assert "Hardhat Polkadot" in pvm_fragment
        assert "Introduction" in pvm_fragment
        assert "PVM intro." in pvm_fragment

    def test_toggle_root_metadata_does_not_block_first_section_fallback(self, tmp_path):
        local_dir = tmp_path / "local-dev-node"
        local_dir.mkdir()
        canonical_path = local_dir / "index.html"
        other_output_path = tmp_path / "local-dev-node-alt" / "index.html"
        other_output_path.parent.mkdir()

        toggle = TogglePagesPlugin()
        canonical_page = _make_page(
            url="local-dev-node/",
            src_path="local-dev-node.md",
            abs_dest_path=str(canonical_path),
            meta={
                "toggle": {
                    "group": "local-dev-node",
                    "variant": "stable",
                    "canonical": True,
                }
            },
        )
        other_page = _make_page(
            url="local-dev-node-alt/",
            src_path="local-dev-node-alt.md",
            abs_dest_path=str(other_output_path),
            meta={"toggle": {"group": "local-dev-node", "variant": "next"}},
        )

        canonical_html = toggle.on_page_content(
            '<h1 id="local-development-node">Local Development Node</h1>'
            '<div class="page-header-row">'
            '<a class="page-header-item page-header-test-badge" href="https://example.com/workflow">'
            '<img src="/badge.svg" alt="passing"/>'
            "</a>"
            "</div>"
            '<h2 id="introduction">Introduction</h2>'
            '<p>Stable intro.</p>'
            '<h2 id="details">Details</h2>'
            '<p>Stable details.</p>',
            page=canonical_page,
            config={"plugins": {}},
            files=[],
        )
        canonical_path.write_text(_wrap_document(canonical_html), encoding="utf-8")

        toggle.on_page_content(
            '<h1 id="local-development-node">Local Development Node</h1>'
            '<div class="page-header-row">'
            '<a class="page-header-item page-header-test-badge" href="https://example.com/workflow-next">'
            '<img src="/badge-next.svg" alt="passing"/>'
            "</a>"
            "</div>"
            '<h2 id="introduction">Introduction</h2>'
            '<p>Next intro.</p>'
            '<h2 id="details">Details</h2>'
            '<p>Next details.</p>',
            page=other_page,
            config={"plugins": {}},
            files=[],
        )
        other_output_path.write_text("<html></html>", encoding="utf-8")
        toggle.on_post_build({"plugins": {}})

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        html = _read(canonical_path)
        root_fragment = _preview_fragment(html, "/local-dev-node/")
        next_fragment = _preview_fragment(html, "/local-dev-node/#next")

        assert "Local Development Node" in root_fragment
        assert "page-header-row" in root_fragment
        assert "/badge.svg" in root_fragment
        assert "Introduction" in root_fragment
        assert "Stable intro." in root_fragment
        assert "Details" not in root_fragment
        assert "/badge-next.svg" in next_fragment
        assert "Introduction" in next_fragment
        assert "Next intro." in next_fragment

    def test_registers_aliases_for_flat_html_outputs(self, tmp_path):
        guide_path = tmp_path / "guide.html"
        guide_path.write_text(
            _wrap_document(
                '<h1 id="guide">Guide</h1>'
                "<p>Useful intro.</p>"
                '<h2 id="details">Details</h2>'
                "<p>Deep details.</p>"
            ),
            encoding="utf-8",
        )

        self.plugin.on_post_build({"site_dir": str(tmp_path)})

        html = _read(guide_path)
        manifest, _ = _preview_bundle(html)

        assert "/guide/" in manifest["entries"]
        assert "/guide.html" in manifest["entries"]
        assert "/guide/#details" in manifest["entries"]
        assert "/guide.html#details" in manifest["entries"]
