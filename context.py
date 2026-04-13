import json
import chromadb
from pathlib import Path
from memory import OllamaEmbeddings, CHROMA_DIR

PROJECTS_FILE       = Path(__file__).parent / "projects.json"
INDEX_CACHE_FILE    = Path(__file__).parent / "projects_cache.json"
CHUNK_SIZE          = 20   
TOP_K_CHUNKS        = 4    
INDEXED_EXTENSIONS  = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".js"}

_project_col = None

def _get_project_col():
    global _project_col
    if _project_col is None:
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _project_col = client.get_or_create_collection(
            name="projects_context",
            embedding_function=OllamaEmbeddings(),
        )
    return _project_col

def load_projects() -> dict:
    if PROJECTS_FILE.exists():
        return json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
    return {}

def detect_project(user_input: str, projects: dict) -> str | None:
    for keyword in projects:
        if keyword.lower() in user_input.lower():
            return keyword
    return None

def get_relevant_chunks(folders: list, query: str, top_k: int = TOP_K_CHUNKS) -> str:
    col = _get_project_col()
    
    if INDEX_CACHE_FILE.exists():
        try:
            cache = json.loads(INDEX_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    else:
        cache = {}

    for folder in folders:
        p = Path(folder)
        if not p.exists():
            print(f"  [!] Folder not found: {folder}")
            continue

        for file in p.rglob("*"):
            if file.suffix not in INDEXED_EXTENSIONS:
                continue
            
            try:
                mtime = file.stat().st_mtime
                str_path = str(file.resolve())
            except Exception:
                continue

            if cache.get(str_path) != mtime:
                # File is new or modified. Remove old chunks for this file if any.
                try:
                    col.delete(where={"file": str_path})
                except Exception:
                    pass
                
                try:
                    lines = file.read_text(encoding="utf-8", errors="ignore").splitlines()
                except Exception:
                    continue

                docs = []
                metadatas = []
                ids = []
                
                for i in range(0, len(lines), CHUNK_SIZE):
                    block = "\n".join(lines[i : i + CHUNK_SIZE]).strip()
                    if not block:
                        continue
                        
                    label = f"# [{file.name} lines {i}-{i + min(CHUNK_SIZE, len(lines)-i)}]"
                    docs.append(f"{label}\n{block}")
                    metadatas.append({"file": str_path, "folder": folder})
                    ids.append(f"{str_path}_{i}")

                if docs:
                    # Insert the new embeddings
                    # print(f"  [Indexing updated file: {file.name}]")  # Optional logging
                    col.add(documents=docs, metadatas=metadatas, ids=ids)
                    
                cache[str_path] = mtime

    # Save cache
    INDEX_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # Semantic Vector Search
    try:
        results = col.query(
            query_texts=[query],
            n_results=top_k,
            where={"folder": {"$in": [str(f) for f in folders]}}
        )
    except Exception as e:
        print(f"  [!] Semantic search error: {e}")
        return ""

    if not results.get("documents") or not results["documents"][0]:
        return ""

    return "\n\n".join(results["documents"][0])
