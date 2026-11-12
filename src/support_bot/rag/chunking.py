"""Split Markdown documents into heading-based chunks."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    title: str
    heading: str
    text: str
    content_hash: str
    position: int

    @property
    def metadata(self) -> dict[str, str | int]:
        return {
            "source": self.source,
            "title": self.title,
            "heading": self.heading,
            "content_hash": self.content_hash,
            "position": self.position,
        }


def _split_long(text: str, max_chars: int) -> list[str]:
    """Split on blank lines so that each piece stays under ``max_chars`` when possible."""
    if len(text) <= max_chars:
        return [text]
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", text):
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) <= max_chars or not current:
            current = candidate
        else:
            pieces.append(current)
            current = para
    if current:
        pieces.append(current)
    return pieces


def chunk_markdown(text: str, source: str, max_chars: int = 1500) -> list[Chunk]:
    """Chunk a Markdown document by H2/H3 headings.

    The first H1 is the document title. Text before the first H2 becomes an
    "Overview" chunk. Headings inside fenced code blocks are ignored. The heading
    stored for a chunk is the path of headings below the title (e.g. "Setup > Windows").
    """
    title = Path(source).stem.replace("-", " ").title()
    stack: list[tuple[int, str]] = []
    sections: list[tuple[str, list[str]]] = [("Overview", [])]
    in_fence = False
    title_seen = False

    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        match = None if in_fence else _HEADING.match(line)
        if match:
            level, name = len(match.group(1)), match.group(2).strip()
            if level == 1 and not title_seen:
                title, title_seen = name, True
                continue
            stack = [(lvl, n) for lvl, n in stack if lvl < level] + [(level, name)]
            sections.append((" > ".join(n for _, n in stack), []))
            continue
        sections[-1][1].append(line)

    chunks: list[Chunk] = []
    for heading, lines in sections:
        body = "\n".join(lines).strip()
        if not body:
            continue
        for piece in _split_long(body, max_chars):
            content_hash = hashlib.sha256(f"{title}\n{heading}\n{piece}".encode()).hexdigest()
            chunk_id = hashlib.sha256(f"{source}\n{content_hash}".encode()).hexdigest()[:32]
            chunks.append(
                Chunk(
                    id=chunk_id,
                    source=source,
                    title=title,
                    heading=heading,
                    text=piece,
                    content_hash=content_hash,
                    position=len(chunks),
                )
            )
    return chunks


def load_knowledge_base(kb_dir: Path, max_chars: int = 1500) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(kb_dir.rglob("*.md")):
        source = path.relative_to(kb_dir).as_posix()
        chunks.extend(chunk_markdown(path.read_text(encoding="utf-8"), source, max_chars))
    return chunks
