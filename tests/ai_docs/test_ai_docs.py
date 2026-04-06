import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml
from bs4 import BeautifulSoup

from plugins.ai_docs.plugin import AIDocsPlugin


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_plugin(**config_overrides):
    """Return an AIDocsPlugin with a pre-populated config dict."""
    plugin = AIDocsPlugin()
    plugin.config = {
        "llms_config": "llms_config.json",
        "ai_resources_page": True,
        "ai_page_actions": True,
        **config_overrides,
    }
    return plugin


def _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/", llms_config=None):
    """Write a minimal llms_config.json and return a mock MkDocs config dict."""
    if llms_config is None:
        llms_config = {
            "project": {"name": "TestProject"},
            "content": {
                "categories_info": {
                    "basics": {"name": "Basics", "description": "Basic docs."}
                },
                "exclusions": {"skip_basenames": ["README.md"], "skip_paths": []},
            },
            "outputs": {"public_root": "/ai/"},
        }
    config_file = tmp_path / "llms_config.json"
    config_file.write_text(json.dumps(llms_config), encoding="utf-8")
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text("", encoding="utf-8")
    return {"config_file_path": str(mkdocs_yml), "site_url": site_url}


def _make_page(src_path="guide.md", is_homepage=False, meta=None, url="guide/"):
    page = MagicMock()
    page.file.src_path = src_path
    page.is_homepage = is_homepage
    page.meta = meta or {}
    page.url = url
    return page


# ===========================================================================
# Feature flags
# ===========================================================================

class TestFeatureFlags:
    """Tests that feature flags correctly gate each hook."""

    def test_ai_resources_page_disabled_skips_generation(self, tmp_path):
        """on_page_markdown returns the original markdown unchanged when ai_resources_page=False."""
        plugin = _make_plugin(ai_resources_page=False)
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        original = "# Original Content"
        result = plugin.on_page_markdown(original, page=page, config=config, files=[])
        assert result == original

    def test_ai_resources_page_enabled_generates_content(self, tmp_path):
        """on_page_markdown replaces content for ai-resources.md when ai_resources_page=True."""
        plugin = _make_plugin(ai_resources_page=True)
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "# AI Resources" in result

    def test_ai_page_actions_disabled_skips_widget(self, tmp_path):
        """on_post_page returns HTML unchanged when ai_page_actions=False."""
        plugin = _make_plugin(ai_page_actions=False)
        plugin._config_loaded = True
        page = _make_page(is_homepage=False)
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert result == output

    def test_ai_page_actions_enabled_injects_widget(self, tmp_path):
        """on_post_page injects the widget when ai_page_actions=True."""
        plugin = _make_plugin(ai_page_actions=True)
        plugin._config_loaded = True
        page = _make_page(is_homepage=False)
        output = '<div class="md-content"><h1>Guide</h1><p>Content</p></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert result != output
        assert "h1-ai-actions-wrapper" in result


# ===========================================================================
# Shared config loading
# ===========================================================================

class TestSharedConfigLoading:
    """Tests that llms_config.json is loaded once and shared across hooks."""

    def test_config_loaded_once(self, tmp_path):
        """_ensure_config_loaded only reads the file on the first call."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        plugin._ensure_config_loaded(config)
        plugin._ensure_config_loaded(config)
        assert plugin._llms_config.get("project", {}).get("name") == "TestProject"

    def test_config_populates_skip_lists(self, tmp_path):
        """_ensure_config_loaded extracts skip_basenames and skip_paths from config."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        plugin._ensure_config_loaded(config)
        assert "README.md" in plugin._skip_basenames

    def test_config_missing_raises(self, tmp_path):
        """_ensure_config_loaded raises FileNotFoundError when llms_config.json is absent."""
        plugin = _make_plugin(llms_config="nonexistent.json")
        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("", encoding="utf-8")
        config = {"config_file_path": str(mkdocs_yml), "site_url": ""}
        import pytest
        with pytest.raises(FileNotFoundError):
            plugin._ensure_config_loaded(config)


# ===========================================================================
# File discovery (ported from test_resolve_md)
# ===========================================================================

