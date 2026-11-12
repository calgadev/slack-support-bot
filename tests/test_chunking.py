from support_bot.rag.chunking import chunk_markdown, load_knowledge_base
from tests.conftest import KB_DIR

DOC = """# VPN Guide

Intro paragraph.

## Install

Install it.

### Windows

Use the Software Center.

```bash
# not a heading
echo hi
```

## Connect

Connect to vpn.acme.example.
"""


def test_splits_by_headings_with_heading_path() -> None:
    chunks = chunk_markdown(DOC, "vpn.md")
    assert [c.heading for c in chunks] == ["Overview", "Install", "Install > Windows", "Connect"]
    assert all(c.title == "VPN Guide" and c.source == "vpn.md" for c in chunks)
    assert "# not a heading" in chunks[2].text


def test_ids_are_stable_and_content_based() -> None:
    first = chunk_markdown(DOC, "vpn.md")
    second = chunk_markdown(DOC, "vpn.md")
    assert [c.id for c in first] == [c.id for c in second]
    changed = chunk_markdown(DOC.replace("Install it.", "Install it now."), "vpn.md")
    assert first[1].id != changed[1].id
    assert first[0].id == changed[0].id  # other sections keep their ids


def test_title_falls_back_to_filename() -> None:
    chunks = chunk_markdown("## Only section\n\nBody.", "shared-drive.md")
    assert chunks[0].title == "Shared Drive"


def test_long_sections_are_split_on_paragraphs() -> None:
    body = "\n\n".join(f"Paragraph {i} " + "word " * 50 for i in range(10))
    chunks = chunk_markdown(f"# T\n\n## Big\n\n{body}", "t.md", max_chars=600)
    assert len(chunks) > 1
    assert all(len(c.text) <= 600 for c in chunks)
    assert all(c.heading == "Big" for c in chunks)


def test_real_knowledge_base_is_chunked() -> None:
    chunks = load_knowledge_base(KB_DIR)
    sources = {c.source for c in chunks}
    assert len(sources) >= 12
    assert len({c.id for c in chunks}) == len(chunks)
