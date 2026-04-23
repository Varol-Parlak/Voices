import json
import ollama
from pathlib import Path
from context import load_projects, detect_project, get_relevant_chunks
from memory import get_relevant_past
from tools import search_web

PROFILES_DIR = Path(__file__).parent / "profiles"
projects = load_projects()

def chat_once(question, active_model, active_voice, history, web_context="", project_context="", past_context=""):
    """
    Core chat generator. Yields text chunks as they stream in.
    Both the CLI and Flask call this — no duplication.
    """
    system_parts = [
        "You are a helpful personal AI assistant.",
        "CRITICAL INSTRUCTIONS:",
        "1. Keep your responses clear.",
        "2. If web search doesn't contain the specific data requested, admit you don't know it.",
        "3. User Information and Contexts are background only. Don't mention them unless relevant."
    ]

    user_info_file = PROFILES_DIR / "user_info.md"
    if user_info_file.exists():
        user_info = user_info_file.read_text(encoding="utf-8").strip()
        if user_info:
            system_parts.append(f"User Information:\n{user_info}")

    voice_file = PROFILES_DIR / f"{active_voice}.md"
    if voice_file.exists():
        voice_instructions = voice_file.read_text(encoding="utf-8").strip()
        if voice_instructions:
            system_parts.append(f"Active Persona:\n{voice_instructions}")

    if past_context:
        system_parts.append(f"Relevant past context:\n{past_context}")
    if project_context:
        system_parts.append(f"Relevant project files:\n{project_context}")
    if web_context:
        system_parts.append(f"Web Search context:\n{web_context}")

    system_prompt = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": question})

    stream = ollama.chat(
        model=active_model, 
        messages=messages, 
        stream=True,
        options={"num_ctx": 8192}
    )
    for chunk in stream:
        content = chunk["message"].get("content", "")
        if content:
            yield content