class TestGetAllMarkdownFiles:
    """Tests for file discovery with dot-directory and skip filtering."""

    def _create_tree(self, base, structure):
        for name, children in structure.items():
            path = os.path.join(base, name)
            if isinstance(children, dict):
                os.makedirs(path, exist_ok=True)
                self._create_tree(path, children)
            else:
                with open(path, "w") as f:
                    f.write(children or "")

    def test_skips_dot_directories(self):
        """Dot-directories are always excluded without being in skip_paths."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "guide.md": "",
                ".snippets": {"nav.md": ""},
                ".github": {"CONTRIBUTING.md": ""},
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "nav.md" not in basenames
            assert "CONTRIBUTING.md" not in basenames

    def test_skips_dot_files(self):
        """Dot-files are always excluded without being in skip_basenames."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "guide.md": "",
                ".hidden.md": "",
                "subdir": {".secret.md": "", "page.md": ""},
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "page.md" in basenames
            assert ".hidden.md" not in basenames
            assert ".secret.md" not in basenames

    def test_skips_nested_dot_directories(self):
        """Dot-directories nested under normal dirs are also excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "docs": {"page.md": "", ".hidden": {"secret.md": ""}},
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "page.md" in basenames
            assert "secret.md" not in basenames

    def test_skip_paths_still_works(self):
        """Manual skip_paths continue to work alongside dot-directory skipping."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {"guide.md": "", "venv": {"pkg.md": ""}})
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], ["venv"])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "pkg.md" not in basenames

    def test_skip_basenames_still_works(self):
        """Manual skip_basenames continue to work alongside dot-directory skipping."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {"guide.md": "", "README.md": ""})
            results = AIDocsPlugin.get_all_markdown_files(tmp, ["README.md"], [])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "README.md" not in basenames

    def test_always_skips_root_index(self):
        """The root index.md (homepage) is always excluded even without skip_basenames."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "index.md": "",
                "guide.md": "",
                "subdir": {"index.md": "", "page.md": ""},
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], [])
            rel_paths = [os.path.relpath(f, tmp) for f in results]
            assert os.path.join(tmp, "index.md") not in results
            assert os.path.join("subdir", "index.md") in rel_paths
            assert "guide.md" in [os.path.basename(f) for f in results]

    def test_skip_basenames_index_skips_all_index_files(self):
        """Adding index.md to skip_basenames excludes all index.md files site-wide."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "index.md": "",
                "guide.md": "",
                "subdir": {"index.md": "", "page.md": ""},
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, ["index.md"], [])
            basenames = [os.path.basename(f) for f in results]
            assert "index.md" not in basenames
            assert "guide.md" in basenames
            assert "page.md" in basenames

    def test_collects_md_and_mdx(self):
        """Both .md and .mdx files are collected."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "page.md": "",
                "component.mdx": "",
                "style.css": "",
            })
            results = AIDocsPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "page.md" in basenames
            assert "component.mdx" in basenames
            assert "style.css" not in basenames


# ===========================================================================
# Git timestamps (ported from test_resolve_md)
# ===========================================================================

