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


class TestIsPageExcluded:
    """Tests for the config-driven page exclusion logic."""

    def setup_method(self):
        self.utils = AIFileUtils()

    def test_dot_directory_excluded(self):
        """Pages inside dot-directories are always excluded."""
        assert self.utils.is_page_excluded(".snippets/nav.md", {}) is True

    def test_nested_dot_directory_excluded(self):
        """Pages nested under a dot-directory are excluded."""
        assert self.utils.is_page_excluded("docs/.hidden/page.md", {}) is True

    def test_skip_basenames_match(self):
        """Pages whose filename matches a skip_basenames entry are excluded."""
        assert self.utils.is_page_excluded(
            "develop/README.md", {}, skip_basenames=["README.md"]
        ) is True

    def test_skip_basenames_no_match(self):
        """Pages whose filename doesn't match skip_basenames are not excluded."""
        assert self.utils.is_page_excluded(
            "develop/guide.md", {}, skip_basenames=["README.md"]
        ) is False

    def test_skip_paths_substring_match(self):
        """Pages whose path contains a skip_paths entry are excluded."""
        assert self.utils.is_page_excluded(
            "node_modules/pkg/README.md", {}, skip_paths=["node_modules"]
        ) is True

    def test_skip_paths_no_match(self):
        """Pages whose path doesn't contain any skip_paths entry are not excluded."""
        assert self.utils.is_page_excluded(
            "develop/guide.md", {}, skip_paths=["node_modules"]
        ) is False

    def test_front_matter_hide(self):
        """Pages with hide_ai_actions front matter are excluded."""
        assert self.utils.is_page_excluded(
            "develop/guide.md", {"hide_ai_actions": True}
        ) is True

    def test_front_matter_not_set(self):
        """Pages without hide_ai_actions front matter are not excluded."""
        assert self.utils.is_page_excluded("develop/guide.md", {}) is False

    def test_normal_page_not_excluded(self):
        """A normal page with no matching rules is not excluded."""
        assert self.utils.is_page_excluded(
            "develop/guide.md",
            {},
            skip_basenames=["README.md"],
            skip_paths=[".snippets"],
        ) is False

    def test_defaults_with_no_skip_lists(self):
        """When no skip lists are provided, only dot-dirs and front matter apply."""
        assert self.utils.is_page_excluded("develop/guide.md", {}) is False
        assert self.utils.is_page_excluded(".hidden/page.md", {}) is True


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
