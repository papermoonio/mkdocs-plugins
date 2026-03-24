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
# on_page_markdown — ai_resources_page (ported from test_ai_resources_page)
# ===========================================================================

class TestAiResourcesPageSubpath:
    """Tests that artifact URLs in the AI resources page include the site subpath."""

    def test_root_site_url(self, tmp_path):
        """Root deploy should produce URLs without a prefix."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://docs.polkadot.com/")
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "/ai/site-index.json" in result
        assert "/ai/llms-full.jsonl" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result
        assert '"/docs/' not in result

    def test_subpath_site_url(self, tmp_path):
        """Subpath deploy should prepend /docs/ to all artifact URLs."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="https://wormhole.com/docs/")
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "/docs/ai/site-index.json" in result
        assert "/docs/ai/llms-full.jsonl" in result
        assert "/docs/ai/categories/basics.md" in result
        assert "/docs/llms.txt" in result

    def test_empty_site_url(self, tmp_path):
        """Empty site_url should produce URLs without a prefix."""
        plugin = _make_plugin()
        config = _make_mkdocs_config(tmp_path, site_url="")
        page = _make_page(src_path="ai-resources.md")
        result = plugin.on_page_markdown("", page=page, config=config, files=[])
        assert "/ai/site-index.json" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result

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