class TestGetGitLastUpdated:
    """Tests for the git timestamp helper."""

    def test_returns_iso_timestamp_for_tracked_file(self):
        """A file tracked by git returns an ISO-8601 timestamp string."""
        ts = AIDocsPlugin.get_git_last_updated(__file__)
        assert ts
        assert "T" in ts

    def test_handles_z_suffix_on_python310(self):
        """Timestamps ending with 'Z' are normalised so Python 3.10 can parse them."""
        mock_result = type("R", (), {"stdout": "2026-03-09T14:16:33Z", "returncode": 0})()
        with patch("plugins.ai_docs.plugin.subprocess.run", return_value=mock_result):
            ts = AIDocsPlugin.get_git_last_updated(__file__)
        assert ts == "2026-03-09T14:16:33+00:00"

    def test_falls_back_for_untracked_file(self):
        """An untracked temp file falls back to filesystem mtime."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"hello")
            tmp_path = f.name
        try:
            ts = AIDocsPlugin.get_git_last_updated(tmp_path)
            assert ts
            assert "T" in ts
        finally:
            os.unlink(tmp_path)


# ===========================================================================
# write_ai_page (ported from test_resolve_md)
# ===========================================================================

class TestWriteAiPage:
    """Tests that write_ai_page writes correct front matter."""

    def test_front_matter_contains_versioning_fields(self):
        plugin = _make_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "pages" / "test-page.md"
            header = {
                "title": "Test Page",
                "url": "https://example.com/test/",
                "word_count": 100,
                "token_estimate": 150,
                "version_hash": "sha256:abc123",
                "last_updated": "2025-01-15T10:00:00+00:00",
            }
            plugin.write_ai_page(out_path, header, "# Hello\n\nWorld.")
            content = out_path.read_text()
            fm = yaml.safe_load(content.split("---")[1])
            assert fm["version_hash"] == "sha256:abc123"
            assert fm["last_updated"] == "2025-01-15T10:00:00+00:00"


# ===========================================================================
# write_category_bundle (ported from test_resolve_md)
# ===========================================================================

class TestWriteCategoryBundle:
    """Tests that category bundles include versioning metadata."""

    def _make_pages(self):
        return [
            {
                "slug": "page-one",
                "title": "Page One",
                "description": "First page",
                "url": "https://example.com/one/",
                "word_count": 50,
                "token_estimate": 75,
                "version_hash": "sha256:aaa",
                "last_updated": "2025-01-10T08:00:00+00:00",
                "body": "# Page One\n\nContent here.",
            },
        ]

    def test_bundle_front_matter_has_build_timestamp_and_hash(self):
        plugin = _make_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "bundle.md"
            plugin.write_category_bundle(
                out_path, "Test", False, [], self._make_pages(),
                build_timestamp="2025-06-01T00:00:00+00:00",
            )
            fm = yaml.safe_load(out_path.read_text().split("---")[1])
            assert fm["build_timestamp"] == "2025-06-01T00:00:00+00:00"
            assert fm["version_hash"].startswith("sha256:")

    def test_bundle_page_entry_has_last_updated_and_hash(self):
        plugin = _make_plugin()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "bundle.md"
            plugin.write_category_bundle(out_path, "Test", False, [], self._make_pages())
            content = out_path.read_text()
            assert "- Last Updated: 2025-01-10T08:00:00+00:00" in content
            assert "- Version Hash: sha256:aaa" in content


# ===========================================================================
# build_site_index (ported from test_resolve_md)
# ===========================================================================

class TestBuildSiteIndex:
    """Tests that site-index.json and llms-full.jsonl include versioning metadata."""

    def _make_pages(self):
        return [
            {
                "slug": "test-page",
                "title": "Test",
                "categories": [],
                "url": "https://example.com/test/",
                "word_count": 10,
                "token_estimate": 15,
                "version_hash": "sha256:abc",
                "last_updated": "2025-03-01T12:00:00+00:00",
                "body": "## Heading\n\nSome text.",
            },
        ]

    def test_site_index_has_top_level_build_metadata(self):
        plugin = _make_plugin()
        plugin._llms_config = {"outputs": {"files": {}}}
        with tempfile.TemporaryDirectory() as tmp:
            ai_root = Path(tmp)
            plugin.build_site_index(self._make_pages(), ai_root, "2025-06-01T00:00:00+00:00")
            index = json.loads((ai_root / "site-index.json").read_text())
            assert index["build_timestamp"] == "2025-06-01T00:00:00+00:00"
            assert index["version_hash"].startswith("sha256:")
            assert index["page_count"] == 1
            entry = index["pages"][0]
            assert entry["version_hash"] == "sha256:abc"
            assert entry["last_updated"] == "2025-03-01T12:00:00+00:00"

    def test_jsonl_sections_have_page_versioning(self):
        plugin = _make_plugin()
        plugin._llms_config = {"outputs": {"files": {}}}
        with tempfile.TemporaryDirectory() as tmp:
            ai_root = Path(tmp)
            plugin.build_site_index(self._make_pages(), ai_root, "2025-06-01T00:00:00+00:00")
            lines = (ai_root / "llms-full.jsonl").read_text().strip().splitlines()
            assert len(lines) >= 1
            section = json.loads(lines[0])
            assert section["page_version_hash"] == "sha256:abc"
            assert section["last_updated"] == "2025-03-01T12:00:00+00:00"


# ===========================================================================
# format_llms_metadata_section (ported from test_resolve_md)
# ===========================================================================

class TestFormatLlmsMetadataSection:
    """Tests that llms.txt metadata includes build_timestamp and version_hash."""

    def test_metadata_section_includes_versioning(self):
        pages = [{"categories": ["basics"], "body": "hello world"}]
        section = AIDocsPlugin.format_llms_metadata_section(
            pages, "2025-06-01T00:00:00+00:00"
        )
        assert "Build Timestamp: 2025-06-01T00:00:00+00:00" in section
        assert "Version Hash: sha256:" in section


# ===========================================================================
# Page exclusions (ported from test_ai_page_actions)
# ===========================================================================

class TestHomepageSkip:
    """Tests that the homepage is always skipped by on_post_page."""

    def setup_method(self):
        self.plugin = _make_plugin()
        self.plugin._config_loaded = True

    def test_homepage_returns_output_unchanged(self):
        """The homepage should be skipped, returning the output as-is."""
        page = _make_page(is_homepage=True, src_path="index.md")
        output = "<h1>Home</h1>"
        result = self.plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert result == output

    def test_non_homepage_is_not_skipped(self):
        """A regular page should not be skipped by the homepage check."""
        page = _make_page(is_homepage=False, src_path="guide.md")
        output = '<div class="md-content"><h1>Guide</h1><p>Content</p></div>'
        result = self.plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert result != output


# ===========================================================================
# _wrap_h1 subpath handling (ported from test_ai_page_actions)
# ===========================================================================

class TestWrapH1SubpathHandling:
    """Tests that _wrap_h1 correctly prefixes the URL with the site subpath."""

    def setup_method(self):
        self.plugin = _make_plugin()

    def _make_soup_with_h1(self):
        html = '<div class="md-content"><h1>Hello</h1></div>'
        soup = BeautifulSoup(html, "html.parser")
        return soup, soup.find("h1")

    def test_root_site_url(self):
        """site_url at root should produce /directory/page.md."""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "directory/page.md", soup, site_url="https://docs.polkadot.com/")
        assert soup.find(attrs={"data-url": True})["data-url"] == "/directory/page.md"

    def test_subpath_site_url(self):
        """site_url with subpath should produce /docs/directory/page.md."""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "directory/page.md", soup, site_url="https://wormhole.com/docs/")
        assert soup.find(attrs={"data-url": True})["data-url"] == "/docs/directory/page.md"

    def test_no_site_url(self):
        """Empty site_url should produce /directory/page.md."""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "directory/page.md", soup, site_url="")
        assert soup.find(attrs={"data-url": True})["data-url"] == "/directory/page.md"

    def test_deep_subpath(self):
        """site_url with deep subpath should produce the correct prefix."""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "directory/page.md", soup, site_url="https://example.com/a/b/c/")
        assert soup.find(attrs={"data-url": True})["data-url"] == "/a/b/c/directory/page.md"


# ===========================================================================
# on_page_markdown — ai_resources_page
# ===========================================================================

class TestAiResourcesPageMarkdown:
    """Tests for on_page_markdown output: static prose and placeholder divs."""

    def test_emits_aggregate_placeholder_div(self, tmp_path):
        """on_page_markdown should include the aggregate table HTML comment placeholder."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert '<!-- ai-resources-aggregate-table -->' in result

    def test_emits_category_placeholder_divs(self, tmp_path):
        """on_page_markdown should include an HTML comment placeholder for each configured category."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert '<!-- ai-category-basics-table -->' in result

    def test_emits_static_prose(self, tmp_path):
        """on_page_markdown should include the overview heading and access section."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "# AI Resources" in result
        assert "## Access LLM Files" in result

    def test_emits_category_headings_for_toc(self, tmp_path):
        """on_page_markdown should emit ### Category Files and per-category #### headings for TOC."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "### Category Files" in result
        assert "#### Basics" in result

    def test_no_table_rows_in_markdown(self, tmp_path):
        """on_page_markdown must not contain table rows — those are injected in on_post_build."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        # Check that artifact URLs (not just filenames) are absent — filenames appear in prose
        assert "/ai/site-index.json" not in result
        assert "/ai/llms-full.jsonl" not in result
        assert "/ai/categories/" not in result

    def test_non_resources_page_unchanged(self, tmp_path):
        """on_page_markdown should leave non-ai-resources pages untouched."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="guide.md")
        original = "# Guide\n\nSome content."
        result = plugin.on_page_markdown(original, page=page, config=config, files=[])
        assert result == original

    def test_missing_project_name_raises(self, tmp_path):
        """A missing project.name in llms_config raises a KeyError."""
        import pytest
        llms_config = {
            "project": {},
            "content": {"categories_info": {}},
            "outputs": {"public_root": "/ai/"},
        }
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, llms_config=llms_config)
        page = _make_page(src_path="ai-resources.md")
        with pytest.raises(KeyError):
            plugin.on_page_markdown("", page=page, config=config, files=[])

# ===========================================================================
# Connect via MCP Section in AI Resources Page
# ===========================================================================

class TestMCPSection:
    """Tests for MCP install section on the AI Resources page."""

    def test_mcp_section_present_when_configured(self, tmp_path):
        """MCP section should appear when mcp_name and mcp_url are set in project config."""
        llms_config = {
            "project": {
                "name": "TestProject",
                "mcp_name": "test-mcp",
                "mcp_url": "https://mcp.example.com/sse",
            },
            "content": {
                "categories_info": {
                    "basics": {"name": "Basics", "description": "Basic docs."}
                          },
                "exclusions": {"skip_basenames": [], "skip_paths": []},
            },
            "outputs": {"public_root": "/ai/"},
        }

        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, llms_config=llms_config)
        page = _make_page(src_path="ai-resources.md")

        result = plugin.on_page_markdown("", page=page, config=config, files=[])

        assert "## Connect via MCP" in result
        assert "https://mcp.example.com/sse" in result
        # All 5 client rows should be present
        assert "Cursor" in result
        assert "VS Code" in result
        assert "Claude Code CLI" in result
        assert "Codex CLI" in result
        assert ":simple-claude: Claude" in result
        # Deeplinks should be generated
        assert "cursor://anysphere.cursor-deeplink" in result
        assert "vscode:mcp/install?" in result

    def test_mcp_section_absent_when_not_configured(self, tmp_path):
        """MCP section should not appear when mcp_name/mcp_url are missing."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path)
        page = _make_page(src_path="ai-resources.md")

        result = plugin.on_page_markdown("", page=page, config=config, files=[])

        assert "## Connect via MCP" not in result

