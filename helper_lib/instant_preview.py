from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, NavigableString, Tag

HEADING_NAMES = {f"h{level}" for level in range(1, 7)}
DEFAULT_EXCLUDE_SELECTORS = (
    ".ai-file-actions-container",
    ".feedback-actions-container",
    ".md-feedback",
    ".md-source-file",
    ".toggle-buttons",
)
DATA_ATTR = "data-instant-preview-data"
MANIFEST_ATTR = "data-instant-preview-manifest"
TEMPLATE_ATTR = "data-instant-preview-template"
EXCLUDE_ATTR = "data-instant-preview-exclude"
BLOCK_LIMIT = 6
MAX_TOTAL_TEXT_CHARS = 1400
MAX_CODE_LINES = 10
MAX_TABLE_ROWS = 3
MAX_CARD_ITEMS = 3
MAX_DETAILS_BLOCKS = 4
MIN_TRUNCATED_BLOCK_CHARS = 72
BLOCKED_CLASS_NAMES = {
    "ai-file-actions-container",
    "feedback-actions-container",
    "glightbox",
    "md-content__button",
    "md-feedback",
    "md-source-file",
    "page-actions-title",
    "toggle-buttons",
}
PRESERVE_BLOCK_CLASS_NAMES = {
    "admonition",
    "page-header-row",
    "status-badge",
    "tabbed-content",
    "tabbed-labels",
    "tabbed-set",
}
SKIP_TAG_NAMES = {
    "button",
    "form",
    "nav",
    "script",
    "select",
    "style",
    "textarea",
}
KEEP_ATTR_NAMES = {
    "alt",
    "checked",
    "class",
    "colspan",
    "for",
    "height",
    "href",
    "id",
    "lang",
    "name",
    "open",
    "rel",
    "rowspan",
    "scope",
    "src",
    "target",
    "title",
    "type",
    "value",
    "width",
}
SVG_KEEP_ATTR_NAMES = {
    "clip-path",
    "clip-rule",
    "cx",
    "cy",
    "d",
    "fill",
    "fill-rule",
    "height",
    "points",
    "preserveaspectratio",
    "r",
    "rx",
    "ry",
    "stroke",
    "stroke-linecap",
    "stroke-linejoin",
    "stroke-miterlimit",
    "stroke-width",
    "transform",
    "vector-effect",
    "viewbox",
    "width",
    "x",
    "x1",
    "x2",
    "xmlns",
    "xmlns:xlink",
    "y",
    "y1",
    "y2",
}
SVG_TAG_NAMES = {
    "circle",
    "ellipse",
    "g",
    "line",
    "path",
    "polygon",
    "polyline",
    "rect",
    "svg",
    "symbol",
    "use",
}


def list_html_files(site_dir: Path) -> list[Path]:
    return sorted(path for path in site_dir.rglob("*.html") if path.is_file())


