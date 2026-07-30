"""
Chunk FastAPI's documentation into data/processed/doc_chunks.jsonl.

Two-stage approach, and the order matters:

1. RESOLVE INCLUDES FIRST. The raw markdown uses a custom
   `{* ../../docs_src/path/to/file.py *}` syntax instead of embedding code
   directly. If chunked before resolving these, the result: chunks containing
   a broken placeholder instead of the actual example code.

2. THEN SPLIT STRUCTURE-AWARE, in two passes:
   a. MarkdownHeaderTextSplitter splits on headers and attaches the header
      path to each resulting section as metadata. 
      This means a chunk about, say, "Query Parameters > Optional parameters"
      keeps that context even after being pulled out of the full document.
   b. Sections that are still too large get further split by
      RecursiveCharacterTextSplitter, which tries to break on paragraph/line
      boundaries before falling back to in the middle of a sentence.

Each output chunk is a JSON object with the chunk text plus metadata
(source file, header path, an approximate source URL) That metadata is
what lets show citations later and filter retrieval by section.

To run:
    python src/chunk_docs.py
"""

import json
import re
from pathlib import Path

from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = PROJECT_ROOT / "data" / "raw" / "docs"
DOCS_SRC_DIR = PROJECT_ROOT / "data" / "raw" / "docs_src"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "doc_chunks.jsonl"
EXCLUDED_FILES = {
    "_llm-test.md",          # internal test fixture for the translation tooling
    "translation-banner.md", # meta-page about the translation process
    "translations.md",       # meta-page about the translation process
    "fastapi-people.md",     # community/contributors page
    "help-fastapi.md",       # community page
    "external-links.md",     # community link roundup
    "newsletter.md",         # marketing
    "cloud.md",              # FastAPI Cloud product page (hosting service, not the framework)
    "fastapicloud.md",       # FastAPI Cloud product page
    "management.md",         # FastAPI Cloud product page
}

# Matches: {* ../../docs_src/some/path.py *}  or  {* ../../docs_src/some/path.py hl[1,3] *}
INCLUDE_PATTERN = re.compile(r"\{\*\s*(\S*docs_src/[^\s*]+)(?:\s+[^*]*)?\*\}")

CHUNK_SIZE = 800       # characters per chunk, before overlap
CHUNK_OVERLAP = 100    # characters shared between consecutive chunks, so a
                        # sentence split across a chunk boundary isn't lost


def resolve_includes(markdown_text: str) -> str:
    """Replace every {* docs_src/path *} placeholder with a real fenced code block."""

    def replace_one(match: re.Match) -> str:
        raw_path = match.group(1)                  # "../../docs_src/foo/bar.py"
        relative_path = raw_path.split("docs_src/", 1)[1]  # "foo/bar.py"
        source_file = DOCS_SRC_DIR / relative_path

        if not source_file.exists():
            # Don't crash the whole run over one missing example file
            # log it and leave a visible marker instead.
            print(f"  WARNING: missing include source: {source_file}")
            return f"[missing code example: {relative_path}]"

        code = source_file.read_text(encoding="utf-8")
        language = "python" if source_file.suffix == ".py" else ""
        return f"```{language}\n{code}\n```"

    return INCLUDE_PATTERN.sub(replace_one, markdown_text)


def guess_url(relative_md_path: Path) -> str:
    """Best-effort reconstruction of the live docs URL for citations."""
    slug = relative_md_path.with_suffix("").as_posix()
    slug = slug.removesuffix("/index")  # index.md pages live at the folder URL
    return f"https://fastapi.tiangolo.com/{slug}/"


def chunk_one_file(md_path: Path, header_splitter, text_splitter) -> list[dict]:
    relative_path = md_path.relative_to(DOCS_DIR)
    raw_text = md_path.read_text(encoding="utf-8")
    resolved_text = resolve_includes(raw_text)

    sections = header_splitter.split_text(resolved_text)

    chunks = []
    for section in sections:
        # section.metadata looks somthing like {"Header 1": "Tutorial", "Header 2": "First Steps"}
        header_path = " > ".join(section.metadata.values())
        sub_chunks = text_splitter.split_text(section.page_content)

        for sub_chunk in sub_chunks:
            chunks.append(
                {
                    "text": sub_chunk,
                    "source_type": "doc",
                    "source_path": relative_path.as_posix(),
                    "section": header_path,
                    "url": guess_url(relative_path),
                }
            )
    return chunks


def main():
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[("#", "Header 1"), ("##", "Header 2"), ("###", "Header 3")],
        strip_headers=False,  # keeps the header text IN the chunk too, not just metadata
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", " ", ""],
    )

    md_files = sorted(DOCS_DIR.rglob("*.md"))
    md_files = [f for f in md_files if f.name not in EXCLUDED_FILES]
    print(f"Found {len(md_files)} markdown files to chunk.")

    all_chunks = []
    for md_path in md_files:
        chunks = chunk_one_file(md_path, header_splitter, text_splitter)
        for i, chunk in enumerate(chunks):
            chunk["chunk_id"] = f"{chunk['source_path']}::{i}"
        all_chunks.extend(chunks)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT_PATH.open("w", encoding="utf-8") as f:
        for chunk in all_chunks:
            f.write(json.dumps(chunk) + "\n")

    print(f"Done. Wrote {len(all_chunks)} chunks from {len(md_files)} files to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()