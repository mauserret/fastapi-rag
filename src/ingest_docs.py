"""
Ingest FastAPI's documentation into data/raw/docs/ and data/raw/docs_src/.

What this does:
1. Shallow-clones the FastAPI repo into a temp folder (--depth 1 means it pulls
   the latest snapshot, not the whole git history, this is much faster and there's 
   no need of history for a RAG corpus).
2. Copies the English markdown docs (docs/en/docs/) into data/raw/docs/,
   preserving folder structure.
3. Also copies docs_src/ into data/raw/docs_src/. The markdown docs reference
   real code examples using a custom {* ../../docs_src/path/to/file.py *}
   syntax instead of embedding code directly. Without docs_src/, the chunks
   would contain broken placeholders instead of actual code, therefore 
   this folder is needed to resolve those includes during chunking.

To run:
    python src/ingest_docs.py
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/tiangolo/fastapi.git"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DOCS_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "docs"
DOCS_SRC_OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "docs_src"


def clone_repo(tmp_dir: Path) -> Path:
    """Shallow-clone the FastAPI repo into tmp_dir, return path to it."""
    print(f"Cloning {REPO_URL} (shallow, depth=1)...")
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(tmp_dir)],
        check=True,
        capture_output=True,
    )
    return tmp_dir


def copy_tree(source: Path, dest: Path, glob_pattern: str) -> int:
    """Copy source -> dest (wiping any old copy first), return matching file count."""
    if not source.exists():
        raise FileNotFoundError(
            f"Expected {source}, but it wasn't there. "
            "The repo structure may have changed — check manually."
        )
    if dest.exists():
        shutil.rmtree(dest)  # raw/ is write-once per run: clean slate each time
    shutil.copytree(source, dest)
    return len(list(dest.rglob(glob_pattern)))


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = clone_repo(Path(tmp))

        doc_count = copy_tree(
            repo_dir / "docs" / "en" / "docs", DOCS_OUTPUT_DIR, "*.md"
        )
        src_count = copy_tree(
            repo_dir / "docs_src", DOCS_SRC_OUTPUT_DIR, "*"
        )

    print(f"Done. Copied {doc_count} markdown files to {DOCS_OUTPUT_DIR}")
    print(f"Done. Copied {src_count} example code files to {DOCS_SRC_OUTPUT_DIR}")


if __name__ == "__main__":
    main()