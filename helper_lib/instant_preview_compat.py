from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from bs4 import BeautifulSoup, NavigableString, Tag

HEADING_NAMES = {f"h{level}" for level in range(1, 7)}
DEFAULT_EXCLUDE_SELECTORS = (
    ".ai-file-actions-container",
    ".toggle-buttons",
)
PROXY_PREFIX = "__instant-preview__"
ROOT_STASH_ATTR = "data-instant-preview-stash"
ROOT_TARGET_ATTR = "data-instant-preview-root-target"
SECTION_HEADING_ATTR = "data-instant-preview-section-heading"


def process_page_html(
    html: str,
    *,
    output_path: str,
    exclude_selectors: list[str],
) -> str:
    soup = BeautifulSoup(html, "html.parser")
    content_root = _find_content_root(soup)
    if content_root is None:
        return html

    _remove_existing_preview_artifacts(content_root)

    selectors = [*DEFAULT_EXCLUDE_SELECTORS, *exclude_selectors]
    mark_preview_excluded(content_root, selectors)
    hoist_leading_preview_excluded(content_root)

    if content_root.select_one(".toggle-container"):
        _rewrite_toggle_heading_ids(content_root)
        _inject_toggle_root_preview(content_root, soup, output_path=output_path)
    else:
        _inject_standard_root_preview(content_root, soup, output_path=output_path)

    return str(soup)


def mark_preview_excluded(root: BeautifulSoup | Tag, selectors: list[str]) -> None:
    for selector in selectors:
        if not selector:
            continue
        for node in root.select(selector):
            node["data-preview-exclude"] = ""


def hoist_leading_preview_excluded(root: BeautifulSoup | Tag) -> None:
    parents: list[Tag] = []
    if isinstance(root, Tag):
        parents.append(root)
    parents.extend(root.find_all(True))

    for parent in parents:
        if not any(
            isinstance(child, Tag) and child.name in HEADING_NAMES
            for child in parent.children
        ):
            continue
        _hoist_in_parent(parent, root)


def list_html_files(site_dir: Path) -> list[Path]:
    return sorted(path for path in site_dir.rglob("*.html") if path.is_file())


def _find_content_root(soup: BeautifulSoup) -> Tag | None:
    return soup.select_one("article") or soup.select_one(".md-content")


def _remove_existing_preview_artifacts(content_root: Tag) -> None:
    for stash in content_root.select(f"[{ROOT_STASH_ATTR}]"):
        stash.decompose()

    for node in content_root.select(f"[{ROOT_TARGET_ATTR}]"):
        node.attrs.pop(ROOT_TARGET_ATTR, None)

    for node in content_root.select(f"[{SECTION_HEADING_ATTR}]"):
        node.attrs.pop(SECTION_HEADING_ATTR, None)
        node.attrs.pop("data-heading-level", None)


def _inject_standard_root_preview(
    content_root: Tag,
    soup: BeautifulSoup,
    *,
    output_path: str,
) -> None:
    h1 = content_root.find("h1")
    if h1 is None:
        return

    title_container = _find_root_title_container(h1, content_root)
    preview_nodes = _collect_root_preview_nodes(
        _iter_siblings_after(title_container),
        soup,
    )
    _append_root_preview_target(
        content_root,
        soup,
        title_heading=h1,
        preview_nodes=preview_nodes,
        seed=f"{output_path}-root",
    )


def _inject_toggle_root_preview(
    content_root: Tag,
    soup: BeautifulSoup,
    *,
    output_path: str,
) -> None:
    container = content_root.select_one(".toggle-container")
    if container is None:
        return

    canonical_variant = _get_canonical_variant(container)
    if not canonical_variant:
        return

    header_span = container.select_one(
        f'.toggle-header > span[data-variant="{canonical_variant}"]'
    )
    panel = container.select_one(f'.toggle-panel[data-variant="{canonical_variant}"]')
    if header_span is None or panel is None:
        return

    h1 = header_span.find("h1")
    if h1 is None:
        return

    preview_nodes = _collect_root_preview_nodes(
        _iter_children(panel),
        soup,
    )
    _append_root_preview_target(
        content_root,
        soup,
        title_heading=h1,
        preview_nodes=preview_nodes,
        seed=f"{output_path}-toggle-{canonical_variant}",
    )


def _find_root_title_container(h1: Tag, content_root: Tag) -> Tag:
    current = h1
    while isinstance(current.parent, Tag) and current.parent is not content_root:
        current = current.parent
    return current


def _collect_root_preview_nodes(
    nodes: Iterable[NavigableString | Tag],
    soup: BeautifulSoup,
) -> list[Tag]:
    preview_nodes: list[Tag] = []
    encountered_section_heading = False

    for current in nodes:
        if isinstance(current, NavigableString):
            if current.strip():
                text_block = _render_text_block(current, soup)
                if text_block is not None:
                    preview_nodes.append(text_block)
            continue

        if current.has_attr("data-preview-exclude"):
            continue

        if current.name in HEADING_NAMES:
            if encountered_section_heading:
                break
            section_heading = _render_section_heading_block(current, soup)
            if section_heading is not None:
                preview_nodes.append(section_heading)
            encountered_section_heading = True
            continue

        clone = _clone_tag_for_preview(current)
        if clone is not None:
            preview_nodes.append(clone)

    return preview_nodes


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


def _append_root_preview_target(
    content_root: Tag,
    soup: BeautifulSoup,
    *,
    title_heading: Tag,
    preview_nodes: list[Tag],
    seed: str,
) -> str:
    target_id = _unique_proxy_id(soup, seed)
    stash = _get_or_create_preview_stash(content_root, soup)
    stash.append(_build_preview_target_heading(title_heading, soup, target_id=target_id))
    for node in preview_nodes:
        stash.append(node)
    return target_id


