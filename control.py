import ollama
import subprocess
from router  import route
from context import load_projects, detect_project, get_relevant_chunks
from memory  import (
    load_today_history, save_exchange,
    get_relevant_past, clear_today, memory_stats,
)

# ── Startup ───────────────────────────────────────────────────────────────────

projects     = load_projects()
active_model = None
MAX_HISTORY  = 20   # cap on live in-session history (safety valve)

print("=" * 50)
print("  Personal AI Agent")
print("=" * 50)
print("  /stop  /context clear  /projects  /model  /history  /memory")
print("=" * 50)

print("\n[Loading memory...]", end=" ", flush=True)
history = load_today_history()
print(f"resumed {len(history) // 2} exchanges from today" if history else "fresh session")

# ── Main loop ─────────────────────────────────────────────────────────────────

while True:
    try:
        question = input("\nYou: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[Goodbye]")
        break

    if not question:
        continue

    # ── Built-in commands ─────────────────────────────────────────────────────

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
            role = "You" if msg["role"] == "user" else "AI"
            snippet = msg["content"][:80]
            ellipsis = "..." if len(msg["content"]) > 80 else ""
            print(f"  {role}: {snippet}{ellipsis}")
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

    # ── Model routing ─────────────────────────────────────────────────────────

    model = route(question)
    if model != active_model:
        print(f"[→ {model}]")
        active_model = model

    # ── Project foldering + keyword RAG ───────────────────────────────────────

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

    # ── Semantic past retrieval ───────────────────────────────────────────────

    past_context = get_relevant_past(question)

    # ── Build system prompt ───────────────────────────────────────────────────

    system_parts = ["You are a helpful personal AI assistant."]

    if past_context:
        system_parts.append(
            f"Relevant context from past conversations:\n{past_context}"
        )

    if project_context:
        system_parts.append(
            f"Relevant project file excerpts:\n{project_context}"
        )

    system_prompt = "\n\n".join(system_parts)

    # ── Build messages: system + today's history + new question ───────────────

    messages = [{"role": "system", "content": system_prompt}]
    messages += history
    messages.append({"role": "user", "content": question})

    # ── Stream response ───────────────────────────────────────────────────────

    response_content = ""
    stream = ollama.chat(model=model, messages=messages, stream=True)

    print(f"AI ({model}): ", end="", flush=True)
    for chunk in stream:
        content = chunk["message"]["content"]
        print(content, end="", flush=True)
        response_content += content
    print()

    # ── Update live history ───────────────────────────────────────────────────

    history.append({"role": "user",      "content": question})
    history.append({"role": "assistant", "content": response_content})

    # Safety cap — keep most recent MAX_HISTORY exchanges in RAM
    if len(history) > MAX_HISTORY * 2:
        history = history[-(MAX_HISTORY * 2):]

    # ── Persist to ChromaDB ───────────────────────────────────────────────────

    save_exchange(question, response_content)