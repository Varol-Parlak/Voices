"""
memory.py — ChromaDB-backed conversation memory.

Each exchange is stored as:
  document : "User: {msg}\nAI: {reply}"
  metadata : {"date": "2026-04-09", "ts": 1712670000}
  id       : "2026-04-09_1712670000"

On startup  → load_today_history()  → rebuild history[] from today's entries (sorted by ts)
Each turn   → get_relevant_past()   → semantic search of OTHER days → inject into system prompt
After reply → save_exchange()       → embed + store new exchange
"""

import time
from datetime import date
from pathlib import Path
from typing import List

import chromadb
import ollama

# ── Config ────────────────────────────────────────────────────────────────────

CHROMA_DIR     = Path(__file__).parent / "memory" / "chroma"
COLLECTION     = "conversations"
MAX_TODAY_HIST = 20   # max past exchanges loaded from today (most recent N)
TOP_K_PAST     = 3    # relevant exchanges injected from other days

# ── Embedding function (calls local ollama) ───────────────────────────────────

class OllamaEmbeddings:
    def __call__(self, input: List[str]) -> List[List[float]]:
        return [
            ollama.embeddings(model="nomic-embed-text", prompt=text)["embedding"]
            for text in input
        ]

# ── Singleton collection ──────────────────────────────────────────────────────

_col = None

def _get_col():
    global _col
    if _col is None:
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _col = client.get_or_create_collection(
            name=COLLECTION,
            embedding_function=OllamaEmbeddings(),
        )
    return _col


# ── Public API ────────────────────────────────────────────────────────────────

def load_today_history() -> list:
    """
    Pull today's stored exchanges from ChromaDB, sort by timestamp,
    and return as a history[] list of {role, content} dicts.
    """
    today = date.today().isoformat()
    col   = _get_col()

    results = col.get(where={"date": today}, include=["documents", "metadatas"])
    if not results["ids"]:
        return []

    # Sort by timestamp so the order is correct
    pairs = sorted(
        zip(results["metadatas"], results["documents"]),
        key=lambda x: x[0]["ts"],
    )

    # Trim to the most recent MAX_TODAY_HIST exchanges
    pairs = pairs[-MAX_TODAY_HIST:]

    history = []
    for _, doc in pairs:
        user_part, _, ai_part = doc.partition("\nAI: ")
        user_msg = user_part.removeprefix("User: ")
        history.append({"role": "user",      "content": user_msg})
        history.append({"role": "assistant", "content": ai_part})

    return history


def save_exchange(user_msg: str, ai_msg: str):
    """Embed and persist a new exchange to ChromaDB."""
    today = date.today().isoformat()
    ts    = int(time.time())
    doc   = f"User: {user_msg}\nAI: {ai_msg}"

    _get_col().add(
        documents=[doc],
        metadatas=[{"date": today, "ts": ts}],
        ids=[f"{today}_{ts}"],
    )


def get_relevant_past(query: str) -> str:
    """
    Semantic search of past days (not today) for the most relevant exchanges.
    Returns a formatted string ready to inject into the system prompt.
    """
    today = date.today().isoformat()
    col   = _get_col()

    # Only search if there are non-today entries
    past = col.get(where={"date": {"$ne": today}})
    if not past["ids"]:
        return ""

    n = min(TOP_K_PAST, len(past["ids"]))
    results = col.query(
        query_texts=[query],
        n_results=n,
        where={"date": {"$ne": today}},
        include=["documents", "metadatas"],
    )

    if not results["ids"][0]:
        return ""

    parts = []
    for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
        parts.append(f"[{meta['date']}]\n{doc}")

    return "\n\n".join(parts)


def clear_today():
    """Remove today's exchanges from ChromaDB (for /context clear)."""
    today   = date.today().isoformat()
    col     = _get_col()
    results = col.get(where={"date": today})
    if results["ids"]:
        col.delete(ids=results["ids"])


def memory_stats() -> str:
    """Return a short summary of how much is stored."""
    col   = _get_col()
    today = date.today().isoformat()
    total = col.count()
    today_count = len(col.get(where={"date": today})["ids"])
    return f"{today_count} exchanges today · {total} total stored"
