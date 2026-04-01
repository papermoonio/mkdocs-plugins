import logging
import re

import yaml
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.files import Files
from mkdocs.structure.pages import Page

log = logging.getLogger("mkdocs.plugins.snippet_var_resolver")

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


def get_value_from_path(data, path):
    """Dotted key lookup into a nested dict (e.g. 'dependencies.foo.version')."""
    value = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


class SnippetVarResolverPlugin(BasePlugin):
    config_scheme = ()

    def on_config(self, config: MkDocsConfig) -> MkDocsConfig:
        self._variables = {}

        # Load variables from macros plugin's include_yaml files
        macros = config["plugins"].get("macros")
        if macros:
            for yaml_path in macros.config.get("include_yaml", []):
                self._load_yaml_file(yaml_path, config)
        else:
            log.debug("[snippet_var_resolver] macros plugin not found, skipping include_yaml")

        if self._variables:
            log.debug(f"[snippet_var_resolver] loaded {len(self._variables)} top-level variable keys")
        else:
            log.warning("[snippet_var_resolver] no variables loaded — {{ }} patterns will not be resolved")

        return config

    def _load_yaml_file(self, yaml_path: str, config: MkDocsConfig) -> None:
        from pathlib import Path

        # Resolve relative to project root, then docs_dir, then as an absolute path
        candidates = [
            Path(config["docs_dir"]).parent / yaml_path,
            Path(config["docs_dir"]) / yaml_path,
            Path(yaml_path),
        ]
        for path in candidates:
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                except yaml.YAMLError as exc:
                    log.warning(f"[snippet_var_resolver] unable to parse {path}: {exc}")
                    return
                if not isinstance(data, dict):
                    log.warning(f"[snippet_var_resolver] expected a YAML mapping in {path}, got {type(data).__name__} — skipping")
                    return
                self._variables.update(data)
                log.debug(f"[snippet_var_resolver] loaded variables from {path}")
                return

        log.warning(f"[snippet_var_resolver] variables file not found: {yaml_path}")

    def on_page_content(
        self, html: str, page: Page, config: MkDocsConfig, files: Files
    ) -> str:
        if not self._variables:
            return html

        def replacer(match):
            key_path = match.group(1)
            value = get_value_from_path(self._variables, key_path)
            if value is not None:
                return str(value)
            return match.group(0)

        resolved = PLACEHOLDER_PATTERN.sub(replacer, html)

        if resolved != html:
            log.debug(f"[snippet_var_resolver] resolved variables in {page.file.src_path}")

        return resolved
