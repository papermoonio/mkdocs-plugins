"""
An MkDocs plugin to minify HTML, JS or CSS files prior to being written to disk
"""

import hashlib
from pathlib import Path
import os
from typing import Callable, Dict, List, Optional, Tuple, Union
import fnmatch
import re
import logging

import csscompressor
import htmlmin
import jsmin
import mkdocs.config.config_options
from mkdocs.config import config_options as c
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import BasePlugin
from mkdocs.structure.pages import Page
from packaging import version

# Use MkDocs' recommended plugin logger namespace so debug logs appear only with `--verbose`.
logger = logging.getLogger(f"mkdocs.plugins.{__name__}")

# Maps asset type to the MkDocs config key that lists additional assets to inject.
# JS files are defined under `extra_javascript`, CSS under `extra_css`.
EXTRAS: Dict[str, str] = {
    "js": "extra_javascript",
    "css": "extra_css",
}

# Minifier dispatch table for JS/CSS. HTML is handled via `htmlmin2` package.
MINIFIERS: Dict[str, Callable] = {
    "js": jsmin.jsmin,
    "css": csscompressor.compress,
}

# Compatibility: csscompressor<=0.9.5. Preserve whitespace in url() to avoid breaking SVG data URIs.
if version.parse(csscompressor.__version__) <= version.parse("0.9.5"):
    # Monkey patch csscompressor 0.9.5
    # See https://github.com/sprymix/csscompressor/issues/9#issuecomment-1024417374
    _preserve_call_tokens_original = csscompressor._preserve_call_tokens
    _url_re = csscompressor._url_re

    def my_new_preserve_call_tokens(*args, **kwargs):
        """If regex is for url pattern, switch the keyword remove_ws to False.
        This preserves svg code in url() pattern of CSS files for old versions."""
        if _url_re == args[1]:
            kwargs["remove_ws"] = False
        return _preserve_call_tokens_original(*args, **kwargs)

    csscompressor._preserve_call_tokens = my_new_preserve_call_tokens

    assert csscompressor._preserve_call_tokens == my_new_preserve_call_tokens


