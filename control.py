import ollama
import subprocess
from pathlib import Path
from router  import route
from tools import search_web
from context import load_projects, detect_project, get_relevant_chunks
from memory  import (
    load_today_history, save_exchange,
    get_relevant_past, clear_today, memory_stats,
)

projects     = load_projects()
active_model = None
MAX_HISTORY  = 20

print("=" * 50)
print("  Personal AI Agent")
print("=" * 50)
print("  /stop  /context clear  /projects  /model  /history  /memory")
print("=" * 50)

print("\n[Loading memory...]", end=" ", flush=True)
history = load_today_history()
print(f"resumed {len(history) // 2} exchanges from today" if history else "fresh session")

while True:
    try:
        question = input("\nYou: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[Goodbye]")
        break

    if not question:
        continue

    web_context = ""
    if question.startswith("/search "):
        query = question[8:].strip()
        if not query:
            print("[Please provide a search query]")
            continue
        web_context = search_web(query)
        question = query  # the model will just see the query

    if question == "/stop":
        if active_model:
            subprocess.run(["ollama", "stop", active_model], check=False)
            print(f"[Stopped {active_model}]")
            active_model = None
        else:
            print("[No active model to stop]")
        break

    if question == "/context clear":
        clear_today()
        history.clear()
        print("[Today's context cleared]")
        continue

    if question == "/history":
        if not history:
            print("[No history this session]")
        for msg in history:
            role    = "You" if msg["role"] == "user" else "AI"
            snippet = msg["content"][:80]
            suffix  = "..." if len(msg["content"]) > 80 else ""
            print(f"  {role}: {snippet}{suffix}")
        continue

    if question == "/memory":
        print(f"[Memory: {memory_stats()}]")
        continue

    if question == "/projects":
        if projects:
            for kw, paths in projects.items():
                print(f"  '{kw}':")
                for label, path in paths.items():
                    print(f"      {label}: {path}")
        else:
            print("[No projects configured in projects.json]")
        continue

    if question == "/model":
        print(f"[Active model: {active_model or 'none yet'}]")
        continue

    model = route(question, active_model)
    if model != active_model:
        if active_model is not None:
            print(f"[Stopping {active_model}]")
            subprocess.run(["ollama", "stop", active_model], check=False)
            print(f"[Switched to {model}]")
        active_model = model

    project_context = ""
    detected = detect_project(question, projects)
    if detected:
        folders = list(projects[detected].values())
        print(f"[Project '{detected}' — scanning {len(folders)} folder(s)...]")
        project_context = get_relevant_chunks(folders, question)
        if project_context:
            print(f"[Injected {len(project_context)} chars of project code]")
        else:
            print("[No matching chunks found]")

    past_context = get_relevant_past(question)

    system_parts = [
        "You are a helpful personal AI assistant.",
        "IMPORTANT: The following User Information and Contexts are for your background knowledge only.",
        "Do NOT acknowledge them or explicitly mention them in your responses unless relevant to the user's request."
    ]

    user_info_file = Path(__file__).parent / "user_info.md"
    if user_info_file.exists():
        user_info = user_info_file.read_text(encoding="utf-8").strip()
        if user_info:
            system_parts.append(f"User Information:\n{user_info}")

    if past_context:
        system_parts.append(f"Relevant context from past conversations:\n{past_context}")
    if project_context:
        system_parts.append(f"Relevant project file excerpts:\n{project_context}")
    if web_context:
        system_parts.append(f"Live Web Search context for this query:\n{web_context}")
    system_prompt = "\n\n".join(system_parts)

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": question})

    response_content = ""
    stream = ollama.chat(model=model, messages=messages, stream=True)

    print(f"AI ({model}): ", end="", flush=True)
    for chunk in stream:
        content = chunk["message"].get("content", "")
        if content:
            print(content, end="", flush=True)
            response_content += content
    print()

    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": response_content})

    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]

    save_exchange(question, response_content)