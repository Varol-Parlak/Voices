import json
import chromadb
import ast
import time
import threading
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
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
# INDEXING & SEMANTIC SEARCH (OPTIMIZED WITH BACKGROUND WATCHER, AST CHUNKING, & HYBRID SEARCH)
# ==========================================

def chunk_by_lines(filepath: Path) -> list[tuple[str, int, int]]:
    """
    Fallback line-based chunking.
    """
    try:
        lines = filepath.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return []
    
    chunks = []
    for i in range(0, len(lines), CHUNK_SIZE):
        block = "\n".join(lines[i : i + CHUNK_SIZE]).strip()
        if block:
            chunks.append((block, i + 1, i + min(CHUNK_SIZE, len(lines) - i)))
    return chunks


def split_if_too_large(chunk_text: str, start_line: int, max_lines: int = CHUNK_SIZE * 2) -> list[tuple[str, int, int]]:
    lines = chunk_text.splitlines()
    if len(lines) <= max_lines:
        return [(chunk_text, start_line, start_line + len(lines) - 1)]
        
    sub_chunks = []
    for i in range(0, len(lines), CHUNK_SIZE):
        block = "\n".join(lines[i : i + CHUNK_SIZE]).strip()
        if block:
            sub_chunks.append((block, start_line + i, start_line + i + min(CHUNK_SIZE, len(lines) - i) - 1))
    return sub_chunks


