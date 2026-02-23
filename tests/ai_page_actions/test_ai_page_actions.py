from unittest.mock import MagicMock

from bs4 import BeautifulSoup

from helper_lib.ai_file_utils.ai_file_utils import AIFileUtils
from plugins.ai_page_actions.plugin import AiPageActionsPlugin


class TestBuildSlug:
    """Tests for the static build_slug helper on AIFileUtils."""

    def test_simple_path(self):
        assert AIFileUtils.build_slug("develop/toolkit/") == "develop-toolkit"

    def test_root_path(self):
        assert AIFileUtils.build_slug("/") == "index"

    def test_empty_string(self):
        assert AIFileUtils.build_slug("") == "index"

    def test_deep_path(self):
        assert AIFileUtils.build_slug("a/b/c/d/") == "a-b-c-d"


class TestBuildToggleSlug:
    """Tests for the static build_toggle_slug helper on AIFileUtils."""

    def test_canonical_variant(self):
        assert AIFileUtils.build_toggle_slug("develop/toolkit/", "") == "develop-toolkit"

    def test_non_canonical_variant(self):
        assert AIFileUtils.build_toggle_slug("develop/toolkit/", "python") == "develop-python"

    def test_single_segment_variant(self):
        assert AIFileUtils.build_toggle_slug("toolkit/", "rust") == "rust"


class TestWrapH1SubpathHandling:
    """Tests that _wrap_h1 correctly prefixes the URL with the site subpath."""

    def setup_method(self):
        self.plugin = AiPageActionsPlugin()

    def _make_soup_with_h1(self):
        html = '<div class="md-content"><h1>Hello</h1></div>'
        soup = BeautifulSoup(html, "html.parser")
        h1 = soup.find("h1")
        return soup, h1

    def test_root_site_url(self):
        """site_url at root should produce /ai/pages/slug.md"""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "my-page", soup, site_url="https://docs.polkadot.com/")
        data_url = soup.find(attrs={"data-url": True})["data-url"]
        assert data_url == "/ai/pages/my-page.md"

    def test_subpath_site_url(self):
        """site_url with subpath should produce /docs/ai/pages/slug.md"""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "my-page", soup, site_url="https://wormhole.com/docs/")
        data_url = soup.find(attrs={"data-url": True})["data-url"]
        assert data_url == "/docs/ai/pages/my-page.md"

    def test_no_site_url(self):
        """Empty site_url should produce /ai/pages/slug.md"""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "my-page", soup, site_url="")
        data_url = soup.find(attrs={"data-url": True})["data-url"]
        assert data_url == "/ai/pages/my-page.md"

    def test_deep_subpath(self):
        """site_url with deep subpath should produce correct prefix."""
        soup, h1 = self._make_soup_with_h1()
        self.plugin._wrap_h1(h1, "my-page", soup, site_url="https://example.com/a/b/c/")
        data_url = soup.find(attrs={"data-url": True})["data-url"]
        assert data_url == "/a/b/c/ai/pages/my-page.md"