def _build_preview_target_heading(
    title_heading: Tag,
    soup: BeautifulSoup,
    *,
    target_id: str,
) -> Tag:
    clone = _clone_tag_for_preview(title_heading)
    heading = soup.new_tag(
        title_heading.name if title_heading.name in HEADING_NAMES else "h1"
    )
    heading["id"] = target_id
    heading[ROOT_TARGET_ATTR] = ""

    if clone is None:
        heading.string = title_heading.get_text(" ", strip=True)
        return heading

    for child in list(clone.contents):
        heading.append(child.extract())
    return heading


def _render_section_heading_block(heading: Tag, soup: BeautifulSoup) -> Tag | None:
    clone = _clone_tag_for_preview(heading)
    if clone is None:
        return None

    block = soup.new_tag("p")
    block[SECTION_HEADING_ATTR] = ""
    level = heading.name[1:] if heading.name in HEADING_NAMES else "2"
    block["data-heading-level"] = level

    strong = soup.new_tag("strong")
    for child in list(clone.contents):
        strong.append(child.extract())
    if not strong.contents:
        strong.string = heading.get_text(" ", strip=True)
    block.append(strong)
    return block


def _render_text_block(text: NavigableString, soup: BeautifulSoup) -> Tag | None:
    content = text.strip()
    if not content:
        return None
    paragraph = soup.new_tag("p")
    paragraph.string = content
    return paragraph


def _clone_tag_for_preview(node: Tag) -> Tag | None:
    if node.has_attr("data-preview-exclude"):
        return None

    fragment = BeautifulSoup(str(node), "html.parser")
    clone = fragment.find(True)
    if clone is None:
        return None

    for excluded in clone.select("[data-preview-exclude]"):
        excluded.decompose()
    if clone.has_attr("data-preview-exclude"):
        return None

    for anchor in clone.select("a.headerlink"):
        anchor.decompose()

    _strip_ids(clone)
    _strip_preview_attrs(clone)
    if not _has_useful_content(clone):
        return None
    return clone


def _strip_ids(node: Tag) -> None:
    for element in [node, *node.find_all(True)]:
        element.attrs.pop("id", None)


def _strip_preview_attrs(node: Tag) -> None:
    for element in [node, *node.find_all(True)]:
        element.attrs.pop("data-preview-exclude", None)


def _has_useful_content(node: Tag) -> bool:
    if node.get_text(" ", strip=True):
        return True
    return node.find(True) is not None


def _get_or_create_preview_stash(content_root: Tag, soup: BeautifulSoup) -> Tag:
    stash = content_root.find(attrs={ROOT_STASH_ATTR: True}, recursive=False)
    if stash is not None:
        return stash

    stash = soup.new_tag("div")
    stash[ROOT_STASH_ATTR] = ""
    stash["style"] = "display:none"
    content_root.insert(0, stash)
    return stash


def _unique_proxy_id(soup: BeautifulSoup, seed: str) -> str:
    slug = _slugify(seed) or "root"
    base = f"{PROXY_PREFIX}{slug}"
    candidate = base
    index = 2
    while soup.find(id=candidate) is not None:
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def _rewrite_toggle_heading_ids(content_root: Tag) -> None:
    for container in content_root.select(".toggle-container"):
        canonical_variant = _get_canonical_variant(container)
        header_spans = {
            span.get("data-variant"): span
            for span in container.select(".toggle-header > span[data-variant]")
            if span.get("data-variant")
        }
        panels = {
            panel.get("data-variant"): panel
            for panel in container.select(".toggle-panel[data-variant]")
            if panel.get("data-variant")
        }

        for variant, panel in panels.items():
            is_canonical = variant == canonical_variant
            span = header_spans.get(variant)

            if span is not None:
                _rewrite_heading_ids(span, variant=variant, is_canonical=is_canonical)
            _rewrite_heading_ids(panel, variant=variant, is_canonical=is_canonical)


def _get_canonical_variant(container: Tag) -> str | None:
    canonical = container.select_one('.toggle-btn[data-canonical="true"]')
    if canonical is not None:
        return canonical.get("data-variant")

    first = container.select_one(".toggle-btn[data-variant]")
    if first is not None:
        return first.get("data-variant")

    return None


def _rewrite_heading_ids(scope: Tag, *, variant: str, is_canonical: bool) -> None:
    if is_canonical:
        return

    id_map: dict[str, str] = {}
    for heading in scope.select("h1, h2, h3, h4, h5, h6"):
        current_id = heading.get("id")
        if not current_id:
            continue
        if current_id.startswith(f"{variant}-"):
            continue

        new_id = f"{variant}-{current_id}"
        id_map[current_id] = new_id
        heading["id"] = new_id

        for link in heading.select("a[href]"):
            href = link.get("href", "")
            if href == f"#{current_id}":
                link["href"] = f"#{new_id}"

    if not id_map:
        return

    for link in scope.select("a[href]"):
        href = link.get("href", "")
        if not href.startswith("#"):
            continue
        new_id = id_map.get(href[1:])
        if new_id:
            link["href"] = f"#{new_id}"


def _hoist_in_parent(parent: Tag, root: BeautifulSoup | Tag) -> None:
    for child in list(parent.children):
        if not isinstance(child, Tag) or child.name not in HEADING_NAMES:
            continue
        if child.name == "h1" and parent is not root:
            continue

        heading = child
        sibling = heading.next_sibling
        while sibling is not None:
            current = sibling
            sibling = sibling.next_sibling

            if isinstance(current, NavigableString):
                if current.strip():
                    break
                continue

            if current.name in HEADING_NAMES:
                break

            if current.has_attr("data-preview-exclude"):
                heading.insert_before(current.extract())
                continue

            break