# ===========================================================================
# _build_aggregate_table_html — URL and token estimate correctness
# ===========================================================================

class TestBuildAggregateTableHtml:
    """Tests that _build_aggregate_table_html produces correct URLs and token counts."""

    def _make_table(self, tmp_path, site_url, aggregate_tokens=None):
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url=site_url)
        plugin._ensure_config_loaded(config)
        from urllib.parse import urlparse
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""
        return plugin._build_aggregate_table_html(
            base_path, "/ai", site_url, aggregate_tokens or {}
        )

    def test_root_site_url(self, tmp_path):
        """Root deploy should produce URLs without a prefix."""
        table = self._make_table(tmp_path, "https://docs.polkadot.com/")
        assert "/ai/site-index.json" in table
        assert "/ai/llms-full.jsonl" in table
        assert "/llms.txt" in table
        assert "/docs/" not in table

    def test_subpath_site_url(self, tmp_path):
        """Subpath deploy should prepend /docs/ to all artifact URLs."""
        table = self._make_table(tmp_path, "https://wormhole.com/docs/")
        assert "/docs/ai/site-index.json" in table
        assert "/docs/ai/llms-full.jsonl" in table
        assert "/docs/llms.txt" in table

    def test_empty_site_url(self, tmp_path):
        """Empty site_url should produce URLs without a prefix."""
        table = self._make_table(tmp_path, "")
        assert "/ai/site-index.json" in table
        assert "/llms.txt" in table

    def test_rows_show_dash_when_zero(self, tmp_path):
        """All rows show '—' when all token counts are zero."""
        table = self._make_table(tmp_path, "https://docs.example.com/")
        assert table.count(">—<") == 3

    def test_aggregate_rows_show_token_counts(self, tmp_path):
        """Aggregate rows show formatted counts when aggregate_tokens is provided."""
        agg = {"llms_txt": 500, "site_index": 12345, "llms_full": 999999}
        table = self._make_table(tmp_path, "https://docs.example.com/", aggregate_tokens=agg)
        assert "500" in table
        assert "12,345" in table
        assert "999,999" in table

    def test_token_estimate_column_header(self, tmp_path):
        """Table should include 'Token Estimate' column."""
        table = self._make_table(tmp_path, "https://docs.example.com/")
        assert "Token Estimate" in table