def chunk_python_file(filepath: Path) -> list[tuple[str, int, int]]:
    """
    Chunk python files using AST to identify logical blocks (functions/classes).
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source)
    except Exception:
        return chunk_by_lines(filepath)

    lines = source.splitlines()
    chunks = []
    
    # Gather top-level classes and functions
    nodes = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            nodes.append(node)
            
    nodes.sort(key=lambda x: x.lineno)
    
    last_end = 0
    for node in nodes:
        start = node.lineno - 1
        end = getattr(node, "end_lineno", None)
        if end is None:
            end = len(lines)
            
        # If there's module-level code before this class/function, chunk it
        if start > last_end:
            module_chunk = "\n".join(lines[last_end:start]).strip()
            if module_chunk:
                chunks.extend(split_if_too_large(module_chunk, last_end + 1))
        
        node_chunk = "\n".join(lines[start:end]).strip()
        if node_chunk:
            chunks.extend(split_if_too_large(node_chunk, start + 1))
        last_end = end
        
    # Catch trailing module-level code
    if last_end < len(lines):
        module_chunk = "\n".join(lines[last_end:]).strip()
        if module_chunk:
            chunks.extend(split_if_too_large(module_chunk, last_end + 1))
                    
    if not chunks:
        return chunk_by_lines(filepath)
        
    return chunks


def chunk_non_python_file(filepath: Path) -> list[tuple[str, int, int]]:
    """
    Chunk non-python files (JS, CSS, HTML, MD, etc.) by grouping paragraph/blocks split by double newlines.
    """
    try:
        source = filepath.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return []
        
    lines = source.splitlines()
    chunks = []
    current_chunk = []
    start_line = 1
    
    for idx, line in enumerate(lines, start=1):
        current_chunk.append(line)
        if (not line.strip() and len(current_chunk) >= CHUNK_SIZE) or len(current_chunk) >= CHUNK_SIZE * 2:
            chunk_text = "\n".join(current_chunk).strip()
            if chunk_text:
                chunks.extend(split_if_too_large(chunk_text, start_line))
            current_chunk = []
            start_line = idx + 1
            
    if current_chunk:
        chunk_text = "\n".join(current_chunk).strip()
        if chunk_text:
            chunks.extend(split_if_too_large(chunk_text, start_line))
            
    return chunks


def update_cache(str_path: str, mtime: float):
    cache = {}
    if INDEX_CACHE_FILE.exists():
        try:
            cache = json.loads(INDEX_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    cache[str_path] = mtime
    try:
        INDEX_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def remove_from_cache(str_path: str):
    cache = {}
    if INDEX_CACHE_FILE.exists():
        try:
            cache = json.loads(INDEX_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    if str_path in cache:
        del cache[str_path]
        try:
            INDEX_CACHE_FILE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
        except Exception:
            pass


def index_single_file(filepath: Path, folder: str, goal_id: str):
    col = _get_project_col()
    str_path = str(filepath.resolve())
    
    try:
        col.delete(where={"file": str_path})
    except Exception:
        pass
        
    try:
        if not filepath.exists() or not filepath.is_file():
            return
            
        # Avoid massive files (>5MB)
        if filepath.stat().st_size > 5 * 1024 * 1024:
            return
            
        if filepath.suffix == ".py":
            chunks = chunk_python_file(filepath)
        else:
            chunks = chunk_non_python_file(filepath)
            
        docs = []
        metadatas = []
        ids = []
        
        for idx, (chunk_text, start_line, end_line) in enumerate(chunks):
            label = f"# [{filepath.name} lines {start_line}-{end_line}]"
            docs.append(f"{label}\n{chunk_text}")
            meta = {"file": str_path, "folder": str(Path(folder).resolve())}
            if goal_id:
                meta["goal"] = goal_id
            metadatas.append(meta)
            ids.append(f"{str_path}_{idx}")
            
        if docs:
            col.add(documents=docs, metadatas=metadatas, ids=ids)
            
        update_cache(str_path, filepath.stat().st_mtime)
    except Exception as e:
        print(f"[Watcher] Error indexing {filepath.name}: {e}")


def delete_single_file(filepath: Path):
    col = _get_project_col()
    str_path = str(filepath.resolve())
    try:
        col.delete(where={"file": str_path})
        remove_from_cache(str_path)
    except Exception as e:
        print(f"[Watcher] Error deleting {filepath.name}: {e}")


class ProjectFileHandler(FileSystemEventHandler):
    def __init__(self, folder_path, goal_id=""):
        super().__init__()
        self.folder_path = folder_path
        self.goal_id = goal_id

    def on_modified(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.suffix in INDEXED_EXTENSIONS:
            print(f"[Watcher] File modified: {filepath.name}")
            index_single_file(filepath, self.folder_path, self.goal_id)

    def on_created(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.suffix in INDEXED_EXTENSIONS:
            print(f"[Watcher] File created: {filepath.name}")
            index_single_file(filepath, self.folder_path, self.goal_id)

    def on_deleted(self, event):
        if event.is_directory:
            return
        filepath = Path(event.src_path)
        if filepath.suffix in INDEXED_EXTENSIONS:
            print(f"[Watcher] File deleted: {filepath.name}")
            delete_single_file(filepath)

    def on_moved(self, event):
        if event.is_directory:
            return
        src_path = Path(event.src_path)
        dest_path = Path(event.dest_path)
        if src_path.suffix in INDEXED_EXTENSIONS:
            print(f"[Watcher] File moved from: {src_path.name} to {dest_path.name}")
            delete_single_file(src_path)
        if dest_path.suffix in INDEXED_EXTENSIONS:
            index_single_file(dest_path, self.folder_path, self.goal_id)


def sync_all_goals():
    print("[Watcher] Syncing project files with database...")
    goals_dict = load_goals()
    
    if INDEX_CACHE_FILE.exists():
        try:
            cache = json.loads(INDEX_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    else:
        cache = {}
        
    for goal_id, goal_data in goals_dict.items():
        folders = goal_data.get("folders", [])
        for folder in folders:
            p = Path(folder)
            if not p.exists():
                continue
                
            for file in p.rglob("*"):
                if file.is_file() and file.suffix in INDEXED_EXTENSIONS:
                    try:
                        mtime = file.stat().st_mtime
                        str_path = str(file.resolve())
                    except Exception:
                        continue
                        
                    if cache.get(str_path) != mtime:
                        print(f"[Watcher] Sync indexing: {file.name}")
                        index_single_file(file, folder, goal_id)
                        cache[str_path] = mtime
                        
    print("[Watcher] Project files sync complete.")


def schedule_folders(observer):
    goals_dict = load_goals()
    scheduled = set()
    for goal_id, goal_data in goals_dict.items():
        folders = goal_data.get("folders", [])
        for folder in folders:
            folder_path = Path(folder)
            if folder_path.exists() and folder_path.is_dir():
                clean_path = str(folder_path.resolve())
                if clean_path not in scheduled:
                    print(f"[Watcher] Scheduling folder: {clean_path} for goal {goal_id}")
                    observer.schedule(
                        ProjectFileHandler(clean_path, goal_id),
                        path=clean_path,
                        recursive=True
                    )
                    scheduled.add(clean_path)


def _watcher_loop():
    print("[Watcher] Starting background loop...")
    try:
        sync_all_goals()
    except Exception as e:
        print(f"[Watcher] Error in initial sync: {e}")
        
    last_goals_mtime = 0
    if GOALS_FILE.exists():
        last_goals_mtime = GOALS_FILE.stat().st_mtime
        
    observer = Observer()
    schedule_folders(observer)
    observer.start()
    
    try:
        while True:
            time.sleep(5)
            if GOALS_FILE.exists():
                mtime = GOALS_FILE.stat().st_mtime
                if mtime != last_goals_mtime:
                    print("[Watcher] goals.json changed. Restarting observer...")
                    last_goals_mtime = mtime
                    observer.stop()
                    observer.join()
                    
                    observer = Observer()
                    schedule_folders(observer)
                    observer.start()
    except Exception as e:
        print(f"[Watcher] Watcher thread encountered error: {e}")
    finally:
        observer.stop()
        observer.join()


def start_background_watcher():
    thread = threading.Thread(target=_watcher_loop, daemon=True)
    thread.start()


def lexical_score(document: str, query: str) -> float:
    """
    Calculates a simple lexical score (0.0 to 1.0+) based on keyword matching.
    """
    query_words = [w.lower() for w in query.split() if len(w) > 2]
    if not query_words:
        return 0.0
        
    doc_lower = document.lower()
    score = 0.0
    
    # Exact phrase match bonus
    if query.lower() in doc_lower:
        score += 2.0
        
    # Individual keyword match
    matched_words = 0
    for word in query_words:
        if word in doc_lower:
            matched_words += 1
            freq = doc_lower.count(word)
            score += 0.5 * min(freq, 5) # Cap frequency to prevent spamming
            
    coverage = matched_words / len(query_words)
    score += coverage * 1.5
    
    return score


def query_hybrid_search(folders: list, query: str, goal_id: str = "", top_k: int = TOP_K_CHUNKS) -> str:
    col = _get_project_col()
    folder_strings = [str(Path(f).resolve()) for f in folders]
    
    try:
        total_chunks = col.count()
        if total_chunks == 0:
            return ""
            
        n_candidates = min(25, total_chunks)
        results = col.query(
            query_texts=[query],
            n_results=n_candidates,
            where={"folder": {"$in": folder_strings}}
        )
    except Exception as e:
        print(f"  [!] Hybrid search query error: {e}")
        return ""
        
    if not results.get("documents") or not results["documents"][0]:
        return ""
        
    documents = results["documents"][0]
    distances = results.get("distances", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    
    scored_candidates = []
    
    for idx, doc in enumerate(documents):
        distance = distances[idx] if idx < len(distances) else DISTANCE_THRESHOLD
        
        # Calculate semantic similarity
        semantic_sim = max(0.0, 1.0 - (distance / DISTANCE_THRESHOLD))
        
        # Calculate lexical score
        lex_score = lexical_score(doc, query)
        
        # Hybrid combined score
        combined_score = (1.0 * semantic_sim) + (0.8 * lex_score)
        
        if distance < DISTANCE_THRESHOLD or lex_score > 0.1:
            scored_candidates.append({
                "doc": doc,
                "score": combined_score
            })
            
    scored_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = scored_candidates[:top_k]
    
    if not top_candidates:
        return ""
        
    return "\n\n".join(c["doc"] for c in top_candidates)


def get_relevant_chunks(folders: list, query: str, goal_id: str = "", top_k: int = TOP_K_CHUNKS) -> str:
    return query_hybrid_search(folders, query, goal_id, top_k)
