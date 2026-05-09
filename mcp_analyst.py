import os
import asyncio
from pathlib import Path
from mcp.server.fastmcp import FastMCP
from langchain_ollama import ChatOllama
from browser_use import Agent

mcp = FastMCP("Analyst")

@mcp.tool()
def explore_project(folder_path: str) -> str:
    """
    Lists all files in a directory. 
    Use this to understand the project structure before reading specific files.
    Ignores hidden files and heavy directories like __pycache__ or .git.
    """
    clean_path = os.path.normpath(folder_path.strip())
    try:
        items = []
        for item in os.listdir(clean_path):
            if item.startswith('.') or item == '__pycache__':
                continue
            item_path = os.path.join(clean_path, item)
            if os.path.isdir(item_path):
                items.append(f"📁 {item}/")
            else:
                items.append(f"📄 {item}")
        
        return f"Contents of {clean_path}:\n" + "\n".join(sorted(items))
    except Exception as e:
        return f"Error reading directory: {str(e)}"

@mcp.tool()
def read_for_review(filepath: str) -> str:
    """
    Reads a source code file and prepends 1-indexed line numbers.
    Use this to read code and point out exact line numbers when finding bugs or safety issues.
    """
    if os.path.exists(filepath) and os.path.isfile(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            numbered_lines = [f"{i}: {line.rstrip('\n')}" for i, line in enumerate(lines, start=1)]
            return f"--- FILE: {filepath} ---\n" + "\n".join(numbered_lines)
        except Exception as e:
            return f"Error reading file: {e}"
            
    return f"Error: File '{filepath}' does not exist."

@mcp.tool()
def grep_codebase(folder_path: str, search_term: str) -> str:
    """
    Searches for a specific keyword, variable, or function name across all Python files in a folder.
    Use this to trace where a function is called or where variables are defined across multiple files.
    """
    clean_path = os.path.normpath(folder_path.strip())
    results = []
    
    try:
        for root, _, files in os.walk(clean_path):
            if '__pycache__' in root or '/.' in root or '\\.' in root:
                continue
                
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8') as f:
                            for i, line in enumerate(f, start=1):
                                if search_term in line:
                                    results.append(f"{os.path.relpath(filepath, clean_path)} (Line {i}): {line.strip()}")
                    except Exception:
                        continue 
                        
        if not results:
            return f"No matches found for '{search_term}' in {clean_path}."
            
        return f"Search results for '{search_term}':\n" + "\n".join(results)
    except Exception as e:
        return f"Search failed: {e}"

@mcp.tool()
async def search_web(query: str, model_name: str = "llama3.1:8b") -> str:
    """
    Searches the web using a Browser Agent to find up-to-date information.
    """
    print(f"\n[AI is searching the web using Browser Agent for: '{query}' with model {model_name}...]", flush=True)
    
    llm = ChatOllama(model=model_name, num_ctx=32000)
    agent = Agent(
        task=query,
        llm=llm,
    )
    
    try:
        result = await agent.run()
        if hasattr(result, "final_result"):
            final_ans = result.final_result()
            if final_ans:
                return f"Search Results:\n{final_ans}"
        return f"Search Results:\n{str(result)}"
    except Exception as e:
        return f"Browser search failed: {e}"

@mcp.tool()
def append_file(filepath: str, content: str) -> str:
    """
    Appends new text or code to the very end of an existing file. 
    Use this tool only when you need to add new content to the bottom of a file without modifying any existing code.
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

@mcp.tool()
def replace_in_file(filepath: str, start_line: int, end_line: int, new_code: str) -> str:
    """
    Replaces a specific range of lines in a file with new code.
    CRITICAL: You must use the read_for_review tool first to determine the exact start_line and end_line.
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


if __name__ == "__main__":
    mcp.run()