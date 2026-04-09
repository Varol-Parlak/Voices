import urllib.request
import urllib.parse
import ssl
import re
import json
from pathlib import Path

def search_web(query: str) -> str:
    """Use this tool ONLY to search the internet for real-time information, current events, or specific facts you don't confidently know. Do NOT use this tool for conversational chit-chat, personal questions, or general knowledge."""
    print(f"\n[AI is searching the web for: '{query}'...]", flush=True)
    
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    encoded_query = urllib.parse.quote(query)
    req = urllib.request.Request(
        f"https://html.duckduckgo.com/html/?q={encoded_query}",
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )
    
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=10) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
            # Extract basic result snippets from DuckDuckGo lite HTML
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            
            clean_snippets = []
            for s in snippets:
                # Remove HTML tags
                clean_s = re.sub(r'<[^>]+>', '', s)
                # Decode basic HTML entities
                clean_s = clean_s.replace('&#39;', "'").replace('&quot;', '"').replace('&amp;', '&')
                clean_snippets.append(clean_s.strip())
                
            res = "\n---\n".join(clean_snippets[:5])
            if not res:
                return "No results found for the query."
            return "Search Results:\n" + res
            
    except Exception as e:
        return f"Search failed due to an error: {e}"

def read_file(filepath: str) -> str:
    """Reads and returns the entire text contents of a local file. Use this to analyze code before modifying it."""
    print(f"\n[AI is reading file: '{filepath}'...]", flush=True)
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist."
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return f"Failed to read file: {e}"

def append_file(filepath: str, content: str) -> str:
    """Appends new text to the end of a local file. Use this to add lines without destroying existing content."""
    print(f"\n[AI is appending to file: '{filepath}'...]", flush=True)
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist."
        with path.open("a", encoding="utf-8") as f:
            if not content.startswith('\n'):
                f.write('\n')
            f.write(content)
        return f"Successfully appended content to '{filepath}'."
    except Exception as e:
        return f"Failed to append to file: {e}"

def replace_in_file(filepath: str, target: str, replacement: str) -> str:
    """Replaces an exact target string with a new string in a file. Use this for specific edits."""
    print(f"\n[AI is editing file: '{filepath}'...]", flush=True)
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist."
        text = path.read_text(encoding="utf-8")
        if target not in text:
            return f"Error: Target text not found in the file. You must match the string exactly."
        text = text.replace(target, replacement)
        path.write_text(text, encoding="utf-8")
        return f"Successfully edited '{filepath}'."
    except Exception as e:
        return f"Failed to edit file: {e}"
