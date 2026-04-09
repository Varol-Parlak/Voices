"""
context.py — Project foldering + keyword RAG.

Context stashing (old txt/summary approach) has been removed.
Memory is now handled entirely by memory.py (ChromaDB).
"""

import json
from pathlib import Path

PROJECTS_FILE       = Path(__file__).parent / "projects.json"
CHUNK_SIZE          = 20   # lines per chunk
TOP_K_CHUNKS        = 4    # max chunks injected per turn
INDEXED_EXTENSIONS  = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv"}


# ── Project foldering ─────────────────────────────────────────────────────────

def load_projects() -> dict:
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {}


def detect_project(user_input: str, projects: dict) -> str | None:
    for keyword in projects:
        if keyword.lower() in user_input.lower():
            return keyword
    return None


# ── Keyword RAG ───────────────────────────────────────────────────────────────

def get_relevant_chunks(folders: list, query: str, top_k: int = TOP_K_CHUNKS) -> str:
    """
    Scan project folders, split files into chunks, score by keyword overlap,
    return the top-k most relevant chunks as a formatted string.
    """
    chunks      = []
    query_words = set(query.lower().split())

    for folder in folders:
        p = Path(folder)
        if not p.exists():
            print(f"  [!] Folder not found: {folder}")
            continue

        for file in p.rglob("*"):
            if file.suffix not in INDEXED_EXTENSIONS:
                continue
            try:
                lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue

            for i in range(0, len(lines), CHUNK_SIZE):
                block       = "\n".join(lines[i : i + CHUNK_SIZE])
                block_words = set(block.lower().split())
                score       = len(query_words & block_words)
                if score > 0:
                    label = f"# [{file.name}  lines {i}–{i + CHUNK_SIZE}]"
                    chunks.append((score, f"{label}\n{block}"))

    if not chunks:
        return ""

    chunks.sort(reverse=True)
    return "\n\n".join(chunk for _, chunk in chunks[:top_k])