class MinifyPlugin(BasePlugin):
    """MkDocs plugin that minifies HTML output and/or extra JS/CSS assets.

    Configuration options (all optional):
    - minify_html (bool): Minify rendered HTML pages.
    - minify_js (bool): Minify user-provided JS files listed in `js_files` and rewrite references.
    - minify_css (bool): Minify user-provided CSS files listed in `css_files` and rewrite references.
    - js_files (str|list): Relative paths (under site_dir) or glob patterns of JS assets to process.
    - css_files (str|list): Relative paths (under site_dir) or glob patterns of CSS assets to process.
    - htmlmin_opts (dict): Extra options forwarded to `htmlmin.minify` (safely merged).
    - cache_safe (bool): Enable cache-busting by hashing asset contents and inserting the hash into
      filenames; also precomputes data/hashes in `on_pre_build` to avoid race conditions.
    - scoped_css (dict): Optional mapping of glob patterns to lists of CSS files to apply only on matching pages.
      These CSS files are minified/hashed and applied per-page; they are NOT injected globally via `extra_css`.
    """

    # MkDocs plugin configuration schema so MkDocs recognizes our options in mkdocs.yml
    config_scheme = (
        ('minify_html', c.Type(bool, default=False)),
        ('minify_js',   c.Type(bool, default=False)),
        ('minify_css',  c.Type(bool, default=False)),
        ('js_files',    c.Type((str, list), default=[])),
        ('css_files',   c.Type((str, list), default=[])),
        ('htmlmin_opts',c.Type(dict, default={})),
        ('cache_safe',  c.Type(bool, default=False)),
        ('scoped_css',  c.Type(dict, default={})),
        ('scoped_css_templates', c.Type(dict, default={})),
        ('debug', c.Type(bool, default=False)),
    )

    # Cache of content hashes per original relative path, used to generate cache-safe names.
    path_to_hash: Dict[str, str] = {}
    """
    The file hash is stored once per normalized path (no leading '/').
    """

    # Cache of file contents for later write-out in on_post_build when cache_safe is enabled.
    path_to_data: Dict[str, str] = {}
    """
    The file data is stored once per normalized path (no leading '/').
    """

    def __init__(self):
        super().__init__()
        # Per-build tracking: template_name -> base -> replaced_count
        # Used to decide whether the post_build templates scan needs to run as a true fallback.
        self._tpl_rewrite_replaced: Dict[str, Dict[str, int]] = {}

    def _tpl_replaced_in_post_template(self, base: str) -> bool:
        """Return True if on_post_template already replaced at least one link for this basename."""
        for _tpl, by_base in (self._tpl_rewrite_replaced or {}).items():
            if int(by_base.get(base, 0)) > 0:
                return True
        return False

    # -------------------------------
    # Helpers
    # -------------------------------

    def _debug_enabled(self) -> bool:
        return bool(self.config.get("debug", False))

    def _dbg(self, msg: str, *args) -> None:
        """Debug log gated by plugin config.

        MkDocs only shows DEBUG when run with `-v/--verbose`.
        """
        if not self._debug_enabled():
            return

        logger.debug("[minify] " + msg, *args)

    def _extract_line_with(self, text: str, needle: str) -> str:
        """Return a single line from `text` containing `needle` (trimmed), or ""."""
        if not text or not needle:
            return ""
        idx = text.find(needle)
        if idx == -1:
            return ""
        start = text.rfind("\n", 0, idx)
        end = text.find("\n", idx)
        if start == -1:
            start = 0
        else:
            start += 1
        if end == -1:
            end = len(text)
        line = text[start:end].strip()
        if len(line) > 240:
            line = line[:240] + "…"
        return line

    def _dbg_hash_missing(self, rel_css: str, final_rel: str) -> None:
        """Debug helper to surface missing hash/data situations."""
        if not self._debug_enabled():
            return
        self._dbg("[hash] missing hash for %s -> final=%s", rel_css, final_rel)

    def _gather_scoped_css_files(self) -> List[str]:
        """Return a de-duplicated list of CSS paths referenced in either `scoped_css`
        (per-page) or `scoped_css_templates` (per-template). Paths are normalized
        to be relative (no leading '/'), preserving first-seen order.
        """
        files: List[str] = []

        for mapping_name in ("scoped_css", "scoped_css_templates"):
            scoped = self.config.get(mapping_name) or {}
            for paths in scoped.values():
                if not paths:
                    continue
                if isinstance(paths, str):
                    files.append(paths.lstrip('/'))
                else:
                    files.extend(p.lstrip('/') for p in paths)

        seen = set()
        out: List[str] = []
        for p in files:
            if p not in seen:
                seen.add(p)
                out.append(p)
        return out

    def _minified_asset(self, file_name: str, file_type: str, file_hash: str) -> str:
        """Return asset filename with optional hash and `.min` suffix."""
        hash_part: str = f".{file_hash[:6]}" if file_hash else ""
        min_part: str = ".min" if self.config.get(f"minify_{file_type}", False) else ""
        return file_name.replace(f".{file_type}", f"{hash_part}{min_part}.{file_type}")

    @staticmethod
    def _minify_file_data_with_func(file_data: str, minify_func: Callable) -> str:
        """Run the correct minifier with safe parameters."""
        if minify_func.__name__ == "jsmin":
            return minify_func(file_data, quote_chars="'\"`")
        else:
            return minify_func(file_data)

    # -------------------------------
    # Asset processing
    # -------------------------------

    def _minify(self, file_type: str, config: MkDocsConfig) -> None:
        """Minify assets of a given type ("js" or "css") and rename on disk."""
        minify_func: Callable = MINIFIERS[file_type]
        self._dbg("[minify] start type=%s cache_safe=%s", file_type, bool(self.config.get("cache_safe", False)))
        file_paths: Union[str, List[str]] = self.config.get(f"{file_type}_files") or []

        # Normalize to a list so we can iterate uniformly.
        if not isinstance(file_paths, list):
            file_paths = [file_paths]

        # Work under the build output directory (already rendered/copied by MkDocs).
        site_dir = Path(config['site_dir'])
        self._dbg("[minify] site_dir=%s", site_dir.as_posix())

        # Expand simple one-segment globs like "assets/*.css" relative to site_dir.
        file_paths2: List[Path] = []
        for fp in file_paths:
            if "*" in fp:
                glob_parts = fp.split("*", maxsplit=1)
                glob_dir = site_dir / Path(glob_parts[0].lstrip('/'))
                for glob_file in glob_dir.glob(f"*{glob_parts[1]}"):
                    file_paths2.append(glob_file)
            else:
                file_paths2.append(site_dir / fp.lstrip('/'))

        self._dbg("[minify] expanded targets (pre-dedupe) count=%d", len(file_paths2))
        # Remove duplicates to avoid double-processing.
        file_paths2 = list(set(file_paths2))
        self._dbg("[minify] targets (deduped) count=%d", len(file_paths2))

        for file_path in file_paths2:
            site_file_path: str = str(file_path.as_posix())
            rel_file_path: str = site_file_path.replace(site_dir.as_posix(), "").strip("/")
            self._dbg("[minify] processing %s", rel_file_path)

            # Open the built asset and either write cached data or minified content.
            with open(site_file_path, mode="r+", encoding="utf8") as f:
                if self.config.get("cache_safe", False):
                    f.write(self.path_to_data[rel_file_path])
                else:
                    minified: str = self._minify_file_data_with_func(f.read(), minify_func)
                    f.seek(0)
                    f.write(minified)
                f.truncate()

            # Retrieve precomputed hash (if any) for cache-safe renaming.
            file_hash: str = self.path_to_hash.get(rel_file_path, "")

            # Finalize by renaming the file to include `.min` and/or the hash.
            new_path = self._minified_asset(site_file_path, file_type, file_hash)
            self._dbg("[minify] rename %s -> %s", site_file_path, new_path)
            os.rename(site_file_path, new_path)

    def _minify_html_page(self, output: str) -> Optional[str]:
        """Minify HTML using plugin config and merged options."""
        output_opts: Dict[str, Union[bool, str, Tuple[str, ...]]] = {
            "remove_comments": False,
            "remove_empty_space": False,
            "remove_all_empty_space": False,
            "reduce_empty_attributes": True,
            "reduce_boolean_attributes": False,
            "remove_optional_attribute_quotes": False,
            "convert_charrefs": True,
            "keep_pre": False,
            "pre_tags": ("pre", "textarea"),
            "pre_attr": "pre",
        }

        selected_opts: Dict = self.config.get("htmlmin_opts", {}) or {}
        for key in selected_opts:
            if key in output_opts:
                output_opts[key] = selected_opts[key]
            else:
                logger.warning("htmlmin option '%s' not recognized", key)

        return htmlmin.minify(output, **output_opts)

    def _minify_extra_config(self, file_type: str, config: MkDocsConfig) -> None:
        """Rewrite extra assets to point to minified/hashed names. With `cache_safe`,
        compute hash and store data in-memory during `on_pre_build`."""
        files_to_minify: Union[str, List[str]] = self.config.get(f"{file_type}_files") or []
        minify_func: Callable = MINIFIERS[file_type]
        minify_flag: bool = self.config.get(f"minify_{file_type}", False)
        extra: str = EXTRAS[file_type]
        self._dbg("[extra_config] start type=%s extra_key=%s cache_safe=%s minify=%s", file_type, extra, bool(self.config.get("cache_safe", False)), bool(self.config.get(f"minify_{file_type}", False)))

        if not isinstance(files_to_minify, list):
            files_to_minify = [files_to_minify]

        norm_targets = {
            (p if isinstance(p, str) else str(p)).lstrip('/')
            for p in (files_to_minify if isinstance(files_to_minify, list) else [files_to_minify])
        }

        for i, extra_item in enumerate(config[extra]):
            raw = str(extra_item)
            had_leading = raw.startswith('/')
            norm = raw.lstrip('/')
            self._dbg("[extra_config] candidate extra[%d]=%s (norm=%s)", i, raw, norm)

            if norm not in norm_targets:
                continue

            file_hash: str = ""

            if self.config.get("cache_safe", False):
                docs_file_path: str = f"{config['docs_dir']}/{norm}".replace("\\", "/")
                theme = config.theme

                # Since MkDocs 1.5.0, theme.custom_dir is available for direct access
                if not hasattr(theme, "custom_dir"):
                    for user_config in config.user_configs:
                        user_config: Dict
                        custom_dir: str = user_config.get("theme", {}).get("custom_dir", "")
                        temp_path: str = f"{custom_dir}/{norm}".replace("\\", "/")
                        if custom_dir and os.path.exists(temp_path):
                            docs_file_path = temp_path
                            break
                elif theme.custom_dir:
                    temp_path: str = f"{theme.custom_dir}/{norm}".replace("\\", "/")
                    if os.path.exists(temp_path):
                        docs_file_path = temp_path

                with open(docs_file_path, encoding="utf8") as f:
                    file_data: str = f.read()

                    if minify_flag:
                        file_data = self._minify_file_data_with_func(file_data, minify_func)

                    self.path_to_data[norm] = file_data

                file_hash = hashlib.sha384(file_data.encode("utf8")).hexdigest()
                # store hash for use in `on_post_build`
                self.path_to_hash[norm] = file_hash

            new_file_path = self._minified_asset(norm, file_type, file_hash)
            if had_leading:
                new_file_path = '/' + new_file_path.lstrip('/')
            self._dbg("[extra_config] rewrite %s -> %s", raw, new_file_path)

            if isinstance(extra_item, str):
                config[extra][i] = new_file_path
            else:  # MkDocs 1.5: ExtraScriptValue.path
                extra_item.path = new_file_path

    # -------------------------------
    # Scoped CSS (per-page injection / replacement)
    # -------------------------------

    def _html_references_original_scoped_css(self, html: str, rel_css: str) -> bool:
        """True if HTML still references the original scoped CSS (path or basename)."""
        if not html:
            return False
        rel_css_norm = rel_css.lstrip("/")
        base = os.path.basename(rel_css_norm)
        return (rel_css_norm in html) or (base in html)

    def _can_delete_original_scoped_css(self, site_dir: Path, rel_css: str) -> bool:
        """Return True if no built HTML references the original CSS anymore."""
        rel_css_norm = rel_css.lstrip("/")
        for html_file in site_dir.rglob("*.html"):
            try:
                html = html_file.read_text(encoding="utf8")
            except Exception:
                continue
            if self._html_references_original_scoped_css(html, rel_css_norm):
                return False
        return True

    def _inject_scoped_css(self, output: str, *, page: Page, config: MkDocsConfig) -> str:
        """Inject or replace page-scoped CSS links when patterns match."""
        scoped_css_config = self.config.get("scoped_css")
        if not scoped_css_config:
            return output

        src_path = getattr(page.file, "src_path", "") or ""
        url = (getattr(page, "url", "") or "").lstrip("/")
        if url == "" or url.endswith("/"):
            url_html = (url + "index.html").lstrip("/")
        else:
            url_html = url
        dest_path = getattr(getattr(page, "file", None), "dest_path", "") or url_html
        url_path = url.rstrip("/")

        self._dbg("[scoped_css/page] page src=%s url=%s dest=%s", src_path, url, dest_path)

        depth = max(0, url_html.strip("/").count("/"))
        rel_prefix = "" if depth == 0 else "../" * depth

        css_files_to_process: List[str] = []
        for pattern, css_files in scoped_css_config.items():
            if not css_files:
                continue
            # Accept selectors matching any of the targets
            matches = (
                fnmatch.fnmatch(src_path, pattern)
                or fnmatch.fnmatch(dest_path, pattern)
                or fnmatch.fnmatch(url_html, pattern)
                or fnmatch.fnmatch(url_path, pattern)
            )
            if matches:
                self._dbg("[scoped_css/page] matched pattern=%s", pattern)
            if not matches:
                continue
            # css_files can be str or list
            if isinstance(css_files, str):
                css_files_to_process.append(css_files)
            else:
                css_files_to_process.extend(css_files)

        if not css_files_to_process:
            return output

        self._dbg("[scoped_css/page] css_files_to_process=%s", ",".join([c.lstrip('/') for c in css_files_to_process]))

        links_to_inject: List[str] = []
        for css_file in css_files_to_process:
            norm_css = css_file.lstrip('/')
            file_hash = self.path_to_hash.get(norm_css, "")
            final_name = self._minified_asset(norm_css, "css", file_hash)  # e.g., assets/.../home.<hash>.min.css
            if file_hash == "":
                self._dbg_hash_missing(norm_css, final_name)            
            basename = os.path.basename(css_file)  # e.g., home.css

            # Regex to capture an existing <link rel="stylesheet" href="...basename"> and replace href value.
            # Groups: 1) prefix up to href value, 2) href value, 3) rest of tag
            pattern = re.compile(
                rf'(<link\b[^>]*?\bhref\s*=\s*)(["\']?)([^"\'>\s]*?{re.escape(basename)})(\2)?([^>]*>)',
                re.IGNORECASE,
            )

            def _sub_href(m: re.Match) -> str:
                orig_href = m.group(3)
                quote = m.group(2) or ""
                tail_quote = m.group(4) or ""
                tail_rest = m.group(5)

                if orig_href.startswith("/"):
                    new_href = "/" + final_name.lstrip("/")
                else:
                    new_href = f"{rel_prefix}{final_name}"

                return f"{m.group(1)}{quote}{new_href}{tail_quote}{tail_rest}"

            new_output, replaced_count = pattern.subn(_sub_href, output)
            if replaced_count > 0:
                self._dbg("[scoped_css/page] replaced existing link basename=%s -> %s", basename, final_name)
                output = new_output
            else:
                self._dbg("[scoped_css/page] will inject link basename=%s -> %s", basename, final_name)
                href = f"{rel_prefix}{final_name}"
                links_to_inject.append(f'<link rel="stylesheet" href="{href}">')

        if links_to_inject:
            # Inject pending links just before </head>; if no </head>, prepend as fallback.
            insert_pos = output.lower().rfind("</head>")
            if insert_pos != -1:
                output = output[:insert_pos] + "\n    " + "\n    ".join(links_to_inject) + "\n" + output[insert_pos:]
            else:
                output = "\n".join(links_to_inject) + "\n" + output

        return output

    # -------------------------------
    # MkDocs hooks
    # -------------------------------

    def on_post_page(self, output: str, *, page: Page, config: MkDocsConfig) -> Optional[str]:
        """Minify rendered HTML and apply scoped CSS for Markdown pages."""
        self._dbg("[post_page] start page=%s", getattr(page, "url", ""))
        if self.config.get("minify_html", False):
            output = self._minify_html_page(output)
            self._dbg("[post_page] minified HTML")
        output = self._inject_scoped_css(output, page=page, config=config)
        self._dbg("[post_page] done")
        return output

    def on_pre_build(self, *, config: MkDocsConfig) -> None:
        """Before build: prepare config rewrites and optionally compute hashes."""
        self._dbg("[pre_build] start minify_html=%s minify_js=%s minify_css=%s cache_safe=%s", bool(self.config.get("minify_html", False)), bool(self.config.get("minify_js", False)), bool(self.config.get("minify_css", False)), bool(self.config.get("cache_safe", False)))
        if self.config.get("minify_js", False) or self.config.get("cache_safe", False):
            self._minify_extra_config("js", config)
        if self.config.get("minify_css", False) or self.config.get("cache_safe", False):
            self._minify_extra_config("css", config)

        scoped_files = self._gather_scoped_css_files()
        for rel_css in scoped_files:
            docs_file_path: str = f"{config['docs_dir']}/{rel_css}".replace("\\", "/")
            theme = config.theme
            found = False
            if not hasattr(theme, "custom_dir"):
                for user_config in config.user_configs:
                    user_config: Dict
                    custom_dir: str = user_config.get("theme", {}).get("custom_dir", "")
                    temp_path: str = f"{custom_dir}/{rel_css}".replace("\\", "/")
                    if custom_dir and os.path.exists(temp_path):
                        docs_file_path = temp_path
                        found = True
                        break
            elif theme.custom_dir:
                temp_path: str = f"{theme.custom_dir}/{rel_css}".replace("\\", "/")
                if os.path.exists(temp_path):
                    docs_file_path = temp_path
                    found = True
            if not found and not os.path.exists(docs_file_path):
                self._dbg("[pre_build] scoped CSS missing on disk: %s (tried=%s)", rel_css, docs_file_path)
                continue

            with open(docs_file_path, encoding="utf8") as f:
                data = f.read()
            if self.config.get("minify_css", False):
                data = self._minify_file_data_with_func(data, MINIFIERS["css"])
            file_hash = hashlib.sha384(data.encode("utf8")).hexdigest()
            self.path_to_hash[rel_css] = file_hash
            self.path_to_data[rel_css] = data
            self._dbg("[pre_build] cached scoped CSS %s hash=%s", rel_css, file_hash[:8])
        self._dbg("[pre_build] done scoped_files=%d", len(scoped_files))

    def on_post_build(self, *, config: MkDocsConfig) -> None:
        """After build: write minified assets and perform renames."""
        self._dbg("[post_build] start")
        if self.config.get("minify_js", False) or self.config.get("cache_safe", False):
            self._minify("js", config)
        if self.config.get("minify_css", False) or self.config.get("cache_safe", False):
            self._minify("css", config)

        scoped_files = self._gather_scoped_css_files()
        if scoped_files:
            site_dir = Path(config['site_dir'])

            for rel_css in scoped_files:
                data = self.path_to_data.get(rel_css)
                if data is None:
                    continue
                file_hash = self.path_to_hash.get(rel_css, "")
                final_rel = self._minified_asset(rel_css, "css", file_hash)
                final_abs = site_dir / final_rel
                final_abs.parent.mkdir(parents=True, exist_ok=True)
                final_abs.write_text(data, encoding="utf8")
                self._dbg("[post_build] wrote scoped CSS %s", final_rel)

            scoped_map = self.config.get("scoped_css") or {}
            if scoped_map:
                final_by_basename: Dict[str, str] = {}
                for rel_css in scoped_files:
                    base = os.path.basename(rel_css)
                    final_by_basename[base] = self._minified_asset(
                        rel_css, "css", self.path_to_hash.get(rel_css, "")
                    )

                for html_file in site_dir.rglob('*.html'):
                    rel_html = html_file.relative_to(site_dir).as_posix()
                    self._dbg("[post_build] scanning HTML %s", rel_html)

                    matched_css: List[str] = []
                    for pattern, css_list in scoped_map.items():
                        if fnmatch.fnmatch(rel_html, pattern):
                            if isinstance(css_list, str):
                                matched_css.append(css_list.lstrip('/'))
                            else:
                                matched_css.extend(p.lstrip('/') for p in css_list)

                    if not matched_css:
                        self._dbg("[post_build] no scoped_css match for %s", rel_html)
                        continue

                    html = html_file.read_text(encoding='utf8')
                    depth = rel_html.count('/')
                    rel_prefix = '' if depth == 0 else '../' * depth

                    links_to_inject: List[str] = []
                    for rel_css in matched_css:
                        base = os.path.basename(rel_css)
                        final_rel = final_by_basename.get(base)
                        if not final_rel:
                            continue

                        self._dbg("[post_build] want CSS %s (base=%s) -> %s", rel_css, base, final_rel)
                        pat = re.compile(
                            rf'(<link\b[^>]*?\bhref\s*=\s*)(["\']?)([^"\'>\s]*?{re.escape(base)})(\2)?([^>]*>)',
                            re.IGNORECASE,
                        )
                        def _sub_href(m: re.Match) -> str:
                            orig = m.group(3)
                            quote = m.group(2) or ""
                            tail_quote = m.group(4) or ""
                            tail_rest = m.group(5)

                            if orig.startswith('/'):
                                new_href = '/' + final_rel.lstrip('/')
                            else:
                                new_href = f"{rel_prefix}{final_rel}"
                            return f"{m.group(1)}{quote}{new_href}{tail_quote}{tail_rest}"

                        new_html, replaced = pat.subn(_sub_href, html)
                        if replaced > 0:
                            self._dbg("[post_build] replaced link base=%s in %s", base, rel_html)
                        else:
                            self._dbg("[post_build] will inject link base=%s into %s", base, rel_html)
                        html = new_html
                        if replaced == 0:
                            href = f"/{final_rel.lstrip('/')}" if rel_prefix == '' else f"{rel_prefix}{final_rel}"
                            links_to_inject.append(f'<link rel="stylesheet" href="{href}">')

                    if links_to_inject:
                        insert_pos = html.lower().rfind('</head>')
                        if insert_pos != -1:
                            html = html[:insert_pos] + "\n    " + "\n    ".join(links_to_inject) + "\n" + html[insert_pos:]
                        else:
                            html = "\n".join(links_to_inject) + "\n" + html

                    html_file.write_text(html, encoding='utf8')

        # Replace-only pass for scoped_css_templates: do not inject, only replace existing links.
        tpl_map = self.config.get("scoped_css_templates") or {}
        if tpl_map:
            site_dir = Path(config['site_dir'])
            tpl_stats: Dict[str, Dict[str, Union[int, bool]]] = {}            

            # Build a de-duplicated list of CSS paths from the templates map
            tpl_css: List[str] = []
            for paths in tpl_map.values():
                if not paths:
                    continue
                if isinstance(paths, str):
                    tpl_css.append(paths.lstrip('/'))
                else:
                    tpl_css.extend(p.lstrip('/') for p in paths)

            # Precompute basename -> final rel path for quick replacement
            tpl_final_by_basename: Dict[str, str] = {}
            for rel_css in tpl_css:
                base = os.path.basename(rel_css)
                file_hash = self.path_to_hash.get(rel_css, "")
                final_rel = self._minified_asset(rel_css, "css", file_hash)
                tpl_final_by_basename[base] = final_rel
                if file_hash == "":
                    self._dbg_hash_missing(rel_css, final_rel)
            # Fallback gating: if on_post_template already replaced links for a basename,
            # skip scanning all HTML files for that basename.
            skipped_bases: List[str] = []
            for base in list(tpl_final_by_basename.keys()):
                if self._tpl_replaced_in_post_template(base):
                    skipped_bases.append(base)
                    tpl_final_by_basename.pop(base, None)

            for base in skipped_bases:
                self._dbg("[post_build/templates] fallback skipped base=%s (already replaced in on_post_template)", base)

            if not tpl_final_by_basename:
                self._dbg("[post_build/templates] fallback skipped (all bases already replaced in on_post_template)")
            else:
                for base in tpl_final_by_basename.keys():
                    tpl_stats[base] = {"found": 0, "replaced": 0, "fallback_injected": 0, "sample_logged": False}

                # Scan every generated HTML and replace hrefs that match any of the basenames
                for html_file in site_dir.rglob('*.html'):
                    rel_html = html_file.relative_to(site_dir).as_posix()
                    self._dbg("[post_build/templates] scanning HTML %s", rel_html)
                    html = html_file.read_text(encoding='utf8')
                    original_html = html

                    for base, final_rel in tpl_final_by_basename.items():
                        if base in html:
                            tpl_stats[base]["found"] += 1
                        self._dbg("[post_build/templates] trying base=%s in %s", base, rel_html)

                        # Strict pattern: require rel=stylesheet somewhere, and match href with or without quotes
                        strict_pat = re.compile(
                            rf'(<link\b(?=[^>]*\brel=(?:["\']?)stylesheet(?:["\']?))[^>]*?\bhref\s*=\s*)(["\']?)([^"\'>\s]*{re.escape(base)})(\2)?([^>]*>)',
                            re.IGNORECASE,
                        )

                        def _sub(m: re.Match) -> str:
                            orig = m.group(3)
                            quote = m.group(2) or ''
                            tail_quote = m.group(4) or ''
                            tail_rest = m.group(5)
                            # Keep absolute if original was absolute; otherwise use a path relative to the file
                            if orig.startswith('/'):
                                new_href = '/' + final_rel.lstrip('/')
                            else:
                                depth = rel_html.count('/')
                                rel_prefix = '' if depth == 0 else '../' * depth
                                new_href = f"{rel_prefix}{final_rel}"
                            return f"{m.group(1)}{quote}{new_href}{tail_quote}{tail_rest}"

                        new_html, replaced = strict_pat.subn(_sub, html)
                        if replaced > 0:
                            tpl_stats[base]["replaced"] += replaced
                            self._dbg("[post_build/templates] replaced base=%s in %s [strict] count=%d", base, rel_html, replaced)
                            html = new_html
                        else:
                            # Fallback: broad pattern without requiring rel=stylesheet; also matches unquoted href
                            self._dbg("[post_build/templates] strict missed base=%s in %s; trying fallback", base, rel_html)
                            broad_pat = re.compile(
                                rf'(<link\b[^>]*?\bhref\s*=\s*)(["\']?)([^"\'>\s]*?{re.escape(base)})(\2)?([^>]*>)',
                                re.IGNORECASE,
                            )
                            new_html2, replaced2 = broad_pat.subn(_sub, html)
                            if replaced2 > 0:
                                tpl_stats[base]["replaced"] += replaced2
                                self._dbg("[post_build/templates] replaced base=%s in %s [fallback] count=%d", base, rel_html, replaced2)
                                html = new_html2
                            else:
                                self._dbg("[post_build/templates] no link matched base=%s in %s", base, rel_html)
                                if (base in html) and (not tpl_stats[base]["sample_logged"]):
                                    line = self._extract_line_with(html, base)
                                    if line:
                                        self._dbg("[post_build/templates] sample line for base=%s: %s", base, line)
                                        tpl_stats[base]["sample_logged"] = True

                    if html is not original_html:
                        html_file.write_text(html, encoding='utf8')
                if self._debug_enabled():
                    try:
                        for base, s in tpl_stats.items():
                            self._dbg(
                                "[post_build/templates] summary base=%s found_in_html_files=%d replaced=%d fallback_injected=%d",
                                base,
                                int(s.get("found", 0)),
                                int(s.get("replaced", 0)),
                                int(s.get("fallback_injected", 0)),
                            )
                    except Exception:
                        pass

        # Cleanup: delete original scoped CSS if it's no longer referenced by any HTML.
        if scoped_files:
            site_dir = Path(config["site_dir"])
            for rel_css in scoped_files:
                rel_css_norm = rel_css.lstrip("/")
                original_abs = site_dir / rel_css_norm

                if not original_abs.exists():
                    continue

                if self._can_delete_original_scoped_css(site_dir, rel_css_norm):
                    try:
                        original_abs.unlink()
                        self._dbg("[cleanup] deleted original scoped CSS %s", rel_css_norm)
                    except Exception as e:
                        self._dbg("[cleanup] failed to delete %s: %s", rel_css_norm, str(e))
                else:
                    self._dbg("[cleanup] kept original scoped CSS %s (still referenced by HTML)", rel_css_norm)

        self._dbg("[post_build] done")

    def on_post_template(self, output_content: str, *, template_name: str, config: MkDocsConfig) -> Optional[str]:
        """Minify HTML templates (home.html, 404.html, index-page.html, etc.) and
        apply scoped CSS replacement/injection when `scoped_css_templates` patterns match.

        Rules:
          - If template's HTML already has <link rel="stylesheet" href="...basename.css">,
            we REPLACE the href with the final minified/hashed name.
          - If not present, we INJECT a new <link> just before </head>.
          - Absolute hrefs remain absolute (/assets/..); relative become root-relative for templates.
        """
        self._dbg("[post_template] template=%s", template_name)
        # Minify template HTML if enabled
        if self.config.get("minify_html", False):
            output_content = self._minify_html_page(output_content) or output_content

        tpl_map = self.config.get("scoped_css_templates") or {}
        if not tpl_map:
            return output_content

        # Match template name against provided patterns (supports globs)
        matched_css: List[str] = []
        for pattern, css_list in tpl_map.items():
            if fnmatch.fnmatch(template_name, pattern):
                if isinstance(css_list, str):
                    matched_css.append(css_list.lstrip('/'))
                else:
                    matched_css.extend(p.lstrip('/') for p in css_list)

        if not matched_css:
            self._dbg("[post_template] no scoped_css_templates match for %s", template_name)
            return output_content

        links_to_inject: List[str] = []
        for rel_css in matched_css:
            base = os.path.basename(rel_css)
            file_hash = self.path_to_hash.get(rel_css, "")
            final_rel = self._minified_asset(rel_css, "css", file_hash)  # e.g. assets/.../home.<hash>.min.css
            if file_hash == "":
                self._dbg_hash_missing(rel_css, final_rel)   
            self._dbg("[post_template] processing CSS %s -> %s", rel_css, final_rel)
            pattern_re = re.compile(
                rf'(<link\b[^>]*?\bhref\s*=\s*)(["\']?)([^"\'>\s]*?{re.escape(base)})(\2)?([^>]*>)',
                re.IGNORECASE,
            )

            def _sub_href(m: re.Match) -> str:
                orig_href = m.group(3)
                quote = m.group(2) or ''
                tail_quote = m.group(4) or ''
                tail_rest = m.group(5)
                # For templates, write root-relative path
                new_href = "/" + final_rel.lstrip("/")
                return f"{m.group(1)}{quote}{new_href}{tail_quote}{tail_rest}"

            found_in_html = base in output_content
            new_html, replaced_count = pattern_re.subn(_sub_href, output_content)
            # Track replacements so post_build templates scan can act as a true fallback.
            self._tpl_rewrite_replaced.setdefault(template_name, {})
            self._tpl_rewrite_replaced[template_name][base] = (
                int(self._tpl_rewrite_replaced[template_name].get(base, 0)) + int(replaced_count)
            )
            if replaced_count > 0:
                self._dbg("[post_template] base=%s found_in_html=%s replaced=%d injected=0", base, found_in_html, replaced_count)
                output_content = new_html
            else:
                self._dbg("[post_template] base=%s found_in_html=%s replaced=0 injected=1", base, found_in_html)
                if found_in_html:
                    line = self._extract_line_with(output_content, base)
                    if line:
                        self._dbg("[post_template] sample line for base=%s: %s", base, line)
                links_to_inject.append(f'<link rel="stylesheet" href="/{final_rel.lstrip("/")}">')

        if links_to_inject:
            insert_pos = output_content.lower().rfind("</head>")
            if insert_pos != -1:
                output_content = (
                    output_content[:insert_pos]
                    + "\n    "
                    + "\n    ".join(links_to_inject)
                    + "\n"
                    + output_content[insert_pos:]
                )
            else:
                output_content = "\n".join(links_to_inject) + "\n" + output_content

        self._dbg("[post_template] done")
        return output_content