import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

import yaml
from mkdocs.config.config_options import Type
from mkdocs.plugins import BasePlugin
from mkdocs.utils import log

# Module scope regex variables

FM_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
PLACEHOLDER_PATTERN = re.compile(r"{{\s*([A-Za-z0-9_.-]+)\s*}}")
SNIPPET_TOKEN_REGEX = re.compile(r"-{1,}8<-{2,}\s*['\"]([^'\"]+)['\"]")
SNIPPET_LINE_REGEX = re.compile(
    r"(?m)^(?P<indent>[ \t]*)-{1,}8<-{2,}\s*['\"](?P<ref>[^'\"]+)['\"]\s*$"
)
HEADING_RE = re.compile(r"^(#{2,6})\s+(.+?)\s*#*\s*$")
SNIPPET_SECTION_REGEX = re.compile(
    r"""^\s*(?:#|//|;|<!--)\s*--8<--\s*\[(?:start|end):[^\]]+\]\s*(?:-->)*\s*$""",
    re.IGNORECASE,
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

        # Resolve docs_dir to normalized path
        docs_dir = self.load_mkdocs_docs_dir(project_root)
        if docs_dir is None:
            docs_dir = Path(config["docs_dir"]).resolve()
        site_dir = Path(config["site_dir"]).resolve()

        # Snippet directory defaults to docs/.snippets
        snippet_dir = docs_dir / ".snippets"
        if not snippet_dir.exists():
            log.debug(f"[resolve_md] snippet directory not found at {snippet_dir}")

        # Load shared variables (variables.yml sits inside docs_dir)
        variables_path = docs_dir / "variables.yml"
        variables = self.load_yaml(str(variables_path))
        if not variables:
            log.warning(f"[resolve_md] no variables loaded from {variables_path}")

        # Determine docs_base_url for canonical URLs
        project_cfg = self.llms_config.get("project", {})
        docs_base_url = (project_cfg.get("docs_base_url", "") or "").rstrip("/") + "/"

        # Determine output directory for resolved markdown (inside site directory)
        ai_pages_dir = self.get_ai_output_dir(site_dir)
        ai_root = ai_pages_dir.parent
        ai_root.mkdir(parents=True, exist_ok=True)
        self.reset_directory(ai_pages_dir)
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

        ai_pages: list[dict] = []

        # For each file in markdown_files
        for md_path in markdown_files:
            text = Path(md_path).read_text(encoding="utf-8")
            # Separate, filter, map, and return desired front matter
            front_matter, body = self.split_front_matter(text)
            reduced_fm = self.map_front_matter(front_matter)
            categories = self.normalize_categories(reduced_fm.get("categories"))
            if categories:
                reduced_fm["categories"] = categories
            elif "categories" in reduced_fm:
                reduced_fm.pop("categories")
            # Resolve snippet placeholders first
            snippet_body = self.replace_snippet_placeholders(
                body, snippet_dir, variables
            )
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
            # Calculate word count and estimated token count
            word_count = self.word_count(cleaned_body)
            token_estimate = self.estimate_tokens(cleaned_body)

            # Output resolved Markdown file to AI artifacts directory
            header = dict(reduced_fm)
            header["url"] = url
            header["word_count"] = word_count
            header["token_estimate"] = token_estimate
            self.write_ai_page(ai_pages_dir, slug, header, cleaned_body)
            processed += 1
            # Creates list used later for category file creation
            cats = reduced_fm.get("categories") or []
            if isinstance(cats, str):
                cats_value = [cats]
            else:
                cats_value = cats

            ai_pages.append(
                {
                    "slug": slug,
                    "path": Path(md_path),
                    "title": header.get("title") or slug,
                    "description": header.get("description") or "",
                    "categories": cats_value,
                    "url": url,
                    "word_count": word_count,
                    "token_estimate": token_estimate,
                    "body": cleaned_body,
                }
            )

            log.debug(f"[resolve_md] {md_path} FM keys: {list(front_matter.keys())}")
            log.debug(f"[resolve_md] {md_path} mapped FM: {reduced_fm}")

        log.info(f"[resolve_md] processed {processed} AI pages")
        if ai_pages:
            log.debug(
                f"[resolve_md] sample AI page metadata: slug={ai_pages[0]['slug']} cats={ai_pages[0].get('categories')}"
            )

        # Build category bundles based on current AI pages
        self.build_category_bundles(ai_pages, ai_root)
        # Build site index + llms JSONL artifacts
        self.build_site_index(ai_pages, ai_root)
        # Build llms.txt for downstream LLM usage directly into the site output
        self.build_llms_txt(ai_pages, site_dir)

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

    @staticmethod
    def normalize_categories(raw) -> list[str]:
        """Normalize categories value into a list of non-empty strings."""
        if raw is None:
            return []
        result: list[str] = []
        if isinstance(raw, list):
            candidates = raw
        elif isinstance(raw, str):
            val = raw.strip()
            if not val:
                return []
            if val.startswith("[") and val.endswith("]"):
                try:
                    parsed = yaml.safe_load(val)
                    candidates = parsed if isinstance(parsed, list) else [val]
                except Exception:
                    candidates = [val]
            else:
                candidates = val.split(",")
        else:
            candidates = [raw]
        for item in candidates:
            text = str(item).strip()
            if text:
                result.append(text)
        return result

    # Resolve variables and placeholders

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
        snippet_directory_root = Path(snippet_directory).resolve()
        absolute_snippet_path = (snippet_directory_root / file_only).resolve()

        # Ensure the resolved path is still within the snippet directory to prevent traversal
        try:
            absolute_snippet_path.relative_to(snippet_directory_root)
        except ValueError:
            log.warning(f"[resolve_md] invalid local snippet path (outside snippet directory): {snippet_ref}")
            return f"<!-- INVALID LOCAL SNIPPET PATH {snippet_ref} -->"
        if not absolute_snippet_path.exists():
            log.warning(f"[resolve_md] missing local snippet {snippet_ref}")
            return f"<!-- MISSING LOCAL SNIPPET {snippet_ref} -->"

        snippet_content = absolute_snippet_path.read_text(encoding="utf-8")
        lines = snippet_content.split("\n")
        if line_start is not None or line_end is not None:
            start_idx = max(line_start - 1, 0) if line_start is not None else 0
            end_idx = line_end if line_end is not None else len(lines)
            snippet_content = "\n".join(lines[start_idx:end_idx])
        return self.strip_snippet_section_markers(snippet_content)

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
            log.warning(
                f"[resolve_md] error fetching remote snippet {snippet_ref}: {exc}"
            )
            return f"<!-- ERROR FETCHING REMOTE SNIPPET {snippet_ref} -->"

        if line_start is not None or line_end is not None:
            lines = snippet_content.split("\n")
            start_idx = max(line_start - 1, 0) if line_start is not None else 0
            end_idx = line_end if line_end is not None else len(lines)
            snippet_content = "\n".join(lines[start_idx:end_idx])
        snippet_content = snippet_content.strip()
        return self.strip_snippet_section_markers(snippet_content)

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
                f"{indent}{line}" if line else ""
                for line in snippet_content.split("\n")
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

    @staticmethod
    def strip_snippet_section_markers(content: str) -> str:
        """Remove snippet section markers (# --8<-- [start:end]) from snippet content."""
        lines = content.splitlines()
        cleaned = [ln for ln in lines if not SNIPPET_SECTION_REGEX.match(ln.strip())]
        return "\n".join(cleaned)

    # Word count & token estimation

    @staticmethod
    def word_count(content: str) -> int:
        return len(re.findall(r"\b\w+\b", content, flags=re.UNICODE))

    @staticmethod
    def estimate_tokens(content: str) -> int:
        return len(re.findall(r"\w+|[^\s\w]", content, flags=re.UNICODE))

    @staticmethod
    def sha256_text(content: str) -> str:
        return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()

    def extract_outline_and_sections(
        self, body: str, max_depth: int = 3
    ) -> tuple[list[dict], list[dict]]:
        lines = body.splitlines(keepends=True)
        in_code = False
        fence = None

        starts = [0]
        for ln in lines[:-1]:
            starts.append(starts[-1] + len(ln))

        outline: list[dict] = []
        sections_meta: list[tuple[int, int, str, str]] = []
        anchors_seen: dict[str, int] = {}

        for idx, line in enumerate(lines):
            m_fence = re.match(r"^(\s*)(`{3,}|~{3,})", line)
            if m_fence:
                token = m_fence.group(2)
                if not in_code:
                    in_code, fence = True, token
                elif token == fence:
                    in_code, fence = False, None
                continue

            if in_code:
                continue

            m = HEADING_RE.match(line)
            if not m:
                continue
            hashes, text = m.group(1), m.group(2).strip()
            depth = len(hashes)
            if depth < 2 or depth > max_depth:
                continue
            anchor = self.slugify_anchor(text, anchors_seen)
            outline.append({"depth": depth, "title": text, "anchor": anchor})
            sections_meta.append((depth, idx, text, anchor))

        sections: list[dict] = []
        for idx, (depth, line_idx, title, anchor) in enumerate(sections_meta):
            start_char = starts[line_idx]
            next_start = len(body)
            if idx + 1 < len(sections_meta):
                next_start = starts[sections_meta[idx + 1][1]]
            section_text = body[start_char:next_start].strip()
            sections.append(
                {
                    "index": idx,
                    "depth": depth,
                    "title": title,
                    "anchor": anchor,
                    "start_char": start_char,
                    "end_char": next_start,
                    "text": section_text,
                }
            )

        return outline, sections

    def extract_preview(self, body: str, max_chars: int = 500) -> str:
        lines = body.splitlines()
        in_code = False
        para: list[str] = []

        def bad_start(s: str) -> bool:
            s = s.lstrip()
            return (
                not s
                or s.startswith("#")
                or s.startswith(">")
                or s.startswith("- ")
                or s.startswith("* ")
                or re.match(r"^\d+\.\s", s) is not None
            )

        def finish(buf: list[str]) -> str:
            text = " ".join(" ".join(buf).split())
            return text[:max_chars].rstrip()

        for line in lines:
            if re.match(r"^(\s*)(`{3,}|~{3,})", line):
                in_code = not in_code
                if para:
                    break
                continue
            if in_code:
                continue
            if line.strip() == "":
                if para:
                    break
                continue
            if not para and bad_start(line):
                continue
            para.append(line)

        return finish(para) if para else ""

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
            route = route[: -len("/index")]
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
        pages_dirname = (
            config.get("outputs", {}).get("files", {}).get("pages_dir", "pages")
        )
        return f"https://raw.githubusercontent.com/{org}/{repo}/{branch}/{public_root}/{pages_dirname}/{slug}"

    def get_ai_output_dir(self, base_dir: Path) -> Path:
        """Resolve target directory for resolved markdown files."""
        repo_cfg = self.llms_config.get("repository", {})
        ai_path = repo_cfg.get("ai_artifacts_path")
        if ai_path:
            ai_path = Path(ai_path)
            if not ai_path.is_absolute():
                ai_path = (base_dir / ai_path).resolve()
        else:
            outputs_cfg = self.llms_config.get("outputs", {})
            public_root = outputs_cfg.get("public_root", "/ai/").strip("/")
            pages_dir = outputs_cfg.get("files", {}).get("pages_dir", "pages")
            ai_path = (base_dir / public_root / pages_dir).resolve()
        return Path(ai_path)

    def reset_directory(self, output_dir: Path) -> None:
        """Remove existing artifacts before writing fresh files."""
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
        for key in (
            "title",
            "description",
            "categories",
            "url",
            "word_count",
            "token_estimate",
        ):
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

    # Replaces copy_md plugin actions
    # Category file creation helper functions
    @staticmethod
    def slugify_category(name: str) -> str:
        s = name.strip().lower()
        s = re.sub(r"[^\w\s-]", "", s)
        s = re.sub(r"\s+", "-", s)
        s = re.sub(r"-{2,}", "-", s).strip("-")
        return s or "category"

    @staticmethod
    def slugify_anchor(text: str, seen: dict[str, int]) -> str:
        value = text.strip().lower()
        value = re.sub(r"`+", "", value)
        value = re.sub(r"[^\w\s\-]", "", value, flags=re.UNICODE)
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"-{2,}", "-", value).strip("-")
        if not value:
            value = "section"
        if value in seen:
            seen[value] += 1
            value = f"{value}-{seen[value]}"
        else:
            seen[value] = 1
        return value

    @staticmethod
    def select_pages_for_category(category: str, pages: list[dict]) -> list[dict]:
        cat_lower = category.lower()
        selected = []
        for page in pages:
            cats = page.get("categories") or []
            if isinstance(cats, str):
                cats_iter = [cats]
            else:
                cats_iter = cats
            if any(str(c).lower() == cat_lower for c in cats_iter):
                selected.append(page)
        return selected

    @staticmethod
    def union_pages(sets: list[list[dict]]) -> list[dict]:
        seen = set()
        out: list[dict] = []
        for lst in sets:
            for p in lst:
                slug = p.get("slug")
                if slug in seen:
                    continue
                seen.add(slug)
                out.append(p)
        return out

    def write_category_bundle(
        self,
        out_path: Path,
        category: str,
        includes_base: bool,
        base_categories: list[str],
        pages: list[dict],
        raw_base: str,
    ) -> None:
        """Concatenate pages into a single Markdown bundle."""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        total_words = sum(p.get("word_count", 0) for p in pages)
        total_tokens = sum(p.get("token_estimate", 0) for p in pages)

        fm_obj = {
            "category": category,
            "includes_base_categories": bool(includes_base),
            "base_categories": base_categories if includes_base else [],
            "word_count": total_words,
            "token_estimate": total_tokens,
            "page_count": len(pages),
        }
        fm_yaml = yaml.safe_dump(
            fm_obj, sort_keys=False, allow_unicode=True, width=4096
        ).strip()

        lines: list[str] = [f"---\n{fm_yaml}\n---\n"]
        lines.append(f"# Begin New Bundle: {category}")
        if includes_base and base_categories:
            lines.append(
                f"Includes shared base categories: {', '.join(base_categories)}"
            )
        lines.append("")

        for page in pages:
            lines.append("\n---\n")
            title = page.get("title") or page["slug"]
            lines.append(f"Page Title: {title}\n")
            lines.append(f"- Source (raw): {raw_base}/{page['slug']}.md")
            html_url = page.get("url")
            if html_url:
                lines.append(f"- Canonical (HTML): {html_url}")
            description = page.get("description")
            if description:
                lines.append(f"- Summary: {description}")
            lines.append(
                f"- Word Count: {page.get('word_count', 0)}; Token Estimate: {page.get('token_estimate', 0)}"
            )
            lines.append("")
            lines.append(page.get("body", "").strip())
            lines.append("")

        out_path.write_text("\n".join(lines), encoding="utf-8")

    def build_category_bundles(self, pages: list[dict], ai_root: Path) -> None:
        """Generate per-category bundle files based on AI pages."""
        content_cfg = self.llms_config.get("content", {})
        categories_order = content_cfg.get("categories_order") or []
        if not categories_order:
            log.info("[resolve_md] no categories configured; skipping bundles")
            return
        base_cats = content_cfg.get("base_context_categories") or []

        categories_dir = ai_root / "categories"
        self.reset_directory(categories_dir)

        raw_base = self.build_raw_base()

        base_sets = [self.select_pages_for_category(cat, pages) for cat in base_cats]
        base_union = self.union_pages(base_sets) if base_sets else []

        log.debug(
            f"[resolve_md] building category bundles for {len(categories_order)} categories; sample page cats: {pages[0].get('categories') if pages else 'none'}"
        )

        for category in categories_order:
            cat_slug = self.slugify_category(category)
            out_path = categories_dir / f"{cat_slug}.md"
            is_base = category in base_cats
            category_pages = self.select_pages_for_category(category, pages)

            if is_base:
                bundle_pages = sorted(
                    category_pages, key=lambda p: p.get("title", "").lower()
                )
                log.debug(
                    f"[resolve_md] base bundle {category}: {len(bundle_pages)} pages"
                )
                self.write_category_bundle(
                    out_path, category, False, base_cats, bundle_pages, raw_base
                )
            else:
                combined = self.union_pages([base_union, category_pages])
                bundle_pages = sorted(
                    combined, key=lambda p: p.get("title", "").lower()
                )
                log.debug(
                    f"[resolve_md] category bundle {category}: base={len(base_union)} cat-only={len(category_pages)} total={len(bundle_pages)}"
                )
                self.write_category_bundle(
                    out_path, category, True, base_cats, bundle_pages, raw_base
                )

        log.info(f"[resolve_md] category bundles written to {categories_dir}")

    # Create full-site content related AI artifact files
    def build_site_index(self, pages: list[dict], ai_root: Path) -> None:
        """Generate site-index.json and llms_full.jsonl from AI pages."""
        if not pages:
            return
        outputs = self.llms_config.get("outputs", {})
        files_cfg = outputs.get("files", {})
        site_index_name = files_cfg.get("site_index", "site-index.json")
        llms_full_name = files_cfg.get("llms_full", "llms-full.jsonl")
        preview_chars = outputs.get("preview_chars", 500)
        max_depth = outputs.get("outline_max_depth", 3)
        token_estimator = "heuristic-v1"

        index_path = ai_root / site_index_name
        llms_path = ai_root / llms_full_name
        index_path.parent.mkdir(parents=True, exist_ok=True)
        llms_path.parent.mkdir(parents=True, exist_ok=True)

        raw_base = self.build_raw_base()
        site_index: list[dict] = []
        jsonl_lines: list[str] = []

        for page in pages:
            body = page.get("body", "")
            outline, sections = self.extract_outline_and_sections(
                body, max_depth=max_depth
            )
            preview = self.extract_preview(body, max_chars=preview_chars) or page.get(
                "description", ""
            )
            total_section_tokens = 0
            for sec in sections:
                sec_tokens = self.estimate_tokens(sec["text"])
                total_section_tokens += sec_tokens
                jsonl_lines.append(
                    json.dumps(
                        {
                            "page_id": page["slug"],
                            "page_title": page.get("title"),
                            "index": sec["index"],
                            "depth": sec["depth"],
                            "title": sec["title"],
                            "anchor": sec["anchor"],
                            "start_char": sec["start_char"],
                            "end_char": sec["end_char"],
                            "estimated_token_count": sec_tokens,
                            "token_estimator": token_estimator,
                            "text": sec["text"],
                        },
                        ensure_ascii=False,
                    )
                )

            stats = {
                "word_count": page.get("word_count", 0),
                "token_estimate": page.get("token_estimate", total_section_tokens),
                "headings": len(outline),
                "sections_indexed": len(sections),
            }

            site_index.append(
                {
                    "id": page["slug"],
                    "title": page.get("title"),
                    "slug": page["slug"],
                    "categories": page.get("categories", []),
                    "raw_md_url": f"{raw_base}/{page['slug']}.md",
                    "html_url": page.get("url"),
                    "preview": preview,
                    "outline": outline,
                    "stats": stats,
                    "hash": self.sha256_text(body),
                    "token_estimator": token_estimator,
                }
            )

        index_path.write_text(
            json.dumps(site_index, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        with llms_path.open("w", encoding="utf-8") as fh:
            for line in jsonl_lines:
                fh.write(line + "\n")

        log.info(
            f"[resolve_md] site index written to {index_path} (pages={len(site_index)})"
        )
        log.info(
            f"[resolve_md] llms full JSONL written to {llms_path} (sections={len(jsonl_lines)})"
        )

    def build_llms_txt(self, pages: list[dict], docs_dir: Path) -> None:
        """Generate llms.txt listing raw markdown links grouped by category."""
        if not pages:
            return
        repo_cfg = self.llms_config.get("repository", {})
        ai_path = repo_cfg.get("ai_artifacts_path", "ai/pages").lstrip("/")
        raw_base = self.build_raw_base()

        project_cfg = self.llms_config.get("project", {})
        project_name = project_cfg.get("name", "Documentation")
        summary_line = project_cfg.get("project_url") or project_cfg.get(
            "docs_base_url", ""
        )

        content_cfg = self.llms_config.get("content", {})
        category_order = content_cfg.get("categories_order", []) or []

        output_rel = self.llms_config.get("llms_txt_output_path", "llms.txt")
        out_path = Path(output_rel)
        if not out_path.is_absolute():
            out_path = (docs_dir / out_path).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

        metadata_section = self.format_llms_metadata_section(pages)
        docs_section = self.format_llms_docs_section(pages, raw_base, category_order)
        summary_line = summary_line.strip()

        content_lines = [
            f"# {project_name}",
            f"\n> {summary_line}\n" if summary_line else "",
            "## How to Use This File",
            (
                "This file lists URLs for raw Markdown pages that complement the rendered pages on the documentation site. "
                "Use these Markdown files when prompting models to retain semantic context without HTML noise."
            ),
            "",
            metadata_section,
            docs_section,
        ]

        out_path.write_text(
            "\n".join(line for line in content_lines if line is not None),
            encoding="utf-8",
        )
        log.info(f"[resolve_md] llms.txt written to {out_path}")

    @staticmethod
    def format_llms_metadata_section(pages: list[dict]) -> str:
        distinct_categories = {
            cat for page in pages for cat in (page.get("categories") or [])
        }
        return "\n".join(
            [
                "## Metadata",
                f"- Documentation pages: {len(pages)}",
                f"- Categories: {len(distinct_categories)}",
                "",
            ]
        )

    @staticmethod
    def format_llms_docs_section(
        pages: list[dict], raw_base: str, category_order: list[str]
    ) -> str:
        grouped: dict[str, list[str]] = {}
        for page in pages:
            raw_url = f"{raw_base}/{page['slug']}.md"
            title = page.get("title") or page["slug"]
            description = page.get("description") or ""
            cats = page.get("categories") or ["Uncategorized"]
            line = f"- [{title}]({raw_url}): {description}"
            for cat in cats:
                grouped.setdefault(cat, []).append(line)

        lines = [
            "## Docs",
            "This section lists documentation pages by category. Each entry links to a raw markdown version of the page and includes a short description.",
        ]
        seen = set()
        for cat in category_order:
            entries = grouped.get(cat)
            if not entries:
                continue
            lines.append(f"\nDocs: {cat}")
            lines.extend(entries)
            seen.add(cat)

        remaining = sorted(cat for cat in grouped if cat not in seen)
        for cat in remaining:
            lines.append(f"\nDocs: {cat}")
            lines.extend(grouped[cat])

        return "\n".join(lines)

    @staticmethod
    def normalize_branch(name: str) -> str:
        return (
            name.replace("refs/heads/", "", 1)
            if name and name.startswith("refs/heads/")
            else name
        )

    def build_raw_base(self) -> str:
        """Return base URL for raw markdown artifacts on GitHub."""
        repo = self.llms_config.get("repository", {})
        org = repo.get("org", "")
        name = repo.get("repo", "")
        branch = self.normalize_branch(repo.get("default_branch", "main"))
        ai_path = repo.get("ai_artifacts_path")
        if not ai_path:
            outputs = self.llms_config.get("outputs", {})
            public_root = outputs.get("public_root", "/ai/").strip("/")
            pages_dir = outputs.get("files", {}).get("pages_dir", "pages").strip("/")
            ai_path = f"{public_root}/{pages_dir}"
        ai_path = ai_path.strip("/")
        return f"https://raw.githubusercontent.com/{org}/{name}/{branch}/{ai_path}"