# ===========================================================================
# _build_category_table_html — URL and token estimate correctness
# ===========================================================================

class TestBuildCategoryTableHtml:
    """Tests that _build_category_table_html produces correct URLs and token counts."""

    def _make_table(self, tmp_path, site_url, category_tokens=None, category_light_tokens=None):
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url=site_url)
        plugin._ensure_config_loaded(config)
        from urllib.parse import urlparse
        base_path = urlparse(site_url).path.rstrip("/") if site_url else ""
        return plugin._build_category_table_html(
            "basics", base_path, "/ai", site_url,
            category_tokens or {}, category_light_tokens or {},
        )

    def test_root_site_url(self, tmp_path):
        """Root deploy should produce category URLs without a prefix."""
        table = self._make_table(tmp_path, "https://docs.polkadot.com/")
        assert "/ai/categories/basics.md" in table
        assert "/ai/categories/basics-light.md" in table
        assert "/docs/" not in table

    def test_subpath_site_url(self, tmp_path):
        """Subpath deploy should prepend /docs/ to category URLs."""
        table = self._make_table(tmp_path, "https://wormhole.com/docs/")
        assert "/docs/ai/categories/basics.md" in table
        assert "/docs/ai/categories/basics-light.md" in table

    def test_token_estimate_in_bundle_row(self, tmp_path):
        """Full bundle row should display the pre-computed token estimate."""
        table = self._make_table(tmp_path, "https://docs.example.com/", category_tokens={"basics": 1234})
        assert "1,234" in table

    def test_token_estimate_in_light_row(self, tmp_path):
        """Light file row should display its own pre-computed token estimate."""
        table = self._make_table(tmp_path, "https://docs.example.com/", category_light_tokens={"basics": 567})
        assert "567" in table

    def test_rows_show_dash_when_zero(self, tmp_path):
        """Both rows show '—' when token counts are zero."""
        table = self._make_table(tmp_path, "https://docs.example.com/")
        assert table.count(">—<") == 2

    def test_token_estimate_column_header(self, tmp_path):
        """Table should include 'Token Estimate' column."""
        table = self._make_table(tmp_path, "https://docs.example.com/")
        assert "Token Estimate" in table


