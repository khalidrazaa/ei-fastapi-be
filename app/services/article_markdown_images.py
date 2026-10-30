"""Locate real Markdown images and replace their markup without touching code."""

from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit

from markdown_it import MarkdownIt
from markdown_it.rules_inline.image import image as image_rule


@dataclass(frozen=True)
class MarkdownImage:
    start: int
    end: int
    destination: str
    alt_markup: str
    title: str


def _capture_image(state, silent):
    start = state.pos
    label_end = state.md.helpers.parseLinkLabel(state, start + 1, False) if state.src.startswith("![", start) else -1
    matched = image_rule(state, silent)
    if matched and not silent:
        token = state.tokens[-1]
        token.meta["image_span"] = (start, state.pos, state.src[start:label_end + 1])
    return matched


def _positions(source, text, start, end):
    """Map an inline block back through list/quote prefixes and table escaping."""
    positions = []
    cursor = start
    for part in source.splitlines(keepends=True):
        line = part.rstrip("\n")
        found = text.find(line, cursor, end) if line else cursor
        if found < 0:
            # markdown-it removes the escape before pipes when splitting table cells.
            candidates, indexes = [], []
            for index in range(cursor, end):
                if text[index] == "\\" and text[index:index + 2] == "\\|":
                    continue
                candidates.append(text[index])
                indexes.append(index)
            found_filtered = "".join(candidates).find(line)
            if found_filtered < 0:
                raise ValueError("Cannot map an image in this Markdown layout. Put it on its own line.")
            mapped = indexes[found_filtered:found_filtered + len(line)]
        else:
            mapped = list(range(found, found + len(line)))
        positions.extend(mapped)
        cursor = mapped[-1] + 1 if mapped else cursor
        if part.endswith("\n"):
            newline = text.find("\n", cursor, end)
            if newline < 0:
                raise ValueError("Cannot map a multiline Markdown image.")
            positions.append(newline)
            cursor = newline + 1
    return positions


def markdown_images(content: str) -> tuple[str, list[MarkdownImage]]:
    text = content.replace("\r\n", "\n").replace("\r", "\n")
    parser = MarkdownIt("commonmark").enable("table")
    parser.inline.ruler.at("image", _capture_image)
    tokens = parser.parse(text)
    offsets = [0]
    for line in text.splitlines(keepends=True):
        offsets.append(offsets[-1] + len(line))
    images = []
    current_map = [0, max(0, len(offsets) - 1)]
    cursors = {}
    for token in tokens:
        if token.map is not None:
            current_map = token.map
        if token.type != "inline" or not token.children:
            continue
        children = [child for child in token.children if "image_span" in child.meta]
        lower = offsets[current_map[0]]
        upper = offsets[min(current_map[1], len(offsets) - 1)]
        lower = max(lower, cursors.get(tuple(current_map), lower))
        positions = _positions(token.content, text, lower, upper)
        if positions:
            cursors[tuple(current_map)] = positions[-1] + 1
        for child in children:
            start, end, alt_markup = child.meta["image_span"]
            # Table parsing removes the slash from escaped pipes. Recover the
            # original label so rewriting cannot introduce new table columns.
            raw_alt = text[positions[start]:positions[start + len(alt_markup) - 1] + 1]
            images.append(MarkdownImage(
                positions[start], positions[end - 1] + 1,
                child.attrGet("src") or "", raw_alt, child.attrGet("title") or "",
            ))
    return text, images


def local_image_path(destination: str) -> str | None:
    """A logical import path, never a filesystem destination."""
    value = unquote(destination).replace("\\", "/")
    parsed = urlsplit(value)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return None
    if value.startswith("/") and not value.startswith("//"):
        return None  # Existing same-origin URLs remain valid.
    if parsed.scheme or parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError(f"Unsupported local image path: {destination}")
    parts = PurePosixPath(value).parts
    if not value or not parts or ".." in parts or "\0" in value or ":" in value:
        raise ValueError(f"Invalid local image path: {destination}")
    return str(PurePosixPath(value))


def _match_image_filename(path: str, filenames: list[str]) -> str | None:
    reference = PurePosixPath(path)
    candidates = [(name, PurePosixPath(name)) for name in filenames]
    tiers = [
        [name for name, candidate in candidates if candidate == reference],
        [name for name, candidate in candidates if candidate.name == reference.name],
    ]
    # Diagram exports commonly change format while keeping the diagram name.
    # Preserve full-filename matches first and never guess between alternatives.
    if reference.suffix.lower() in {".png", ".svg"}:
        diagrams = [(name, candidate) for name, candidate in candidates
                    if candidate.suffix.lower() in {".png", ".svg"}]
        tiers.extend([
            [name for name, candidate in diagrams
             if candidate.with_suffix("") == reference.with_suffix("")],
            [name for name, candidate in diagrams if candidate.stem == reference.stem],
        ])
    for matches in tiers:
        if len(matches) > 1:
            raise ValueError(f"Multiple selected images match {path}. Choose an explicit image mapping.")
        if matches:
            return matches[0]
    return None


def resolve_images(content: str, filenames: list[str], manifest: dict[str, str]):
    text, references = markdown_images(content)
    available = set(filenames)
    normalized_manifest = {}
    for destination, filename in manifest.items():
        path = local_image_path(destination)
        key = path if path is not None else "url:" + unquote(destination)
        if filename not in available:
            raise ValueError(f"Invalid image mapping for {destination}.")
        if key in normalized_manifest and normalized_manifest[key] != filename:
            raise ValueError(f"Conflicting image mappings for {destination}.")
        normalized_manifest[key] = filename
    resolved, used, actual_paths = [], set(), set()
    for image in references:
        path = local_image_path(image.destination)
        key = path if path is not None else "url:" + unquote(image.destination)
        actual_paths.add(key)
        filename = normalized_manifest.get(key)
        if path is None and filename is None:
            continue
        if filename is None and path is not None:
            filename = _match_image_filename(path, filenames)
        if filename is None:
            raise ValueError(f"Select the image referenced by Markdown: {image.destination}")
        used.add(filename)
        resolved.append((image, filename))
    if set(normalized_manifest) - actual_paths:
        raise ValueError("The image manifest contains paths that are not Markdown images.")
    if available - used:
        raise ValueError("Every selected image must be referenced in the article Markdown.")
    return text, resolved


def rewrite_images(text: str, resolved, urls: dict[str, str]) -> str:
    for image, filename in sorted(resolved, key=lambda pair: pair[0].start, reverse=True):
        title = image.title.replace("\\", "\\\\").replace('"', '\\"').replace("|", "\\|")
        suffix = f' "{title}"' if title else ""
        replacement = f"{image.alt_markup}(<{urls[filename]}>{suffix})"
        text = text[:image.start] + replacement + text[image.end:]
    return text


def validate_published_images(content: str) -> None:
    _, images = markdown_images(content)
    for image in images:
        if local_image_path(image.destination) is not None:
            raise ValueError(f"Upload the local diagram before publishing: {image.destination}")
