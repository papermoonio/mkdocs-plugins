# resolve_md plugin

# imports
import json
import os
import re
import shutil
import yaml

from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from mkdocs.utils import log
from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin

# Module scope regex variables

FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
SNIPPET_TOKEN_REGEX = re.compile(r"-{1,}8<-{2,}\s*['\"]([^'\"]+)['\"]")
SNIPPET_LINE_REGEX = re.compile(
    r"(?m)^(?P<indent>[ \t]*)-{1,}8<-{2,}\s*['\"](?P<ref>[^'\"]+)['\"]\s*$"
)

# Define plugin class
class ResolveMDPlugin(BasePlugin):
    # Define value for `llms_config` in the project mkdocs.yml file
    config_scheme = (("llms_config", Type(str, required=True)),)

    def __init__(self):
        super().__init__()
        self.allow_remote_snippets = True

    # Process will start after site build is complete
    def on_post_build(self, config):
        # Locate and load config
        config_file_path = Path(config["config_file_path"]).resolve()
        project_root = config_file_path.parent
        self.llms_config = self.load_llms_config(project_root)
        snippet_cfg = self.llms_config.get("snippets", {})
        self.allow_remote_snippets = snippet_cfg.get("allow_remote", True)

        log.info(f"[resolve_md] loaded llms_config from {project_root}")

        # Resolve docs_dir to normalized path
        docs_dir = self.load_mkdocs_docs_dir(project_root)
        if docs_dir is None:
            docs_dir = Path(config["docs_dir"]).resolve()

        log.info(f"[resolve_md] resolved docs_dir to {docs_dir}")

        # Snippet directory defaults to docs/.snippets
        snippet_dir = docs_dir / ".snippets"
        if not snippet_dir.exists():
            log.debug(f"[resolve_md] snippet directory not found at {snippet_dir}")

        # Load shared variables (variables.yml sits inside docs_dir)
        variables_path = docs_dir / "variables.yml"
        variables = self.load_yaml(str(variables_path))
        if not variables:
            log.warning(f"[resolve_md] no variables loaded from {variables_path}")
        else:
            log.info(
                f"[resolve_md] loaded {len(variables)} top-level variables from {variables_path}"
            )

        # Determine docs_base_url for canonical URLs
        project_cfg = self.llms_config.get("project", {})
        docs_base_url = (project_cfg.get("docs_base_url", "") or "").rstrip("/") + "/"

        # Determine output directory for resolved markdown
        ai_pages_dir = self.get_ai_output_dir(project_root)
        self.reset_ai_output_dir(ai_pages_dir)
        log.info(f"[resolve_md] writing resolved pages to {ai_pages_dir}")

        # Loop through docs_dir MD files, filter for exclusions defined in llms_config.json
        content_cfg = self.llms_config.get("content", {})
        exclusions = content_cfg.get("exclusions", {})
        skip_basenames = exclusions.get("skip_basenames", [])
        skip_paths = exclusions.get("skip_paths", [])
        markdown_files = self.get_all_markdown_files(
            docs_dir, skip_basenames, skip_paths
        )

        log.info(f"[resolve_md] found {len(markdown_files)} markdown files")

        processed = 0

        # For each file in markdown_files
        for md_path in markdown_files:
            text = Path(md_path).read_text(encoding="utf-8")
            # Separate, filter, map, and return desired front matter
            front_matter, body = self.split_front_matter(text)
            reduced_fm = self.map_front_matter(front_matter)
            # Resolve snippet placeholders first
            snippet_body = self.replace_snippet_placeholders(body, snippet_dir, variables)
            if snippet_body != body:
                log.debug(f"[resolve_md] resolved snippets in {md_path}")
            body = snippet_body
            # Resolve variable placeholders against variables.yml definitions
            resolved_body = self.resolve_markdown_placeholders(body, variables)
            if resolved_body != body:
                log.debug(f"[resolve_md] resolved placeholders in {md_path}")
            # Remove HTML comments after substitutions
            cleaned_body = self.remove_html_comments(resolved_body)
            if cleaned_body != resolved_body:
                log.debug(f"[resolve_md] stripped HTML comments in {md_path}")
            # Convert path to slug and create raw file URL
            rel_path = Path(md_path).relative_to(docs_dir)
            rel_no_ext = str(rel_path.with_suffix(""))
            slug, url = self.compute_slug_and_url(rel_no_ext, docs_base_url)
            # Output resolved Markdown file to AI artifacts directory
            header = dict(reduced_fm)
            header["url"] = url
            self.write_ai_page(ai_pages_dir, slug, header, cleaned_body)
            processed += 1

            log.debug(f"[resolve_md] {md_path} FM keys: {list(front_matter.keys())}")
            log.debug(f"[resolve_md] {md_path} mapped FM: {reduced_fm}")

        log.info(f"[resolve_md] processed {processed} AI pages")

        # Mirror resolved pages into site/ so the UI widgets can fetch them.
        site_dir = Path(config["site_dir"]).resolve()
        self.copy_ai_pages_to_site(ai_pages_dir, site_dir)


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

    # Replace snippet placeholders with code blocks

    @staticmethod
    def parse_line_range(snippet_path: str):
        """Split snippet reference into filename and optional start/end line numbers."""
        parts = snippet_path.split(":")
        file_only = parts[0]
        line_start = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
        line_end = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else None
        return file_only, line_start, line_end

    def fetch_local_snippet(self, snippet_ref: str, snippet_directory: Path) -> str:
        """Load snippet content from docs/.snippets (optionally slicing by line range)."""
        file_only, line_start, line_end = self.parse_line_range(snippet_ref)
        snippet_directory = Path(snippet_directory)
        absolute_snippet_path = (snippet_directory / file_only).resolve()

        if not absolute_snippet_path.exists():
            log.warning(f"[resolve_md] missing local snippet {snippet_ref}")
            return f"<!-- MISSING LOCAL SNIPPET {snippet_ref} -->"

        snippet_content = absolute_snippet_path.read_text(encoding="utf-8")
        lines = snippet_content.split("\n")
        if line_start is not None or line_end is not None:
            start_idx = max(line_start - 1, 0) if line_start is not None else 0
            end_idx = line_end if line_end is not None else len(lines)
            snippet_content = "\n".join(lines[start_idx:end_idx])
        return snippet_content

    def fetch_remote_snippet(self, snippet_ref: str) -> str:
        """Retrieve remote snippet via HTTP unless remote fetching is disabled."""
        if not self.allow_remote_snippets:
            return f"<!-- REMOTE SNIPPET SKIPPED (disabled): {snippet_ref} -->"
        match = re.match(r"^(https?://.+?)(?::(\d+))?(?::(\d+))?$", snippet_ref)
        if not match:
            log.warning(f"[resolve_md] invalid remote snippet ref {snippet_ref}")
            return f"<!-- INVALID REMOTE SNIPPET {snippet_ref} -->"

        url = match.group(1)
        line_start = int(match.group(2)) if match.group(2) else None
        line_end = int(match.group(3)) if match.group(3) else None

        try:
            with urllib_request.urlopen(url, timeout=10) as response:
                snippet_content = response.read().decode("utf-8")
        except (urllib_error.URLError, urllib_error.HTTPError) as exc:
            log.warning(f"[resolve_md] error fetching remote snippet {snippet_ref}: {exc}")
            return f"<!-- ERROR FETCHING REMOTE SNIPPET {snippet_ref} -->"

        if line_start is not None or line_end is not None:
            lines = snippet_content.split("\n")
            start_idx = max(line_start - 1, 0) if line_start is not None else 0
            end_idx = line_end if line_end is not None else len(lines)
            snippet_content = "\n".join(lines[start_idx:end_idx])
        return snippet_content.strip()

    def replace_snippet_placeholders(
        self, markdown: str, snippet_directory: Path, variables: dict
    ) -> str:
        """
        Recursively replace --8<-- snippet placeholders until none remain.
        Snippet references can include {{variables}} which are resolved first.
        """

        def fetch_snippet(snippet_ref: str) -> str:
            resolved_path = self.resolve_markdown_placeholders(snippet_ref, variables)
            if resolved_path.startswith("http"):
                return self.fetch_remote_snippet(resolved_path)
            return self.fetch_local_snippet(resolved_path, snippet_directory)

        def replace_line_match(match: re.Match) -> str:
            indent = match.group("indent") or ""
            snippet_ref = match.group("ref")
            snippet_content = fetch_snippet(snippet_ref).replace("\r\n", "\n")
            if not indent:
                return snippet_content
            indented = [
                f"{indent}{line}" if line else "" for line in snippet_content.split("\n")
            ]
            return "\n".join(indented)

        def replace_inline_match(match: re.Match) -> str:
            snippet_ref = match.group(1)
            return fetch_snippet(snippet_ref)

        previous = None
        while previous != markdown:
            previous = markdown
            markdown = SNIPPET_LINE_REGEX.sub(replace_line_match, markdown)
            markdown = SNIPPET_TOKEN_REGEX.sub(replace_inline_match, markdown)
        return markdown

    # Remove HTML comments from Markdown

    @staticmethod
    def remove_html_comments(content: str) -> str:
        """Remove <!-- ... --> comments (multiline)."""
        return re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
    
    # Convert file path to slug, create markdown file URL

    @staticmethod
    def compute_slug_and_url(rel_path_no_ext: str, docs_base_url: str):
        """
        rel_path_no_ext: docs-relative path without extension, using OS separators.
        - If endswith '/index', drop the trailing 'index' for the URL and slug base.
        - Slug = path segments joined by '-', lowercased.
        - URL = docs_base_url + route + '/'
        """
        # Normalize to forward slashes
        route = rel_path_no_ext.replace(os.sep, "/")
        if route.endswith("/index"):
            route = route[:-len("/index")]
        # slug
        slug = route.replace("/", "-").lower()
        # url (ensure one trailing slash)
        if not route.endswith("/"):
            route = f"{route}/"
        url = f"{docs_base_url}{route}"
        return slug, url

    @staticmethod
    def build_raw_url(config: dict, slug: str) -> str:
        org = config["repository"]["org"]
        repo = config["repository"]["repo"]
        branch = config["repository"]["default_branch"]
        public_root = config.get("outputs", {}).get("public_root", "/.ai/").strip("/")
        pages_dirname = config.get("outputs", {}).get("files", {}).get("pages_dir", "pages")
        return f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{public_root}/{pages_dirname}/{slug}"

    def get_ai_output_dir(self, project_root: Path) -> Path:
        """Resolve target directory for resolved markdown files."""
        repo_cfg = self.llms_config.get("repository", {})
        ai_path = repo_cfg.get("ai_artifacts_path")
        if ai_path:
            ai_path = Path(ai_path)
            if not ai_path.is_absolute():
                ai_path = (project_root / ai_path).resolve()
        else:
            outputs_cfg = self.llms_config.get("outputs", {})
            public_root = outputs_cfg.get("public_root", "/.ai/").strip("/")
            pages_dir = outputs_cfg.get("files", {}).get("pages_dir", "pages")
            ai_path = (project_root / public_root / pages_dir).resolve()
        return Path(ai_path)

    def reset_ai_output_dir(self, output_dir: Path) -> None:
        """Remove existing AI page artifacts before writing fresh files."""
        output_dir.mkdir(parents=True, exist_ok=True)
        for entry in output_dir.iterdir():
            if entry.is_dir():
                shutil.rmtree(entry)
            else:
                entry.unlink()

    def write_ai_page(self, ai_pages_dir: Path, slug: str, header: dict, body: str):
        """Write resolved markdown with YAML front matter."""
        ai_pages_dir.mkdir(parents=True, exist_ok=True)
        out_path = ai_pages_dir / f"{slug}.md"
        fm_obj = {}
        for key in ("title", "description", "categories", "url"):
            val = header.get(key)
            if val not in (None, "", []):
                fm_obj[key] = val

        fm_yaml = yaml.safe_dump(
            fm_obj, sort_keys=False, allow_unicode=True, width=4096
        ).strip()
        content = f"---\n{fm_yaml}\n---\n\n{body.strip()}\n"
        with out_path.open("w", encoding="utf-8") as fh:
            fh.write(content)
        log.debug(f"[resolve_md] wrote {out_path}")

    def copy_ai_pages_to_site(self, source_dir: Path, site_dir: Path) -> None:
        """Copy resolved AI pages into the built site directory."""
        outputs_cfg = self.llms_config.get("outputs", {})
        public_root = outputs_cfg.get("public_root", "/ai/").strip("/")
        pages_dir = outputs_cfg.get("files", {}).get("pages_dir", "pages")

        target_segments = [seg for seg in public_root.split("/") if seg]
        if pages_dir:
            target_segments.append(pages_dir)

        target_dir = site_dir.joinpath(*target_segments) if target_segments else site_dir / pages_dir
        target_dir = target_dir.resolve()

        if target_dir.exists():
            shutil.rmtree(target_dir)

        try:
            shutil.copytree(source_dir, target_dir)
            log.info(f"[resolve_md] copied AI pages to {target_dir}")
        except Exception as exc:
            log.error(f"[resolve_md] failed to copy AI pages to site dir: {exc}")
