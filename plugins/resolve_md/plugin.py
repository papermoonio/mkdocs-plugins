# resolve_md plugin

# imports
import json
import os
import re
import shutil
import yaml

from mkdocs.utils import log
from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin
from pathlib import Path

# Module scope regex variables

FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")


# Define plugin class
class ResolveMDPlugin(BasePlugin):
    # Define value for `llms_config` in the project mkdocs.yml file
    config_scheme = (("llms_config", Type(str, required=True)),)

    # Process will start after site build is complete
    def on_post_build(self, config):
        # Locate and load config
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        self.llms_config = self.load_llms_config(project_root)

        log.info(f"[resolve_md] loaded llms_config from {project_root}")

        # Resolve docs_dir to normalized path
        docs_dir = self.load_mkdocs_docs_dir(project_root)
        if docs_dir is None:
            docs_dir = Path(config["docs_dir"]).resolve()

        log.info(f"[resolve_md] resolved docs_dir to {docs_dir}")

        # Load shared variables (variables.yml sits inside docs_dir)
        variables_path = docs_dir / "variables.yml"
        variables = self.load_yaml(str(variables_path))
        if not variables:
            log.warning(f"[resolve_md] no variables loaded from {variables_path}")
        else:
            log.info(
                f"[resolve_md] loaded {len(variables)} top-level variables from {variables_path}"
            )

        # Loop through docs_dir MD files, filter for exclusions defined in llms_config.json
        content_cfg = self.llms_config.get("content", {})
        exclusions = content_cfg.get("exclusions", {})
        skip_basenames = exclusions.get("skip_basenames", [])
        skip_paths = exclusions.get("skip_paths", [])
        markdown_files = self.get_all_markdown_files(
            docs_dir, skip_basenames, skip_paths
        )

        log.info(f"[resolve_md] found {len(markdown_files)} markdown files")

        # For each file in markdown_files
        for md_path in markdown_files:
            text = Path(md_path).read_text(encoding="utf-8")
            # Separate, filter, map, and return desired front matter
            front_matter, body = self.split_front_matter(text)
            reduced_fm = self.map_front_matter(front_matter)
            # Resolve variable placeholders against variables.yml definitions
            resolved_body = self.resolve_markdown_placeholders(body, variables)
            if resolved_body != body:
                log.debug(f"[resolve_md] resolved placeholders in {md_path}")
            # Remove HTML comments after substitutions
            cleaned_body = self.remove_html_comments(resolved_body)
            if cleaned_body != resolved_body:
                log.debug(f"[resolve_md] stripped HTML comments in {md_path}")

            log.debug(f"[resolve_md] {md_path} FM keys: {list(front_matter.keys())}")
            log.debug(f"[resolve_md] {md_path} mapped FM: {reduced_fm}")


    # ----- Helper functions -------

    # File discovery and filtering per skip names/paths in llms_config.json
    @staticmethod
    def get_all_markdown_files(docs_dir, skip_basenames, skip_paths):
        """Collect *.md|*.mdx, skipping basenames and paths that contain any skip_paths substring."""
        results = []
        for root, _, files in os.walk(docs_dir):
            if any(x in root for x in skip_paths):
                continue
            for file in files:
                if file.endswith((".md", ".mdx")) and file not in skip_basenames:
                    results.append(os.path.join(root, file))
        return sorted(results)

    # Loaders for: llms_config.json, yaml files, and Mkdocs docs_dir

    def load_llms_config(self, project_root: Path) -> dict:
        """Load llms_config.json from the repo root."""
        config_json = self.config["llms_config"]
        llms_config_path = (project_root / config_json).resolve()

        if not llms_config_path.exists():
            raise FileNotFoundError(f"llms_config not found at {llms_config_path}")

        with llms_config_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        log.debug(f"[resolve_md] llms_config keys: {list(data.keys())}")
        return data

    @staticmethod
    def load_yaml(yaml_file: str):
        """Load a YAML file; return {} if missing/empty."""
        if not os.path.exists(yaml_file):
            return {}
        try:
            with open(yaml_file, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            log.warning(f"[resolve_md] unable to parse YAML file {yaml_file}: {exc}")
            return {}
        return data or {}

    def load_mkdocs_docs_dir(self, repo_root: Path) -> Path | None:
        """Prefer mkdocs.yml docs_dir if present; fall back to plugin config."""
        mkdocs_path = repo_root / "mkdocs.yml"
        if mkdocs_path.exists():
            mk = self.load_yaml(str(mkdocs_path))
            docs_dir = mk.get("docs_dir") if isinstance(mk, dict) else None
            if docs_dir:
                return (repo_root / docs_dir).resolve()
        return None

    # Front-matter helpers

    @staticmethod
    def split_front_matter(source_text: str):
        """
        Return (front_matter_dict, body_text). If no FM, dict={} and body=source_text.
        """
        m = FM_PATTERN.match(source_text)
        if not m:
            return {}, source_text
        fm_text = m.group(1)
        try:
            fm = yaml.safe_load(fm_text) or {}
        except Exception:
            fm = {}
        body = source_text[m.end() :]
        return fm, body

    @staticmethod
    def map_front_matter(fm: dict) -> dict:
        """
        Emit front matter fields:
        - title (as-is)
        - description (prefer 'description', else fallback to 'summary' if present)
        - categories (as-is)
        """
        out = {}
        if "title" in fm:
            out["title"] = fm["title"]
        # prefer description; fallback to summary if authors used that
        if "description" in fm:
            out["description"] = fm["description"]
        elif "summary" in fm:
            out["description"] = fm["summary"]
        if "categories" in fm:
            out["categories"] = fm["categories"]
        return out

    # Resolve variable and placeholders

    @staticmethod
    def get_value_from_path(data, path):
        """Simple dotted lookup (dicts only, no arrays)."""
        if not path:
            return None
        keys = [k.strip() for k in path.split(".") if k.strip()]
        value = data
        for key in keys:
            if not isinstance(value, dict) or key not in value:
                return None
            value = value[key]
        return value

    @staticmethod
    def resolve_markdown_placeholders(content: str, variables: dict) -> str:
        """Replace {{ dotted.keys }} using variables dict; leave unknowns intact."""

        def replacer(match):
            key_path = match.group(1)
            value = ResolveMDPlugin.get_value_from_path(variables, key_path)
            return str(value) if value is not None else match.group(0)

        return PLACEHOLDER_PATTERN.sub(replacer, content)

    # Remove HTML comments from Markdown

    @staticmethod
    def remove_html_comments(content: str) -> str:
        """Remove <!-- ... --> comments (multiline)."""
        return re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    
    
