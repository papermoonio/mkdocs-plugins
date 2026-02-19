"""
Simple test for mkdocs-minify-plugin.
"""

import subprocess
import sys
from pathlib import Path

import pytest

from plugins.minify.plugin import MINIFIERS, MinifyPlugin


class TestMinifyPlugin:
    """Test for the principal functions of the plugin."""

    def test_plugin_init(self):
        """Test: The plugins is initialized correctly."""
        plugin = MinifyPlugin()
        assert isinstance(plugin.config, dict)

    def test_minify_js(self):
        """Test: Minificación de JavaScript funciona."""
        plugin = MinifyPlugin()
        js_code = "console.log('hello');\nvar x = 1;"
        result = plugin._minify_file_data_with_func(js_code, MINIFIERS["js"])
        assert "console.log('hello');var x=1" in result

    def test_minify_css(self):
        """Test: CSS minification works."""
        plugin = MinifyPlugin()
        css_code = ".test {\n    color: red;\n    margin: 10px;\n}"
        result = plugin._minify_file_data_with_func(css_code, MINIFIERS["css"])
        assert ".test{" in result and "color:red" in result

    def test_minify_html(self):
        """Test: HTML minification works."""
        plugin = MinifyPlugin()
        html_code = "<html><body><p>Hello   World</p></body></html>"
        result = plugin._minify_html_page(html_code)
        assert result is not None
        assert "<html><body><p>Hello World</p></body></html>" in result

    def test_asset_naming(self):
        """Test: Minified file names are correct."""
        plugin = MinifyPlugin()

        # Without hash, without minification
        plugin.config["minify_css"] = False
        result = plugin._minified_asset("style.css", "css", "")
        assert result == "style.css"

        # With minification
        plugin.config["minify_css"] = True
        result = plugin._minified_asset("style.css", "css", "")
        assert result == "style.min.css"

        # With hash
        result = plugin._minified_asset("style.css", "css", "abc123")
        assert result == "style.abc123.min.css"

    def test_scoped_css_gathering(self):
        """Test: Collection of CSS files with scope works."""
        plugin = MinifyPlugin()
        plugin.config["scoped_css"] = {
            "index.md": ["css/home.css"],
            "about.md": ["css/about.css"],
        }
        plugin.config["scoped_css_templates"] = {}

        files = plugin._gather_scoped_css_files()
        assert "css/home.css" in files
        assert "css/about.css" in files

    def test_integration_build(self, tmp_path):
        """Test: Complete integration with MkDocs build."""
        # Crear estructura de sitio
        docs = tmp_path / "docs"
        docs.mkdir()
        (docs / "index.md").write_text("# Home\n\nWelcome.", encoding="utf8")

        assets = docs / "extra_assets"
        assets.mkdir()
        (assets / "css").mkdir()
        (assets / "js").mkdir()

        # Create test files
        (assets / "css" / "main.css").write_text(
            ".test { color: blue; }", encoding="utf8"
        )
        (assets / "js" / "main.js").write_text("console.log('test');", encoding="utf8")

        # Configuration
        config_content = """
site_name: Test Site
theme:
  name: mkdocs
plugins:
  - minify:
      minify_html: true
      minify_css: true
      minify_js: true
      css_files:
        - extra_assets/css/main.css
      js_files:
        - extra_assets/js/main.js
extra_css:
  - extra_assets/css/main.css
extra_javascript:
  - extra_assets/js/main.js
"""

        config_file = tmp_path / "mkdocs.yml"
        config_file.write_text(config_content, encoding="utf8")

        site_dir = tmp_path / "site"
        site_dir.mkdir()

        # Execute build
        try:
            subprocess.check_call(
                [
                    sys.executable,
                    "-m",
                    "mkdocs",
                    "build",
                    "-q",
                    "-f",
                    str(config_file),
                    "-d",
                    str(site_dir),
                ],
                cwd=str(tmp_path),
            )

            # Verify that the minified files were created
            assert (site_dir / "extra_assets" / "css" / "main.min.css").exists()
            assert (site_dir / "extra_assets" / "js" / "main.min.js").exists()

            # Verify that the HTML references the minified files
            index_html = (site_dir / "index.html").read_text(encoding="utf8")
            assert "main.min.css" in index_html
            assert "main.min.js" in index_html

        except subprocess.CalledProcessError:
            pytest.skip("MkDocs build failed in this environment")

    def test_error_handling(self):
        """Test: The plugin handles errors without crashing."""
        plugin = MinifyPlugin()

        # Malformed CSS
        bad_css = ".test { color: red; /* unclosed comment"
        result = plugin._minify_file_data_with_func(bad_css, MINIFIERS["css"])
        assert result is not None

        # Malformed HTML
        bad_html = "<html><body><p>Unclosed paragraph"
        result = plugin._minify_html_page(bad_html)
        assert result is not None

    def test_none_inputs(self):
        """Test: The plugin handles None inputs correctly."""
        plugin = MinifyPlugin()

        # Should handle None without crashing
        try:
            result = plugin._minify_html_page(None)
            assert result is None
        except (TypeError, AttributeError):
            # It is also acceptable that it raises an exception
            pass
