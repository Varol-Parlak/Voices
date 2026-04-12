import urllib.request
import urllib.parse
import ssl
import re
import json
from pathlib import Path

def search_web(query: str) -> str:
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
            
            snippets = re.findall(r'<a class="result__snippet[^>]*>(.*?)</a>', html, re.IGNORECASE | re.DOTALL)
            
            clean_snippets = []
            for s in snippets:
                clean_s = re.sub(r'<[^>]+>', '', s)
                clean_s = clean_s.replace('&#39;', "'").replace('&quot;', '"').replace('&amp;', '&')
                clean_snippets.append(clean_s.strip())
                
            res = "\n---\n".join(clean_snippets[:5])
            if not res:
                return "No results found for the query."
            return "Search Results:\n" + res
            
    except Exception as e:
        return f"Search failed due to an error: {e}"

def read_file(filepath: str) -> str:
    print(f"\n[AI is reading file: '{filepath}'...]", flush=True)
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist."
        return path.read_text(encoding='utf-8', errors='ignore')
    except Exception as e:
        return f"Failed to read file: {e}"

def append_file(filepath: str, content: str) -> str:
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