def _write_bundle(path, token_estimate):
    """Write a minimal category bundle file with the given token_estimate in front matter."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntoken_estimate: {token_estimate}\n---\n\nContent.\n", encoding="utf-8")

# ===========================================================================
# _patch_ai_resources_page — HTML injection
# ===========================================================================

class TestPatchAiResourcesPage:
    """Tests that _patch_ai_resources_page injects the table into the built HTML."""

    def _write_html(self, path, content):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def _base_html(self):
        return (
            '<html><body>'
            '<!-- ai-resources-aggregate-table -->'
            '<!-- ai-category-basics-table -->'
            '</body></html>'
        )

    def test_replaces_placeholder(self, tmp_path):
        """The placeholder divs should be replaced with HTML tables."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/")
        plugin._ensure_config_loaded(config)

        site_dir = tmp_path / "site"
        html_path = site_dir / "ai-resources" / "index.html"
        self._write_html(html_path, self._base_html())

        plugin._patch_ai_resources_page(site_dir, config)

        result = html_path.read_text(encoding="utf-8")
        assert '<!-- ai-resources-aggregate-table -->' not in result
        assert '<!-- ai-category-basics-table -->' not in result
        assert "<table>" in result
        assert "Token Estimate" in result

    def test_reads_category_tokens_from_bundle_front_matter(self, tmp_path):
        """Category token estimates should be read from bundle and light file front matter."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/")
        plugin._ensure_config_loaded(config)

        site_dir = tmp_path / "site"
        self._write_html(site_dir / "ai-resources" / "index.html", self._base_html())
        _write_bundle(site_dir / "ai" / "categories" / "basics.md", token_estimate=9999)
        _write_bundle(site_dir / "ai" / "categories" / "basics-light.md", token_estimate=1111)

        plugin._patch_ai_resources_page(site_dir, config)

        result = (site_dir / "ai-resources" / "index.html").read_text(encoding="utf-8")
        assert "9,999" in result
        assert "1,111" in result

    def test_missing_html_file_warns(self, tmp_path, caplog):
        """A missing HTML file should log a warning and not raise."""
        import logging
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/")
        plugin._ensure_config_loaded(config)
        site_dir = tmp_path / "site"
        site_dir.mkdir()

        with caplog.at_level(logging.WARNING):
            plugin._patch_ai_resources_page(site_dir, config)

        assert any("not found" in r.message for r in caplog.records)

    def test_missing_placeholder_warns(self, tmp_path, caplog):
        """HTML without the aggregate placeholder should log a warning and leave the file unchanged."""
        import logging
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/")
        plugin._ensure_config_loaded(config)

        site_dir = tmp_path / "site"
        html_path = site_dir / "ai-resources" / "index.html"
        original = "<html><body><p>No placeholder here.</p></body></html>"
        self._write_html(html_path, original)

        with caplog.at_level(logging.WARNING):
            plugin._patch_ai_resources_page(site_dir, config)

        assert html_path.read_text(encoding="utf-8") == original
        assert any("placeholder not found" in r.message for r in caplog.records)

    def test_non_directory_urls(self, tmp_path):
        """With use_directory_urls=False the method should target ai-resources.html."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.example.com/")
        config["use_directory_urls"] = False
        plugin._ensure_config_loaded(config)

        site_dir = tmp_path / "site"
        html_path = site_dir / "ai-resources.html"
        self._write_html(html_path, self._base_html())

        plugin._patch_ai_resources_page(site_dir, config)

        result = html_path.read_text(encoding="utf-8")
        assert "<table>" in result


# ===========================================================================
# build_category_light
# ===========================================================================

