from bs4 import BeautifulSoup

from plugins.link_processor.plugin import LinkProcessorPlugin


def make_plugin(skip_prefixes=None):
    plugin = LinkProcessorPlugin()
    plugin.load_config({"skip_internal_path_prefixes": skip_prefixes or []})
    return plugin


def process(html, skip_prefixes=None):
    plugin = make_plugin(skip_prefixes)
    return plugin.on_page_content(html, page=None, config=None, files=None)


def get_link(html):
    return BeautifulSoup(html, "html.parser").find("a")


class TestExternalLinks:
    def test_adds_target_blank(self):
        out = process('<a href="https://example.com">link</a>')
        a = get_link(out)
        assert a["target"] == "_blank"

    def test_adds_rel_noopener_noreferrer(self):
        out = process('<a href="https://example.com">link</a>')
        a = get_link(out)
        assert set(a["rel"]) == {"noopener", "noreferrer"}

    def test_merges_existing_rel(self):
        out = process('<a href="https://example.com" rel="sponsored">link</a>')
        a = get_link(out)
        assert set(a["rel"]) == {"noopener", "noreferrer", "sponsored"}

    def test_http_scheme_also_processed(self):
        out = process('<a href="http://example.com">link</a>')
        a = get_link(out)
        assert a["target"] == "_blank"
        assert set(a["rel"]) == {"noopener", "noreferrer"}

    def test_does_not_modify_href(self):
        href = "https://example.com/path?q=1#section"
        out = process(f'<a href="{href}">link</a>')
        a = get_link(out)
        assert a["href"] == href


class TestInternalLinks:
    def test_adds_trailing_slash(self):
        out = process('<a href="/learn/build">link</a>')
        a = get_link(out)
        assert a["href"] == "/learn/build/"

    def test_preserves_existing_trailing_slash(self):
        out = process('<a href="/learn/build/">link</a>')
        a = get_link(out)
        assert a["href"] == "/learn/build/"

    def test_adds_trailing_slash_with_fragment(self):
        out = process('<a href="/learn/build#some-section">link</a>')
        a = get_link(out)
        assert a["href"] == "/learn/build/#some-section"

    def test_adds_trailing_slash_with_query_and_fragment(self):
        out = process('<a href="/learn/build?v=2#section">link</a>')
        a = get_link(out)
        assert a["href"] == "/learn/build/?v=2#section"

    def test_relative_path(self):
        out = process('<a href="learn/build">link</a>')
        a = get_link(out)
        assert a["href"] == "learn/build/"

    def test_root_slash_unchanged(self):
        out = process('<a href="/">link</a>')
        a = get_link(out)
        assert a["href"] == "/"

    def test_no_target_or_rel_added(self):
        out = process('<a href="/learn/build">link</a>')
        a = get_link(out)
        assert a.get("target") is None
        assert a.get("rel") is None


class TestFragmentAndMailtoLinks:
    def test_fragment_only_unchanged(self):
        out = process('<a href="#section">link</a>')
        a = get_link(out)
        assert a["href"] == "#section"

    def test_mailto_unchanged(self):
        out = process('<a href="mailto:hello@example.com">link</a>')
        a = get_link(out)
        assert a["href"] == "mailto:hello@example.com"

    def test_fragment_no_target_or_rel(self):
        out = process('<a href="#section">link</a>')
        a = get_link(out)
        assert a.get("target") is None
        assert a.get("rel") is None


class TestFileExtensionPaths:
    def test_png_no_trailing_slash(self):
        out = process('<a href="/images/photo.png">link</a>')
        a = get_link(out)
        assert a["href"] == "/images/photo.png"

    def test_pdf_no_trailing_slash(self):
        out = process('<a href="/docs/guide.pdf">link</a>')
        a = get_link(out)
        assert a["href"] == "/docs/guide.pdf"

    def test_dotfile_in_segment_no_trailing_slash(self):
        out = process('<a href="/path/file.min.js">link</a>')
        a = get_link(out)
        assert a["href"] == "/path/file.min.js"


class TestSkipPrefixes:
    def test_skips_matching_prefix(self):
        out = process('<a href="/api/v1/endpoint">link</a>', skip_prefixes=["/api/"])
        a = get_link(out)
        assert a["href"] == "/api/v1/endpoint"

    def test_processes_non_matching_prefix(self):
        out = process('<a href="/docs/page">link</a>', skip_prefixes=["/api/"])
        a = get_link(out)
        assert a["href"] == "/docs/page/"

    def test_multiple_prefixes(self):
        out = process(
            '<a href="/static/file">link</a>',
            skip_prefixes=["/api/", "/static/"],
        )
        a = get_link(out)
        assert a["href"] == "/static/file"

    def test_prefix_must_match_start(self):
        out = process('<a href="/docs/api/page">link</a>', skip_prefixes=["/api/"])
        a = get_link(out)
        assert a["href"] == "/docs/api/page/"
