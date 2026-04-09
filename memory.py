import time
from datetime import date
from pathlib import Path
from typing import List

import chromadb
import ollama

CHROMA_DIR     = Path(__file__).parent / "memory" / "chroma"
COLLECTION     = "conversations"
MAX_TODAY_HIST = 20
TOP_K_PAST     = 10


class OllamaEmbeddings:
    def name(self) -> str:
        return "ollama-nomic-embed-text"

    def __call__(self, input: List[str]) -> List[List[float]]:
        return [
            ollama.embeddings(model="nomic-embed-text", prompt=text)["embedding"]
            for text in input
        ]


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


def load_today_history() -> list:
    today = date.today().isoformat()
    col   = _get_col()

    results = col.get(where={"date": today}, include=["documents", "metadatas"])
    if not results["ids"]:
        return []

    pairs = sorted(
        zip(results["metadatas"], results["documents"]),
        key=lambda x: x[0]["ts"],
    )
    pairs = pairs[-MAX_TODAY_HIST:]

    history = []
    for _, doc in pairs:
        user_part, _, ai_part = doc.partition("\nAI: ")
        user_msg = user_part.removeprefix("User: ")
        history.append({"role": "user",      "content": user_msg})
        history.append({"role": "assistant", "content": ai_part})

    return history


def save_exchange(user_msg: str, ai_msg: str):
    today = date.today().isoformat()
    ts    = int(time.time())
    doc   = f"User: {user_msg}\nAI: {ai_msg}"

    _get_col().add(
        documents=[doc],
        metadatas=[{"date": today, "ts": ts}],
        ids=[f"{today}_{ts}"],
    )


def get_relevant_past(query: str) -> str:
    today = date.today().isoformat()
    col   = _get_col()

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
    today   = date.today().isoformat()
    col     = _get_col()
    results = col.get(where={"date": today})
    if results["ids"]:
        col.delete(ids=results["ids"])


def memory_stats() -> str:
    col         = _get_col()
    today       = date.today().isoformat()
    total       = col.count()
    today_count = len(col.get(where={"date": today})["ids"])
    return f"{today_count} exchanges today · {total} total stored"
