from unittest.mock import MagicMock

import yaml

from plugins.snippet_var_resolver.plugin import SnippetVarResolverPlugin, get_value_from_path


def make_plugin(variables=None):
    plugin = SnippetVarResolverPlugin()
    plugin.load_config({})
    plugin._variables = variables or {}
    return plugin


def resolve(html, variables=None):
    plugin = make_plugin(variables)
    return plugin.on_page_content(html, page=MagicMock(), config=None, files=None)


def make_config(include_yaml=None, extra=None, docs_dir=None):
    macros = MagicMock()
    macros.config = {"include_yaml": include_yaml or []}

    config = MagicMock()
    config.__getitem__ = lambda self, key: {
        "plugins": {"macros": macros},
        "extra": extra or {},
        "docs_dir": docs_dir or "/tmp/docs",
    }[key]
    config.get = lambda key, default=None: {
        "plugins": {"macros": macros},
        "extra": extra or {},
        "docs_dir": docs_dir or "/tmp/docs",
    }.get(key, default)
    return config


class TestGetValueFromPath:
    def test_top_level_key(self):
        assert get_value_from_path({"version": "1.0"}, "version") == "1.0"

    def test_dotted_path(self):
        data = {"dependencies": {"foo": {"version": "2.3"}}}
        assert get_value_from_path(data, "dependencies.foo.version") == "2.3"

    def test_missing_key_returns_none(self):
        assert get_value_from_path({"a": "b"}, "missing") is None

    def test_partially_missing_path_returns_none(self):
        data = {"dependencies": {"foo": "bar"}}
        assert get_value_from_path(data, "dependencies.foo.version") is None

    def test_empty_path_returns_none(self):
        assert get_value_from_path({"a": "b"}, "") is None


class TestVariableResolution:
    def test_simple_variable_replaced(self):
        out = resolve("<p>Version: {{ version }}</p>", {"version": "1.2.3"})
        assert out == "<p>Version: 1.2.3</p>"

    def test_dotted_path_replaced(self):
        variables = {"deps": {"zombienet": {"version": "v1.3.0"}}}
        out = resolve("<p>{{ deps.zombienet.version }}</p>", variables)
        assert out == "<p>v1.3.0</p>"

    def test_unknown_variable_left_intact(self):
        out = resolve("<p>{{ unknown.key }}</p>", {"version": "1.0"})
        assert out == "<p>{{ unknown.key }}</p>"

    def test_multiple_variables_in_one_page(self):
        variables = {"name": "Polkadot", "version": "1.0"}
        out = resolve("<p>{{ name }} {{ version }}</p>", variables)
        assert out == "<p>Polkadot 1.0</p>"

    def test_mixed_known_and_unknown(self):
        out = resolve("<p>{{ name }} and {{ missing }}</p>", {"name": "Polkadot"})
        assert out == "<p>Polkadot and {{ missing }}</p>"

    def test_no_variables_loaded_returns_html_unchanged(self):
        html = "<p>{{ version }}</p>"
        out = resolve(html, {})
        assert out == html

    def test_whitespace_variants_in_placeholder(self):
        variables = {"version": "1.0"}
        assert "1.0" in resolve("<p>{{version}}</p>", variables)
        assert "1.0" in resolve("<p>{{  version  }}</p>", variables)

    def test_variable_in_href(self):
        variables = {"repo": {"url": "https://github.com/example/repo"}}
        out = resolve('<a href="{{ repo.url }}">link</a>', variables)
        assert 'href="https://github.com/example/repo"' in out

    def test_non_string_value_cast_to_string(self):
        out = resolve("<p>{{ count }}</p>", {"count": 42})
        assert out == "<p>42</p>"

    def test_no_placeholders_returns_html_unchanged(self):
        html = "<p>No variables here.</p>"
        assert resolve(html, {"version": "1.0"}) == html


class TestOnConfig:
    def test_loads_variables_from_include_yaml(self, tmp_path):
        # Plugin resolves yaml paths relative to docs_dir parent, so place
        # variables.yml at tmp_path and set docs_dir to tmp_path/docs.
        (tmp_path / "variables.yml").write_text(yaml.dump({"version": "3.0", "name": "Test"}))

        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})
        config = _build_config(tmp_path, include_yaml=["variables.yml"])

        plugin.on_config(config)
        assert plugin._variables.get("version") == "3.0"
        assert plugin._variables.get("name") == "Test"

    def test_merges_multiple_yaml_files(self, tmp_path):
        (tmp_path / "a.yml").write_text(yaml.dump({"key_a": "val_a"}))
        (tmp_path / "b.yml").write_text(yaml.dump({"key_b": "val_b"}))

        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})
        config = _build_config(tmp_path, include_yaml=["a.yml", "b.yml"])

        plugin.on_config(config)
        assert plugin._variables.get("key_a") == "val_a"
        assert plugin._variables.get("key_b") == "val_b"

    def test_malformed_yaml_does_not_raise(self, tmp_path):
        (tmp_path / "bad.yml").write_text("key: [unclosed")

        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})
        config = _build_config(tmp_path, include_yaml=["bad.yml"])

        plugin.on_config(config)  # should not raise
        assert plugin._variables == {}

    def test_non_mapping_yaml_does_not_raise(self, tmp_path):
        (tmp_path / "list.yml").write_text(yaml.dump(["item1", "item2"]))

        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})
        config = _build_config(tmp_path, include_yaml=["list.yml"])

        plugin.on_config(config)  # should not raise
        assert plugin._variables == {}

    def test_missing_yaml_file_does_not_raise(self, tmp_path):
        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})
        config = _build_config(tmp_path, include_yaml=["nonexistent.yml"])

        plugin.on_config(config)  # should not raise
        assert plugin._variables == {}

    def test_no_macros_plugin_does_not_raise(self, tmp_path):
        plugin = SnippetVarResolverPlugin()
        plugin.load_config({})

        config = MagicMock()
        config.__getitem__ = lambda self, key: {
            "plugins": {},
            "extra": {},
            "docs_dir": str(tmp_path / "docs"),
        }[key]
        config.get = lambda key, default=None: {
            "plugins": {},
            "extra": {},
            "docs_dir": str(tmp_path / "docs"),
        }.get(key, default)

        plugin.on_config(config)  # should not raise
        assert plugin._variables == {}


# --- helpers ---

def _make_macros(include_yaml=None):
    macros = MagicMock()
    macros.config = {"include_yaml": include_yaml or []}
    return macros


def _build_config(tmp_path, include_yaml=None, extra=None):
    macros = _make_macros(include_yaml)
    docs_dir = str(tmp_path / "docs")

    config = MagicMock()
    config.__getitem__ = lambda self, key: {
        "plugins": {"macros": macros},
        "extra": extra or {},
        "docs_dir": docs_dir,
    }[key]
    config.get = lambda key, default=None: {
        "plugins": {"macros": macros},
        "extra": extra or {},
        "docs_dir": docs_dir,
    }.get(key, default)
    return config