def process_page_html(
    html: str,
    *,
    output_path: str,
    exclude_selectors: list[str],
    link_scope_selectors: list[str],
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    _remove_existing_preview_bundle(soup)

    content_root = _find_content_root(soup)
    if content_root is None:
        return str(soup)

    marked_nodes = _mark_preview_excluded(
        content_root,
        [*DEFAULT_EXCLUDE_SELECTORS, *exclude_selectors],
    )
    entries = _extract_preview_entries(content_root, output_path=output_path)
    _clear_preview_excluded(marked_nodes)

    if entries:
        _inject_preview_bundle(
            soup,
            output_path=output_path,
            link_scope_selectors=link_scope_selectors,
            entries=entries,
        )

    return str(soup)


def _find_content_root(soup: BeautifulSoup) -> Tag | None:
    return (
        soup.select_one("article")
        or soup.select_one(".md-content")
        or soup.select_one("main")
    )


def _remove_existing_preview_bundle(soup: BeautifulSoup) -> None:
    for node in soup.select(f"[{DATA_ATTR}]"):
        node.decompose()


def _mark_preview_excluded(root: Tag, selectors: list[str]) -> list[Tag]:
    marked: list[Tag] = []
    for selector in selectors:
        if not selector:
            continue
        for node in root.select(selector):
            if node.has_attr(EXCLUDE_ATTR):
                continue
            node[EXCLUDE_ATTR] = ""
            marked.append(node)
    return marked


def _clear_preview_excluded(nodes: Iterable[Tag]) -> None:
    for node in nodes:
        node.attrs.pop(EXCLUDE_ATTR, None)


def _extract_preview_entries(content_root: Tag, *, output_path: str) -> dict[str, str]:
    page_key = _canonical_page_key(output_path)
    page_aliases = _page_key_aliases(output_path)

    if content_root.select_one(".toggle-container"):
        return _extract_toggle_entries(
            content_root,
            page_key=page_key,
            page_aliases=page_aliases,
        )
    return _extract_standard_entries(
        content_root,
        page_key=page_key,
        page_aliases=page_aliases,
    )


def _extract_standard_entries(
    content_root: Tag,
    *,
    page_key: str,
    page_aliases: list[str],
) -> dict[str, str]:
    entries: dict[str, str] = {}
    h1 = content_root.find("h1")
    if h1 is None:
        return entries

    root_nodes = _build_root_preview_nodes(h1, content_root)
    root_html = _render_nodes(root_nodes)
    _register_entry(entries, page_key, root_html)
    _register_aliases(entries, page_aliases, root_html)

    root_heading_id = h1.get("id")
    if root_heading_id:
        _register_entry(entries, _build_hash_key(page_key, root_heading_id), root_html)
        _register_aliases_with_hash(entries, page_aliases, root_heading_id, root_html)

    for heading in content_root.select("h2[id], h3[id], h4[id], h5[id], h6[id]"):
        section_id = heading.get("id")
        if not section_id:
            continue
        section_html = _build_section_preview_html(heading)
        if not section_html:
            continue
        _register_entry(entries, _build_hash_key(page_key, section_id), section_html)
        _register_aliases_with_hash(entries, page_aliases, section_id, section_html)

    return entries


def _extract_toggle_entries(
    content_root: Tag,
    *,
    page_key: str,
    page_aliases: list[str],
) -> dict[str, str]:
    entries: dict[str, str] = {}
    container = content_root.select_one(".toggle-container")
    if container is None:
        return entries

    canonical_variant = _get_canonical_variant(container)
    if canonical_variant is None:
        return entries

    header_spans = {
        span.get("data-variant", ""): span
        for span in container.select(".toggle-header > span[data-variant]")
    }
    panels = {
        panel.get("data-variant", ""): panel
        for panel in container.select(".toggle-panel[data-variant]")
    }

    for variant, panel in panels.items():
        if not variant:
            continue
        is_canonical = variant == canonical_variant
        header_span = header_spans.get(variant)
        if header_span is None:
            continue
        h1 = header_span.find("h1")
        if h1 is None:
            continue

        root_nodes = _build_panel_root_preview_nodes(h1, panel)
        root_html = _render_nodes(root_nodes)
        if not root_html:
            continue

        root_key = page_key if is_canonical else _build_hash_key(page_key, variant)
        _register_entry(entries, root_key, root_html)
        if not is_canonical:
            _register_aliases_with_hash(entries, page_aliases, variant, root_html)
        root_heading_id = h1.get("id")
        if is_canonical and root_heading_id:
            _register_entry(entries, _build_hash_key(page_key, root_heading_id), root_html)
            _register_aliases_with_hash(entries, page_aliases, root_heading_id, root_html)

        for heading in panel.select("h2[id], h3[id], h4[id], h5[id], h6[id]"):
            raw_id = heading.get("id")
            if not raw_id:
                continue
            logical_id = raw_id if is_canonical else _toggle_heading_id(raw_id, variant)
            section_html = _build_section_preview_html(heading)
            if not section_html:
                continue
            _register_entry(entries, _build_hash_key(page_key, logical_id), section_html)
            _register_aliases_with_hash(entries, page_aliases, logical_id, section_html)

    return entries


def _build_root_preview_nodes(h1: Tag, content_root: Tag) -> list[Tag]:
    soup = BeautifulSoup("", "html.parser")
    title_container = _find_top_level_container(h1, content_root)
    nodes: list[Tag] = []
    heading_clone = _clone_tag_for_preview(h1)
    if heading_clone is None:
        return nodes

    nodes.append(heading_clone)
    remaining_chars = max(0, MAX_TOTAL_TEXT_CHARS - _preview_text_length(heading_clone))
    remaining_blocks = BLOCK_LIMIT

    if title_container is not h1:
        inner_blocks, remaining_chars = _collect_preview_blocks(
            _iter_siblings_after(h1),
            soup,
            stop_level=6,
            max_blocks=remaining_blocks,
            remaining_chars=remaining_chars,
        )
        nodes.extend(inner_blocks)
        remaining_blocks -= len(inner_blocks)

    if remaining_blocks > 0:
        outer_blocks, _ = _collect_preview_blocks(
            _iter_siblings_after(title_container),
            soup,
            stop_level=6,
            max_blocks=remaining_blocks,
            remaining_chars=remaining_chars,
        )
        nodes.extend(outer_blocks)

    return _append_first_section_fallback(
        nodes,
        content_root=content_root,
        heading_selector="h2[id], h3[id], h4[id], h5[id], h6[id]",
    )


def _build_panel_root_preview_nodes(h1: Tag, panel: Tag) -> list[Tag]:
    nodes = _build_preview_nodes(
        heading=h1,
        nodes=_iter_children(panel),
        stop_level=None,
        soup=BeautifulSoup("", "html.parser"),
    )
    return _append_first_section_fallback(
        nodes,
        content_root=panel,
        heading_selector="h2[id], h3[id], h4[id], h5[id], h6[id]",
    )


def _append_first_section_fallback(
    nodes: list[Tag],
    *,
    content_root: Tag,
    heading_selector: str,
) -> list[Tag]:
    if len(nodes) > 1:
        return nodes

    first_section = content_root.select_one(heading_selector)
    if first_section is None:
        return nodes

    section_nodes = _build_section_preview_nodes(first_section)
    if not section_nodes:
        return nodes

    return [*nodes, *section_nodes]


def _build_section_preview_html(heading: Tag) -> str:
    return _render_nodes(_build_section_preview_nodes(heading))


def _build_section_preview_nodes(heading: Tag) -> list[Tag]:
    return _build_preview_nodes(
        heading=heading,
        nodes=_iter_siblings_after(heading),
        stop_level=_heading_level(heading),
        soup=BeautifulSoup("", "html.parser"),
    )


def _build_preview_nodes(
    *,
    heading: Tag,
    nodes: Iterable[NavigableString | Tag],
    stop_level: int | None,
    soup: BeautifulSoup,
) -> list[Tag]:
    collected: list[Tag] = []
    heading_clone = _clone_tag_for_preview(heading)
    if heading_clone is None:
        return collected

    collected.append(heading_clone)
    remaining_chars = max(0, MAX_TOTAL_TEXT_CHARS - _preview_text_length(heading_clone))
    preview_blocks, _ = _collect_preview_blocks(
        nodes,
        soup,
        stop_level=stop_level,
        max_blocks=BLOCK_LIMIT,
        remaining_chars=remaining_chars,
    )
    collected.extend(preview_blocks)
    return collected


def _collect_preview_blocks(
    nodes: Iterable[NavigableString | Tag],
    soup: BeautifulSoup,
    *,
    stop_level: int | None,
    max_blocks: int,
    remaining_chars: int,
) -> tuple[list[Tag], int]:
    collected: list[Tag] = []
    for current in nodes:
        if len(collected) >= max_blocks or remaining_chars <= 0:
            break

        if isinstance(current, NavigableString):
            candidates = _normalize_text_node(current, soup)
        else:
            if current.has_attr(EXCLUDE_ATTR):
                continue
            if current.name in HEADING_NAMES:
                if stop_level is None or _heading_level(current) <= stop_level:
                    break
                continue
            candidates = _normalize_preview_blocks(current, soup)

        for candidate in candidates:
            if len(collected) >= max_blocks or remaining_chars <= 0:
                break
            fitted = _fit_block_to_budget(candidate, remaining_chars, soup)
            if fitted is None:
                continue
            collected.append(fitted)
            remaining_chars = max(0, remaining_chars - _preview_text_length(fitted))

    return collected, remaining_chars


def _normalize_text_node(text: NavigableString, soup: BeautifulSoup) -> list[Tag]:
    block = _render_text_block(str(text), soup)
    return [block] if block is not None else []


def _normalize_preview_blocks(node: Tag, soup: BeautifulSoup) -> list[Tag]:
    if node.has_attr(EXCLUDE_ATTR) or node.name in SKIP_TAG_NAMES:
        return []
    if _has_blocked_class(node):
        return []
    if _is_code_container(node):
        block = _build_code_block(node, soup)
        return [block] if block is not None else []
    if _is_table_container(node):
        block = _build_table_summary(node, soup)
        return [block] if block is not None else []
    if _is_card_container(node):
        block = _build_card_summary(node, soup)
        return [block] if block is not None else []
    if node.name == "details":
        return _build_details_blocks(node, soup)
    if _is_image_container(node):
        block = _build_image_block(node)
        return [block] if block is not None else []
    if _should_clone_block(node):
        clone = _clone_tag_for_preview(node)
        return [clone] if clone is not None else []
    if node.name in {"blockquote", "ol", "p", "pre", "ul"}:
        clone = _clone_tag_for_preview(node)
        return [clone] if clone is not None else []
    if node.name == "figure":
        block = _build_image_block(node)
        return [block] if block is not None else []

    collected: list[Tag] = []
    for child in _iter_children(node):
        if len(collected) >= BLOCK_LIMIT:
            break
        if isinstance(child, NavigableString):
            collected.extend(_normalize_text_node(child, soup))
        else:
            collected.extend(_normalize_preview_blocks(child, soup))
    if collected:
        return collected[:BLOCK_LIMIT]

    text_block = _render_text_block(node.get_text(" ", strip=True), soup)
    return [text_block] if text_block is not None else []


def _render_text_block(text: str, soup: BeautifulSoup) -> Tag | None:
    value = _collapse_whitespace(text)
    if not value:
        return None
    paragraph = soup.new_tag("p")
    paragraph.string = value
    return paragraph


def _clone_tag_for_preview(node: Tag) -> Tag | None:
    if node.has_attr(EXCLUDE_ATTR) or node.name in SKIP_TAG_NAMES:
        return None

    fragment = BeautifulSoup(str(node), "html.parser")
    clone = fragment.find(True)
    if clone is None:
        return None

    for excluded in clone.select(f"[{EXCLUDE_ATTR}]"):
        excluded.decompose()
    for nested in list(clone.find_all(SKIP_TAG_NAMES)):
        nested.decompose()
    for nested in list(clone.find_all(True)):
        if _has_blocked_class(nested):
            nested.decompose()
    for anchor in clone.select("a.headerlink"):
        anchor.decompose()
    for anchor in clone.select("a.glightbox"):
        image = anchor.find("img")
        if image is None:
            anchor.decompose()
            continue
        replacement = _build_image_block(image)
        if replacement is None:
            anchor.decompose()
        else:
            anchor.replace_with(replacement)
    for details in clone.select("details"):
        details["open"] = ""

    for element in [clone, *clone.find_all(True)]:
        attrs = {}
        allowed_attr_names = set(KEEP_ATTR_NAMES)
        if element.name in SVG_TAG_NAMES:
            allowed_attr_names.update(SVG_KEEP_ATTR_NAMES)
        for key, value in element.attrs.items():
            if key == "id" or key == EXCLUDE_ATTR:
                continue
            if key.startswith("on") or key.startswith("data-") or key.startswith("aria-"):
                continue
            if key in allowed_attr_names:
                attrs[key] = value
        element.attrs = attrs

    if not _has_useful_content(clone):
        return None
    return clone


def _fit_block_to_budget(
    block: Tag,
    remaining_chars: int,
    soup: BeautifulSoup,
) -> Tag | None:
    text_length = _preview_text_length(block)
    if text_length == 0 or text_length <= remaining_chars:
        return block
    if remaining_chars < MIN_TRUNCATED_BLOCK_CHARS:
        return None

    truncated_text = _truncate_text(block.get_text(" ", strip=True), remaining_chars)
    if not truncated_text:
        return None

    if block.name == "blockquote":
        quote = soup.new_tag("blockquote")
        paragraph = soup.new_tag("p")
        paragraph.string = truncated_text
        quote.append(paragraph)
        return quote
    if block.name == "pre":
        pre = soup.new_tag("pre")
        code = soup.new_tag("code")
        code.string = truncated_text
        pre.append(code)
        return pre

    paragraph = soup.new_tag("p")
    paragraph.string = truncated_text
    return paragraph


def _preview_text_length(node: Tag) -> int:
    return len(_collapse_whitespace(node.get_text(" ", strip=True)))


def _is_code_container(node: Tag) -> bool:
    if node.name in {"code", "pre"}:
        return True
    classes = set(node.get("class", []))
    if "highlight" in classes or any(name.startswith("language-") for name in classes):
        return True
    if node.has_attr("data-termynal") or node.select_one("[data-termynal]"):
        return True
    return node.find("pre") is not None and node.find("code") is not None


def _build_code_block(node: Tag, soup: BeautifulSoup) -> Tag | None:
    lines: list[str] = []
    language_class: str | None = None

    termynal = node if node.has_attr("data-termynal") else node.select_one("[data-termynal]")
    if termynal is not None:
        lines = [
            _collapse_whitespace(item.get_text(" ", strip=True))
            for item in termynal.select("[data-ty]")
            if _collapse_whitespace(item.get_text(" ", strip=True))
        ]
    else:
        code_node = node if node.name == "code" else node.find("code")
        if code_node is not None:
            for class_name in code_node.get("class", []):
                if class_name.startswith("language-"):
                    language_class = class_name
                    break
            raw_text = code_node.get_text("\n", strip=False)
        else:
            pre_node = node if node.name == "pre" else node.find("pre")
            raw_text = "" if pre_node is None else pre_node.get_text("\n", strip=False)
        lines = [line.rstrip() for line in raw_text.splitlines()]

    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    if not lines:
        return None

    if len(lines) > MAX_CODE_LINES:
        lines = lines[:MAX_CODE_LINES]
        lines.append("...")

    pre = soup.new_tag("pre")
    code = soup.new_tag("code")
    if language_class is not None:
        code["class"] = [language_class]
    code.string = "\n".join(lines)
    pre.append(code)
    return pre


def _is_table_container(node: Tag) -> bool:
    return node.name == "table" or node.find("table") is not None


def _build_table_summary(node: Tag, soup: BeautifulSoup) -> Tag | None:
    table = node if node.name == "table" else node.find("table")
    if table is None:
        return None

    rows = table.find_all("tr")
    if not rows:
        return None

    header_cells: list[str] = []
    data_rows = rows
    first_row = rows[0]
    if first_row.find("th") is not None:
        header_cells = _row_texts(first_row)
        data_rows = rows[1:]

    summary = soup.new_tag("ul")
    row_count = 0
    for row in data_rows:
        cells = _row_texts(row)
        if not cells:
            continue
        if header_cells and len(header_cells) == len(cells):
            row_text = "; ".join(
                f"{header}: {value}"
                for header, value in zip(header_cells, cells)
                if value
            )
        else:
            row_text = " | ".join(cells)
        if not row_text:
            continue
        item = soup.new_tag("li")
        item.string = _truncate_text(row_text, 180)
        summary.append(item)
        row_count += 1
        if row_count >= MAX_TABLE_ROWS:
            break

    return summary if row_count else None


def _row_texts(row: Tag) -> list[str]:
    return [
        _collapse_whitespace(cell.get_text(" ", strip=True))
        for cell in row.find_all(["th", "td"])
        if _collapse_whitespace(cell.get_text(" ", strip=True))
    ]


def _is_card_container(node: Tag) -> bool:
    classes = set(node.get("class", []))
    if "card" in classes:
        return True
    if "grid" in classes and "cards" in classes:
        return True
    return node.select_one(".grid.cards, .card") is not None


def _build_card_summary(node: Tag, soup: BeautifulSoup) -> Tag | None:
    items = node.select(".grid.cards > ul > li, .grid.cards > ol > li, .grid.cards > .card, .grid > .card")
    if not items and "card" in set(node.get("class", [])):
        items = [node]
    if not items:
        return None

    summary = soup.new_tag("ul")
    count = 0
    for item in items:
        title = _extract_card_title(item)
        teaser = _extract_card_teaser(item, title)
        if not title and not teaser:
            continue
        summary_item = soup.new_tag("li")
        text = title or ""
        if teaser and teaser != title:
            text = f"{text}: {teaser}" if text else teaser
        summary_item.string = _truncate_text(text, 180)
        summary.append(summary_item)
        count += 1
        if count >= MAX_CARD_ITEMS:
            break

    return summary if count else None


def _extract_card_title(item: Tag) -> str:
    title_node = item.find(HEADING_NAMES.union({"strong"}))
    if title_node is not None:
        return _collapse_whitespace(title_node.get_text(" ", strip=True))
    link = item.find("a")
    if link is not None:
        return _collapse_whitespace(link.get_text(" ", strip=True))
    paragraph = item.find("p")
    if paragraph is not None:
        return _collapse_whitespace(paragraph.get_text(" ", strip=True))
    return _collapse_whitespace(item.get_text(" ", strip=True))


def _extract_card_teaser(item: Tag, title: str) -> str:
    for paragraph in item.find_all("p"):
        text = _collapse_whitespace(paragraph.get_text(" ", strip=True))
        if text and text != title:
            return text
    for text in item.stripped_strings:
        value = _collapse_whitespace(text)
        if value and value != title:
            return value
    return ""


def _build_details_blocks(node: Tag, soup: BeautifulSoup) -> list[Tag]:
    summary_node = node.find("summary", recursive=False)
    summary_text = ""
    if summary_node is not None:
        summary_text = _collapse_whitespace(summary_node.get_text(" ", strip=True))

    blocks: list[Tag] = []
    if summary_text:
        paragraph = soup.new_tag("p")
        strong = soup.new_tag("strong")
        strong.string = summary_text
        paragraph.append(strong)
        blocks.append(paragraph)

    detail_blocks: list[Tag] = []
    for child in _iter_children(node):
        if isinstance(child, Tag) and child.name == "summary":
            continue
        if len(detail_blocks) >= MAX_DETAILS_BLOCKS:
            break
        if isinstance(child, NavigableString):
            normalized = _normalize_text_node(child, soup)
        else:
            normalized = _normalize_preview_blocks(child, soup)
        for candidate in normalized:
            detail_blocks.append(candidate)
            if len(detail_blocks) >= MAX_DETAILS_BLOCKS:
                break

    blocks.extend(detail_blocks)
    return blocks


def _is_image_container(node: Tag) -> bool:
    if node.name == "img":
        return True
    if node.name == "a" and "glightbox" in node.get("class", []):
        return node.find("img") is not None
    if node.name == "figure" and node.find("img") is not None:
        return True
    return node.select_one("a.glightbox img") is not None


def _build_image_block(node: Tag) -> Tag | None:
    image = node if node.name == "img" else node.find("img")
    if image is None:
        return None

    clone = BeautifulSoup(str(image), "html.parser").find("img")
    if clone is None:
        return None

    clone.attrs = {
        key: value
        for key, value in clone.attrs.items()
        if key in {"alt", "height", "src", "title", "width"}
    }
    if not clone.get("src"):
        return None
    return clone


def _should_clone_block(node: Tag) -> bool:
    classes = set(node.get("class", []))
    if PRESERVE_BLOCK_CLASS_NAMES.intersection(classes):
        return True
    if node.name in {"aside", "section"}:
        return True
    return False


def _has_blocked_class(node: Tag) -> bool:
    return bool(BLOCKED_CLASS_NAMES.intersection(node.get("class", [])))


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _truncate_text(text: str, limit: int) -> str:
    value = _collapse_whitespace(text)
    if len(value) <= limit:
        return value

    cutoff = max(0, limit - 3)
    trimmed = value[:cutoff].rstrip()
    if " " in trimmed:
        trimmed = trimmed.rsplit(" ", 1)[0]
    trimmed = trimmed.rstrip(" ,;:.")
    if not trimmed:
        return value[:cutoff].rstrip() + "..."
    return trimmed + "..."


def _has_useful_content(node: Tag) -> bool:
    if node.get_text(" ", strip=True):
        return True
    return node.find(True) is not None


def _iter_siblings_after(node: Tag) -> Iterable[NavigableString | Tag]:
    sibling = node.next_sibling
    while sibling is not None:
        current = sibling
        sibling = sibling.next_sibling
        if isinstance(current, (NavigableString, Tag)):
            yield current


def _iter_children(node: Tag) -> Iterable[NavigableString | Tag]:
    for child in node.children:
        if isinstance(child, (NavigableString, Tag)):
            yield child


def _find_top_level_container(node: Tag, boundary: Tag) -> Tag:
    current = node
    while isinstance(current.parent, Tag) and current.parent is not boundary:
        current = current.parent
    return current


def _heading_level(node: Tag) -> int:
    if node.name not in HEADING_NAMES:
        return 7
    return int(node.name[1])


def _canonical_page_key(output_path: str) -> str:
    clean_path = output_path.strip("/")
    if clean_path == "index.html" or clean_path == "":
        return "/"
    if clean_path.endswith("/index.html"):
        return f"/{clean_path[:-len('index.html')]}"
    if clean_path.endswith(".html"):
        return f"/{clean_path[:-len('.html')]}/"
    return f"/{clean_path}/"


def _page_key_aliases(output_path: str) -> list[str]:
    clean_path = output_path.strip("/")
    if not clean_path:
        return []
    return [f"/{clean_path}"]


def _build_hash_key(page_key: str, heading_id: str) -> str:
    return f"{page_key}#{heading_id}"


def _toggle_heading_id(heading_id: str, variant: str) -> str:
    if heading_id.startswith(f"{variant}-"):
        return heading_id
    return f"{variant}-{heading_id}"


def _register_entry(entries: dict[str, str], key: str, html: str) -> None:
    if html:
        entries[key] = html


def _register_aliases(entries: dict[str, str], aliases: list[str], html: str) -> None:
    for alias in aliases:
        _register_entry(entries, alias, html)


def _register_aliases_with_hash(
    entries: dict[str, str],
    aliases: list[str],
    heading_id: str,
    html: str,
) -> None:
    for alias in aliases:
        _register_entry(entries, f"{alias}#{heading_id}", html)


def _render_nodes(nodes: Iterable[Tag]) -> str:
    container = BeautifulSoup("", "html.parser")
    for node in nodes:
        if node is not None:
            container.append(node)
    return container.decode_contents()


def _inject_preview_bundle(
    soup: BeautifulSoup,
    *,
    output_path: str,
    link_scope_selectors: list[str],
    entries: dict[str, str],
) -> None:
    body = soup.body or soup
    container = soup.new_tag("div")
    container[DATA_ATTR] = ""
    container["hidden"] = ""

    manifest = {
        "version": 1,
        "page": _canonical_page_key(output_path),
        "scopes": link_scope_selectors,
        "entries": {},
    }

    template_lookup: dict[str, str] = {}
    for index, (key, html) in enumerate(entries.items(), start=1):
        template_id = template_lookup.get(html)
        if template_id is None:
            template_id = f"instant-preview-template-{index}"
            template_lookup[html] = template_id

            template = soup.new_tag("template")
            template[TEMPLATE_ATTR] = template_id
            fragment = BeautifulSoup(html, "html.parser")
            for child in list(fragment.contents):
                template.append(child.extract())
            container.append(template)

        manifest["entries"][key] = {"template": template_id}

    manifest_tag = soup.new_tag("script")
    manifest_tag["type"] = "application/json"
    manifest_tag[MANIFEST_ATTR] = ""
    manifest_tag.string = json.dumps(manifest, separators=(",", ":"), sort_keys=True)
    container.insert(0, manifest_tag)
    body.append(container)


def _get_canonical_variant(container: Tag) -> str | None:
    canonical_button = container.select_one('.toggle-btn[data-canonical="true"]')
    if canonical_button is not None:
        return canonical_button.get("data-variant")
    first_button = container.select_one(".toggle-btn[data-variant]")
    if first_button is not None:
        return first_button.get("data-variant")
    return None
