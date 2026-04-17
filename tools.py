import urllib.request
import urllib.parse
import ssl
import re
import json
from pathlib import Path
import os

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
    """
    Reads a file and returns its content with 1-indexed line numbers prepended to each line.
    Use this tool to inspect a file's contents before attempting to edit it, so you know the exact line numbers to target.

    Args:
        filepath (str): The absolute or relative path to the file you want to read.
    
    Returns:
        str: The file contents with line numbers, or an error message if the file is not found.
    """
    if os.path.exists(filepath) and os.path.isfile(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            numbered_lines = []
            for index, line in enumerate(lines, start=1):
                numbered_lines.append(f"{index}: {line.rstrip('\n')}")
            
            return "\n".join(numbered_lines)
        except Exception as e:
            return f"Error reading file: {e}"

    filename = os.path.basename(filepath)
    return f"Error: File '{filepath}' does not exist. (Tip: Use list_dir first to confirm the exact path)"

def append_file(filepath: str, content: str) -> str:
    """
    Appends new text or code to the very end of an existing file. 
    Use this tool only when you need to add new content to the bottom of a file without modifying any existing code.

    Args:
        filepath (str): The path to the file you want to modify.
        content (str): The exact text to append. It will automatically be placed on a new line.
        
    Returns:
        str: A success or failure message.
    """
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

def list_dir(folder_path: str) -> str:
    """
    Lists all files and subdirectories inside a given directory path.
    Use this tool to explore the project structure or verify a file's exact name and path before reading or editing.

    Args:
        folder_path (str): The absolute or relative directory path to explore.
        
    Returns:
        str: A list of items in the directory, or an error message if the directory is invalid.
    """
    clean_path = os.path.normpath(folder_path.strip())
    try:
        items = os.listdir(clean_path)
        return f"Contents of {clean_path}:\n" + "\n".join(items)
    except Exception as e:
        return f"Error: Could not read directory. {str(e)}"

def replace_in_file(filepath: str, start_line: int, end_line: int, new_code: str) -> str:
    """
    Replaces a specific range of lines in a file with new code.
    CRITICAL: You must use the read_file tool first to determine the exact start_line and end_line.
    
    Args:
        filepath (str): The path to the file you want to edit.
        start_line (int): The first line number to be replaced (1-indexed).
        end_line (int): The last line number to be replaced (inclusive).
        new_code (str): The exact replacement code to insert. It must be perfectly indented to match the file.
        
    Returns:
        str: A success or failure message.
    """
    print(f"\n[AI is editing file: '{filepath}' (Lines {start_line}-{end_line})...]", flush=True)
    try:
        path = Path(filepath)
        if not path.exists():
            return f"Error: File '{filepath}' does not exist."
        
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        start_index = start_line - 1
        end_index = end_line
        
        if start_index < 0: 
            start_index = 0
        if end_index > len(lines): 
            end_index = len(lines)
        
        if not new_code.endswith('\n'):
            new_code += '\n'
        
        updated_lines = lines[:start_index] + [new_code] + lines[end_index:]
        
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(updated_lines)
            
        return f"Successfully edited '{filepath}'. Replaced lines {start_line} through {end_line}."
    except Exception as e:
        return f"Failed to edit file: {e}"