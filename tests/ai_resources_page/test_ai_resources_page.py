import json
from pathlib import Path
from unittest.mock import MagicMock

from plugins.ai_resources_page.plugin import AiResourcesPagePlugin


def _make_config(tmp_path, site_url="https://docs.example.com/"):
    """Create a minimal llms_config.json and return a mock MkDocs config."""
    llms_config = {
        "project": {"name": "TestProject"},
        "content": {
            "categories_info": {
                "basics": {
                    "name": "Basics",
                    "description": "Basic docs.",
                }
            }
        },
        "outputs": {"public_root": "/ai/"},
    }
    config_file = tmp_path / "llms_config.json"
    config_file.write_text(json.dumps(llms_config), encoding="utf-8")

    # MkDocs config mock
    mkdocs_yml = tmp_path / "mkdocs.yml"
    mkdocs_yml.write_text("", encoding="utf-8")

    config = {
        "config_file_path": str(mkdocs_yml),
        "site_url": site_url,
    }
    return config


class TestAiResourcesPageSubpath:
    """Tests that artifact URLs include the site subpath."""

    def test_root_site_url(self, tmp_path):
        """Root deploy should produce URLs without a prefix."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://docs.polkadot.com/")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/ai/site-index.json" in result
        assert "/ai/llms-full.jsonl" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result
        # Should NOT have a double path like /docs/ai/
        assert '"/docs/' not in result

    def test_subpath_site_url(self, tmp_path):
        """Subpath deploy should prepend /docs/ to all URLs."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://wormhole.com/docs/")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/docs/ai/site-index.json" in result
        assert "/docs/ai/llms-full.jsonl" in result
        assert "/docs/ai/categories/basics.md" in result
        assert "/docs/llms.txt" in result

    def test_empty_site_url(self, tmp_path):
        """Empty site_url should produce URLs without a prefix."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="")
        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "/ai/site-index.json" in result
        assert "/ai/categories/basics.md" in result
        assert "/llms.txt" in result


class TestFormatTokenCount:
    """Tests for the token count formatting helper."""

    def test_millions(self):
        assert AiResourcesPagePlugin.format_token_count(1_500_000) == "~1.5M tokens"

    def test_millions_even(self):
        assert AiResourcesPagePlugin.format_token_count(2_000_000) == "~2M tokens"

    def test_thousands(self):
        assert AiResourcesPagePlugin.format_token_count(45_200) == "~45.2K tokens"

    def test_thousands_even(self):
        assert AiResourcesPagePlugin.format_token_count(8_000) == "~8K tokens"

    def test_small_count(self):
        assert AiResourcesPagePlugin.format_token_count(500) == "~500 tokens"


class TestTokenPlaceholdersInMarkdown:
    """Tests that on_page_markdown inserts token estimate placeholders."""

    def test_placeholders_present_in_markdown(self, tmp_path):
        """Each file cell should contain a token estimate placeholder comment."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://docs.example.com/")

        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "<!-- token-estimate:llms.txt -->" in result
        assert "<!-- token-estimate:site-index.json -->" in result
        assert "<!-- token-estimate:llms-full.jsonl -->" in result
        assert "<!-- token-estimate:categories/basics.md -->" in result

    def test_token_estimate_bullet_in_how_to_use(self, tmp_path):
        """The How to Use section includes the token estimate explanation."""
        plugin = AiResourcesPagePlugin()
        config = _make_config(tmp_path, site_url="https://docs.example.com/")

        page = MagicMock()
        page.file.src_path = "ai-resources.md"

        result = plugin.on_page_markdown("", page, config, [])

        assert "**Token estimates**" in result
        assert "tiktoken" in result


class TestTokenCountPostBuild:
    """Tests that on_post_build replaces placeholders with real token counts."""

    def _build_html(self, tmp_path):
        """Simulate a built ai-resources page with placeholders."""
        site_dir = tmp_path / "site"
        page_dir = site_dir / "ai-resources"
        page_dir.mkdir(parents=True)
        html = (
            "<html><body>"
            '<code>llms.txt</code><!-- token-estimate:llms.txt -->'
            '<code>site-index.json</code><!-- token-estimate:site-index.json -->'
            '<code>llms-full.jsonl</code><!-- token-estimate:llms-full.jsonl -->'
            '<code>basics.md</code><!-- token-estimate:categories/basics.md -->'
            "</body></html>"
        )
        (page_dir / "index.html").write_text(html, encoding="utf-8")
        return site_dir

    def test_replaces_placeholders_with_token_counts(self, tmp_path):
        """on_post_build should replace placeholder comments with styled spans."""
        plugin = AiResourcesPagePlugin()
        site_dir = self._build_html(tmp_path)

        # Write the token manifest
        token_counts = {
            "llms.txt": 5200,
            "site-index.json": 128000,
            "llms-full.jsonl": 1500000,
            "categories/basics.md": 52000,
        }
        (tmp_path / "ai-resources-token-count.json").write_text(
            json.dumps(token_counts), encoding="utf-8"
        )

        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("", encoding="utf-8")
        config = {
            "config_file_path": str(mkdocs_yml),
            "site_dir": str(site_dir),
        }

        plugin.on_post_build(config)

        result = (site_dir / "ai-resources" / "index.html").read_text()
        assert "~5.2K tokens" in result
        assert "~128K tokens" in result
        assert "~1.5M tokens" in result
        assert "~52K tokens" in result
        assert "<!-- token-estimate:" not in result

    def test_removes_placeholders_when_no_manifest(self, tmp_path):
        """Placeholders are cleaned up even when no manifest exists."""
        plugin = AiResourcesPagePlugin()
        site_dir = self._build_html(tmp_path)

        mkdocs_yml = tmp_path / "mkdocs.yml"
        mkdocs_yml.write_text("", encoding="utf-8")
        config = {
            "config_file_path": str(mkdocs_yml),
            "site_dir": str(site_dir),
        }

        plugin.on_post_build(config)

        result = (site_dir / "ai-resources" / "index.html").read_text()
        assert "<!-- token-estimate:" not in result
        assert "tokens" not in result
