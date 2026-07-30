"""
Ingest FastAPI's documentation into data/raw/docs/.

What this does:
1. Shallow-clones the FastAPI repo into a temp folder (--depth 1 means we only
   pull the latest snapshot, not the whole git history — much faster and we
   don't need history for a RAG corpus).
2. Copies just the English markdown docs (docs/en/docs/) into our own
   data/raw/docs/ folder, preserving the folder structure (some docs live in
   subfolders like tutorial/ or advanced/ — that structure is useful metadata
   later, so we keep it).

Run it with:
    python src/ingest_docs.py
"""

import shutil
import subprocess
import tempfile
from pathlib import Path

REPO_URL = "https://github.com/tiangolo/fastapi.git"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "docs"


def clone_repo(tmp_dir: Path) -> Path:
    """Shallow-clone the FastAPI repo into tmp_dir, return path to it."""
    print(f"Cloning {REPO_URL} (shallow, depth=1)...")
    subprocess.run(
        ["git", "clone", "--depth", "1", REPO_URL, str(tmp_dir)],
        check=True,
        capture_output=True,
    )
    return tmp_dir


def copy_docs(repo_dir: Path) -> int:
    """Copy the English docs markdown tree into OUTPUT_DIR. Returns file count."""
    source_docs = repo_dir / "docs" / "en" / "docs"
    if not source_docs.exists():
        raise FileNotFoundError(
            f"Expected docs at {source_docs}, but they weren't there. "
            "The repo structure may have changed — check manually."
        )

    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)  # raw/ is write-once per run: clean slate each time
    shutil.copytree(source_docs, OUTPUT_DIR)

    md_files = list(OUTPUT_DIR.rglob("*.md"))
    return len(md_files)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        repo_dir = clone_repo(Path(tmp))
        count = copy_docs(repo_dir)
    print(f"Done. Copied {count} markdown files to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()