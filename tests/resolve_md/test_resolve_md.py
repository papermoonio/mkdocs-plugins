import os
import tempfile

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
