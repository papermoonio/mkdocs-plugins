import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml

from plugins.resolve_md.plugin import ResolveMDPlugin


class TestGetAllMarkdownFiles:
    """Tests for file discovery with dot-directory and skip filtering."""

    def _create_tree(self, base, structure):
        """Create a directory tree from a dict.

        Keys ending with '/' are directories; others are files.
        """
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
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], [])
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
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "page.md" in basenames
            assert ".hidden.md" not in basenames
            assert ".secret.md" not in basenames

    def test_skips_nested_dot_directories(self):
        """Dot-directories nested under normal dirs are also excluded."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "docs": {
                    "page.md": "",
                    ".hidden": {"secret.md": ""},
                },
            })
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "page.md" in basenames
            assert "secret.md" not in basenames

    def test_skip_paths_still_works(self):
        """Manual skip_paths continue to work alongside dot-directory skipping."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "guide.md": "",
                "venv": {"pkg.md": ""},
            })
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], ["venv"])
            basenames = [os.path.basename(f) for f in results]
            assert "guide.md" in basenames
            assert "pkg.md" not in basenames

    def test_skip_basenames_still_works(self):
        """Manual skip_basenames continue to work alongside dot-directory skipping."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "guide.md": "",
                "README.md": "",
            })
            results = ResolveMDPlugin.get_all_markdown_files(tmp, ["README.md"], [])
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
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            rel_paths = [os.path.relpath(f, tmp) for f in results]
            # Root index.md is excluded
            assert os.path.join(tmp, "index.md") not in results
            # Nested index.md is still included
            assert os.path.join("subdir", "index.md") in rel_paths
            assert "guide.md" in basenames

    def test_skip_basenames_index_skips_all_index_files(self):
        """Adding index.md to skip_basenames excludes all index.md files site-wide."""
        with tempfile.TemporaryDirectory() as tmp:
            self._create_tree(tmp, {
                "index.md": "",
                "guide.md": "",
                "subdir": {"index.md": "", "page.md": ""},
            })
            results = ResolveMDPlugin.get_all_markdown_files(tmp, ["index.md"], [])
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
            results = ResolveMDPlugin.get_all_markdown_files(tmp, [], [])
            basenames = [os.path.basename(f) for f in results]
            assert "page.md" in basenames
            assert "component.mdx" in basenames
            assert "style.css" not in basenames


class TestGetGitLastUpdated:
    """Tests for the git timestamp helper."""

    def test_returns_iso_timestamp_for_tracked_file(self):
        """A file tracked by git returns an ISO-8601 timestamp string."""
        # Use this test file itself — it's tracked in the repo
        ts = ResolveMDPlugin.get_git_last_updated(__file__)
        assert ts, "Expected a non-empty timestamp"
        assert "T" in ts, "Expected ISO-8601 format with a T separator"

    def test_handles_z_suffix_on_python310(self):
        """Timestamps ending with 'Z' are normalised so Python 3.10 can parse them."""
        mock_result = type("R", (), {"stdout": "2026-03-09T14:16:33Z", "returncode": 0})()
        with patch("plugins.resolve_md.plugin.subprocess.run", return_value=mock_result):
            ts = ResolveMDPlugin.get_git_last_updated(__file__)
        assert ts == "2026-03-09T14:16:33+00:00"

    def test_falls_back_for_untracked_file(self):
        """An untracked temp file falls back to filesystem mtime."""
        with tempfile.NamedTemporaryFile(suffix=".md", delete=False) as f:
            f.write(b"hello")
            tmp_path = f.name
        try:
            ts = ResolveMDPlugin.get_git_last_updated(tmp_path)
            assert ts, "Expected a non-empty timestamp"
            assert "T" in ts, "Expected ISO-8601 format"
        finally:
            os.unlink(tmp_path)


class TestWriteAiPage:
    """Tests that write_ai_page includes version_hash and last_updated."""

    def test_front_matter_contains_versioning_fields(self):
        plugin = ResolveMDPlugin()
        with tempfile.TemporaryDirectory() as tmp:
            pages_dir = Path(tmp) / "pages"
            header = {
                "title": "Test Page",
                "url": "https://example.com/test/",
                "word_count": 100,
                "token_estimate": 150,
                "version_hash": "sha256:abc123",
                "last_updated": "2025-01-15T10:00:00+00:00",
            }
            out_path = pages_dir / "test-page.md"
            plugin.write_ai_page(out_path, header, "# Hello\n\nWorld.")
            content = out_path.read_text()
            fm_match = content.split("---")[1]
            fm = yaml.safe_load(fm_match)
            assert fm["version_hash"] == "sha256:abc123"
            assert fm["last_updated"] == "2025-01-15T10:00:00+00:00"


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
        plugin = ResolveMDPlugin()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "bundle.md"
            plugin.write_category_bundle(
                out_path, "Test", False, [], self._make_pages(),
                build_timestamp="2025-06-01T00:00:00+00:00",
            )
            content = out_path.read_text()
            fm = yaml.safe_load(content.split("---")[1])
            assert fm["build_timestamp"] == "2025-06-01T00:00:00+00:00"
            assert fm["version_hash"].startswith("sha256:")

    def test_bundle_page_entry_has_last_updated_and_hash(self):
        plugin = ResolveMDPlugin()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "bundle.md"
            plugin.write_category_bundle(
                out_path, "Test", False, [], self._make_pages(),
            )
            content = out_path.read_text()
            assert "- Last Updated: 2025-01-10T08:00:00+00:00" in content
            assert "- Version Hash: sha256:aaa" in content


class TestBuildSiteIndex:
    """Tests that site-index.json includes versioning metadata."""

    def test_site_index_has_top_level_build_metadata(self):
        plugin = ResolveMDPlugin()
        plugin.llms_config = {"outputs": {"files": {}}}
        pages = [
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
        with tempfile.TemporaryDirectory() as tmp:
            ai_root = Path(tmp)
            plugin.build_site_index(pages, ai_root, "2025-06-01T00:00:00+00:00")
            index = json.loads((ai_root / "site-index.json").read_text())
            assert index["build_timestamp"] == "2025-06-01T00:00:00+00:00"
            assert index["version_hash"].startswith("sha256:")
            assert index["page_count"] == 1
            entry = index["pages"][0]
            assert entry["version_hash"] == "sha256:abc"
            assert entry["last_updated"] == "2025-03-01T12:00:00+00:00"

    def test_jsonl_sections_have_page_versioning(self):
        plugin = ResolveMDPlugin()
        plugin.llms_config = {"outputs": {"files": {}}}
        pages = [
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
        with tempfile.TemporaryDirectory() as tmp:
            ai_root = Path(tmp)
            plugin.build_site_index(pages, ai_root, "2025-06-01T00:00:00+00:00")
            jsonl_path = ai_root / "llms-full.jsonl"
            lines = jsonl_path.read_text().strip().splitlines()
            assert len(lines) >= 1
            section = json.loads(lines[0])
            assert section["page_version_hash"] == "sha256:abc"
            assert section["last_updated"] == "2025-03-01T12:00:00+00:00"


class TestFormatLlmsMetadataSection:
    """Tests that llms.txt metadata includes build_timestamp and version_hash."""

    def test_metadata_section_includes_versioning(self):
        pages = [{"categories": ["basics"], "body": "hello world"}]
        section = ResolveMDPlugin.format_llms_metadata_section(
            pages, "2025-06-01T00:00:00+00:00"
        )
        assert "Build Timestamp: 2025-06-01T00:00:00+00:00" in section
        assert "Version Hash: sha256:" in section
