import json
import chromadb
from pathlib import Path
from memory import OllamaEmbeddings, CHROMA_DIR

BASE_DIR            = Path(__file__).parent
GOALS_FILE          = BASE_DIR / "goals.json"
PROJECTS_FILE       = BASE_DIR / "projects.json"   # Legacy fallback
INDEX_CACHE_FILE    = BASE_DIR / "projects_cache.json"
CHUNK_SIZE          = 20   
TOP_K_CHUNKS        = 4    
INDEXED_EXTENSIONS  = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".csv", ".html", ".css", ".js"}
DISTANCE_THRESHOLD  = 400.0

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


# ==========================================
# GOALS SYSTEM
# ==========================================

def load_goals() -> dict:
    """Load goals.json. Falls back to projects.json for backwards compatibility."""
    if GOALS_FILE.exists():
        return json.loads(GOALS_FILE.read_text(encoding="utf-8"))
    # Legacy fallback: convert old projects.json format to goals format
    if PROJECTS_FILE.exists():
        old = json.loads(PROJECTS_FILE.read_text(encoding="utf-8"))
        goals = {}
        for keyword, paths in old.items():
            goal_id = keyword.replace(" ", "_")
            goals[goal_id] = {
                "keywords": [keyword],
                "folders": list(paths.values()),
                "profile": ""
            }
        return goals
    return {}


def detect_goals(user_input: str, goals: dict) -> list[str]:
    """
    Scan user input for goal keywords. Returns a list of matching goal IDs.
    Matches longest keywords first to avoid partial matches 
    (e.g. "exam ide" should match before "exam").
    """
    input_lower = user_input.lower()
    matched = []

    # Build a flat list of (keyword, goal_id) sorted by keyword length descending
    keyword_map = []
    for goal_id, goal_data in goals.items():
        for kw in goal_data.get("keywords", []):
            keyword_map.append((kw.lower(), goal_id))
    keyword_map.sort(key=lambda x: len(x[0]), reverse=True)

    for kw, goal_id in keyword_map:
        if kw in input_lower and goal_id not in matched:
            matched.append(goal_id)

    return matched


def get_goal_profile(goal_id: str, goals: dict) -> str:
    """Read the profile.md for a given goal. Returns empty string if not found."""
    goal_data = goals.get(goal_id, {})
    profile_path = goal_data.get("profile", "")
    if not profile_path:
        return ""
    
    full_path = BASE_DIR / profile_path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8").strip()
    return ""


def get_goal_folders(goal_id: str, goals: dict) -> list[str]:
    """Get the folder paths for a given goal."""
    return goals.get(goal_id, {}).get("folders", [])


# ==========================================
# LEGACY COMPAT (kept for imports that still use these)
# ==========================================

def load_projects() -> dict:
    """Legacy wrapper. Returns old-style {keyword: {label: path}} dict from goals."""
    goals = load_goals()
    projects = {}
    for goal_id, goal_data in goals.items():
        keywords = goal_data.get("keywords", [goal_id])
        folders = goal_data.get("folders", [])
        if keywords and folders:
            projects[keywords[0]] = {"pc": folders[0]}
    return projects


def detect_project(user_input: str, projects: dict) -> str | None:
    """Legacy wrapper kept for backwards compatibility."""
    for keyword in projects:
        if keyword.lower() in user_input.lower():
            return keyword
    return None


# ==========================================
# INDEXING & SEMANTIC SEARCH
# ==========================================

def get_relevant_chunks(folders: list, query: str, goal_id: str = "", top_k: int = TOP_K_CHUNKS) -> str:
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
                    meta = {"file": str_path, "folder": folder}
                    if goal_id:
                        meta["goal"] = goal_id
                    metadatas.append(meta)
                    ids.append(f"{str_path}_{i}")

                if docs:
                    col.add(documents=docs, metadatas=metadatas, ids=ids)
                    
                cache[str_path] = mtime

    # Save cache
    INDEX_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")

    # Semantic Vector Search — scoped to the goal's folders
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

    # Filter out chunks that are semantically unrelated
    distances = results.get("distances")
    valid_docs = []
    if distances and distances[0]:
        for doc, dist in zip(results["documents"][0], distances[0]):
            if dist < DISTANCE_THRESHOLD:
                valid_docs.append(doc)
    else:
        valid_docs = results["documents"][0]

    if not valid_docs:
        return ""

    return "\n\n".join(valid_docs)