class TestBuildCategoryLight:
    """Tests for build_category_light — per-category lightweight index files."""

    def _make_plugin_with_config(self, tmp_path):
        plugin = _make_plugin()
        llms_config = {
            "project": {"name": "TestProject"},
            "content": {
                "categories_info": {
                    "basics": {"name": "Basics", "description": "Basic docs."},
                },
                "exclusions": {"skip_basenames": [], "skip_paths": []},
            },
            "outputs": {"public_root": "/ai/"},
        }
        config_file = tmp_path / "llms_config.json"
        config_file.write_text(json.dumps(llms_config), encoding="utf-8")
        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("", encoding="utf-8")
        plugin._ensure_config_loaded({"config_file_path": str(mkdocs_yml), "site_url": ""})
        return plugin

    def _make_pages(self):
        return [
            {
                "slug": "intro",
                "title": "Introduction",
                "categories": ["basics"],
                "url": "https://example.com/intro/",
                "raw_md_url": "https://example.com/intro.md",
                "preview": "A short intro.",
                "outline": [
                    {"title": "Overview", "anchor": "overview", "depth": 2},
                    {"title": "Details", "anchor": "details", "depth": 2},
                ],
                "word_count": 50,
                "token_estimate": 80,
                "version_hash": "sha256:abc",
                "last_updated": "2025-01-01T00:00:00+00:00",
                "body": "## Overview\n\nSome text.\n\n## Details\n\nMore text.",
            },
        ]

    def test_file_is_generated_for_category(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light(self._make_pages(), ai_root)
        assert (ai_root / "categories" / "basics-light.md").exists()

    def test_front_matter_fields(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light(self._make_pages(), ai_root, build_timestamp="2025-06-01T00:00:00+00:00")
        content = (ai_root / "categories" / "basics-light.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(content.split("---")[1])
        assert fm["category"] == "Basics"
        assert fm["description"] == "Basic docs."
        assert fm["page_count"] == 1
        assert isinstance(fm["token_estimate"], int)
        assert fm["token_estimate"] > 0
        assert fm["updated"] == "2025-06-01T00:00:00+00:00"

    def test_front_matter_omits_updated_when_no_timestamp(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light(self._make_pages(), ai_root)
        content = (ai_root / "categories" / "basics-light.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(content.split("---")[1])
        assert "updated" not in fm

    def test_section_headings_and_anchors_emitted(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light(self._make_pages(), ai_root)
        content = (ai_root / "categories" / "basics-light.md").read_text(encoding="utf-8")
        assert "Overview" in content
        assert "`#overview`" in content
        assert "Details" in content
        assert "`#details`" in content

    def test_page_title_and_url_emitted(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light(self._make_pages(), ai_root)
        content = (ai_root / "categories" / "basics-light.md").read_text(encoding="utf-8")
        assert "## Introduction" in content
        assert "https://example.com/intro.md" in content

    def test_no_file_for_empty_pages(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        plugin.build_category_light([], ai_root)
        assert not (ai_root / "categories" / "basics-light.md").exists()

    def test_page_count_zero_for_unmatched_category(self, tmp_path):
        plugin = self._make_plugin_with_config(tmp_path)
        ai_root = tmp_path / "ai"
        pages = [{"slug": "x", "title": "X", "categories": ["other"], "body": "hello",
                  "raw_md_url": "", "preview": "", "outline": [], "token_estimate": 5}]
        plugin.build_category_light(pages, ai_root)
        content = (ai_root / "categories" / "basics-light.md").read_text(encoding="utf-8")
        fm = yaml.safe_load(content.split("---")[1])
        assert fm["page_count"] == 0


# ===========================================================================
# ai_page_actions_anchor
# ===========================================================================

class TestAiPageActionsAnchor:
    """Tests for the ai_page_actions_anchor config option."""

    def _make_plugin(self, anchor_class=""):
        plugin = AIDocsPlugin()
        plugin.config = {
            "llms_config": "llms_config.json",
            "ai_resources_page": True,
            "ai_page_actions": True,
            "ai_page_actions_anchor": anchor_class,
        }
        plugin._config_loaded = True
        return plugin

    def _make_page(self, url="guide/", src_path="guide.md"):
        page = MagicMock()
        page.is_homepage = False
        page.file.src_path = src_path
        page.meta = {}
        page.url = url
        return page

    def test_anchor_mode_injects_into_target_element(self):
        """Widget is appended into the element with the configured class."""
        plugin = self._make_plugin(anchor_class="page-actions-slot")
        page = self._make_page()
        output = (
            '<div class="md-content">'
            '<h1>Guide</h1>'
            '<div class="page-actions-slot"></div>'
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")
        slot = soup.select_one(".page-actions-slot")
        assert slot is not None
        assert slot.find(attrs={"data-url": True}) is not None

    def test_anchor_mode_does_not_wrap_h1(self):
        """When anchor class is set, the H1 is not wrapped in h1-ai-actions-wrapper."""
        plugin = self._make_plugin(anchor_class="page-actions-slot")
        page = self._make_page()
        output = (
            '<div class="md-content">'
            '<h1>Guide</h1>'
            '<div class="page-actions-slot"></div>'
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "h1-ai-actions-wrapper" not in result

    def test_anchor_mode_injects_into_all_matching_elements(self):
        """Widget is appended into every element with the anchor class."""
        plugin = self._make_plugin(anchor_class="action-slot")
        page = self._make_page()
        output = (
            '<div class="md-content">'
            '<div class="action-slot" id="a"></div>'
            '<div class="action-slot" id="b"></div>'
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")
        slots = soup.select(".action-slot")
        assert len(slots) == 2
        for slot in slots:
            assert slot.find(attrs={"data-url": True}) is not None

    def test_anchor_mode_no_match_returns_output_unchanged(self):
        """When the anchor class is not found, the page is returned unchanged."""
        plugin = self._make_plugin(anchor_class="nonexistent-slot")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert result == output

    def test_anchor_mode_uses_page_route_for_md_path(self):
        """The widget data-url is derived from the page route, not a toggle variant."""
        plugin = self._make_plugin(anchor_class="slot")
        page = self._make_page(url="api/reference/", src_path="api/reference.md")
        output = (
            '<div class="md-content">'
            '<div class="slot"></div>'
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")
        data_url = soup.find(attrs={"data-url": True})["data-url"]
        assert data_url == "/api/reference.md"

    def test_empty_anchor_falls_back_to_h1_wrapping(self):
        """When ai_page_actions_anchor is empty, the default H1-wrapping behavior runs."""
        plugin = self._make_plugin(anchor_class="")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1><p>Content</p></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "h1-ai-actions-wrapper" in result

    # --- Toggle page + anchor_class tests ---

    def test_toggle_anchor_injects_widget_per_variant_with_data_filename(self):
        """Each variant's anchor element gets a widget whose data-url matches data-filename."""
        plugin = self._make_plugin(anchor_class="actions-slot")
        page = self._make_page(url="runtime/", src_path="runtime.md")
        output = (
            '<div class="md-content">'
            '<div class="toggle-container">'
            '<button class="toggle-btn" data-variant="stable" data-filename="runtime-stable"></button>'
            '<button class="toggle-btn" data-variant="latest" data-filename="runtime-latest"></button>'
            '<div class="actions-slot" data-variant="stable"></div>'
            '<div class="actions-slot" data-variant="latest"></div>'
            "</div>"
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")

        stable_slot = soup.select_one('.actions-slot[data-variant="stable"]')
        latest_slot = soup.select_one('.actions-slot[data-variant="latest"]')

        assert stable_slot is not None
        assert latest_slot is not None

        stable_widget = stable_slot.find(attrs={"data-url": True})
        latest_widget = latest_slot.find(attrs={"data-url": True})

        assert stable_widget is not None, "stable slot should have a widget"
        assert latest_widget is not None, "latest slot should have a widget"
        assert stable_widget["data-url"] == "/runtime-stable.md"
        assert latest_widget["data-url"] == "/runtime-latest.md"

    def test_toggle_anchor_falls_back_to_route_when_no_data_filename(self):
        """When data-filename is absent, the widget data-url falls back to the page route."""
        plugin = self._make_plugin(anchor_class="actions-slot")
        page = self._make_page(url="guide/", src_path="guide.md")
        output = (
            '<div class="md-content">'
            '<div class="toggle-container">'
            '<button class="toggle-btn" data-variant="v1"></button>'
            '<div class="actions-slot" data-variant="v1"></div>'
            "</div>"
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")
        widget = soup.select_one('.actions-slot[data-variant="v1"]').find(attrs={"data-url": True})
        assert widget is not None
        assert widget["data-url"] == "/guide.md"

    def test_toggle_anchor_no_match_skips_injection(self):
        """When the anchor class is not found for a variant, no widget is injected."""
        plugin = self._make_plugin(anchor_class="actions-slot")
        page = self._make_page(url="guide/", src_path="guide.md")
        output = (
            '<div class="md-content">'
            '<div class="toggle-container">'
            '<button class="toggle-btn" data-variant="v1" data-filename="guide-v1"></button>'
            # No matching .actions-slot[data-variant="v1"] present
            '<div class="other-class" data-variant="v1"></div>'
            "</div>"
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")
        assert soup.find(attrs={"data-url": True}) is None

    def test_toggle_anchor_does_not_inject_into_other_variants_slot(self):
        """Each variant's widget only appears in its own anchor element, not another variant's."""
        plugin = self._make_plugin(anchor_class="slot")
        page = self._make_page(url="docs/", src_path="docs.md")
        output = (
            '<div class="md-content">'
            '<div class="toggle-container">'
            '<button class="toggle-btn" data-variant="a" data-filename="docs-a"></button>'
            '<button class="toggle-btn" data-variant="b" data-filename="docs-b"></button>'
            '<div class="slot" data-variant="a"></div>'
            '<div class="slot" data-variant="b"></div>'
            "</div>"
            "</div>"
        )
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        soup = BeautifulSoup(result, "html.parser")

        slot_a = soup.select_one('.slot[data-variant="a"]')
        slot_b = soup.select_one('.slot[data-variant="b"]')

        assert slot_a.find(attrs={"data-url": "/docs-a.md"}) is not None
        assert slot_b.find(attrs={"data-url": "/docs-b.md"}) is not None
        # Ensure cross-contamination didn't happen
        assert slot_a.find(attrs={"data-url": "/docs-b.md"}) is None
        assert slot_b.find(attrs={"data-url": "/docs-a.md"}) is None


# ===========================================================================
# ai_page_actions_style
# ===========================================================================

class TestAiPageActionsStyle:
    """Tests for the ai_page_actions_style and ai_page_actions_dropdown_label options."""

    def _make_plugin(self, style="split", dropdown_label="Markdown for LLMs"):
        plugin = AIDocsPlugin()
        plugin.config = {
            "llms_config": "llms_config.json",
            "ai_resources_page": True,
            "ai_page_actions": True,
            "ai_page_actions_anchor": "",
            "ai_page_actions_style": style,
            "ai_page_actions_dropdown_label": dropdown_label,
        }
        plugin._config_loaded = True
        return plugin

    def _make_page(self, url="guide/", src_path="guide.md"):
        page = MagicMock()
        page.is_homepage = False
        page.file.src_path = src_path
        page.meta = {}
        page.url = url
        return page

    def test_split_style_renders_copy_button(self):
        """Split style produces the primary copy button outside the dropdown menu."""
        plugin = self._make_plugin(style="split")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "ai-file-actions-copy" in result

    def test_split_style_no_dropdown_modifier(self):
        """Split style does not apply the --dropdown container modifier."""
        plugin = self._make_plugin(style="split")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "ai-file-actions-container--dropdown" not in result

    def test_dropdown_style_no_copy_button(self):
        """Dropdown style does not render a standalone copy button."""
        plugin = self._make_plugin(style="dropdown")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "ai-file-actions-copy" not in result

    def test_dropdown_style_container_modifier(self):
        """Dropdown style applies the --dropdown modifier to the container."""
        plugin = self._make_plugin(style="dropdown")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "ai-file-actions-container--dropdown" in result

    def test_dropdown_style_trigger_label(self):
        """Dropdown style uses the configured dropdown_label on the trigger."""
        plugin = self._make_plugin(style="dropdown", dropdown_label="AI Tools")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "AI Tools" in result

    def test_dropdown_style_default_label(self):
        """Dropdown style uses 'Markdown for LLMs' as the default trigger label."""
        plugin = self._make_plugin(style="dropdown")
        page = self._make_page()
        output = '<div class="md-content"><h1>Guide</h1></div>'
        result = plugin.on_post_page(output, page=page, config={"site_url": ""})
        assert "Markdown for LLMs" in result
