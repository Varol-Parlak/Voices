import ollama
import subprocess
from pathlib import Path
from router  import route
from tools import search_web, read_file, append_file, replace_in_file
from context import load_projects, detect_project, get_relevant_chunks
from memory  import (
    load_today_history, save_exchange,
    get_relevant_past, clear_today, memory_stats,
)

projects     = load_projects()
active_model = None
MAX_HISTORY  = 20

print("=" * 70)
print("  Personal AI Agent")
print("=" * 70)
print("  /stop  /context clear  /projects  /model  /history  /memory /agent")
print("=" * 70)

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

    from router import MODEL_TRIGGERS, DEFAULT_MODEL

    if question == "/model":
        print(f"[Active model: {active_model or 'none yet'}]")
        continue

    if question.startswith("/model "):
        parts = question.split(maxsplit=2)
        target = parts[1].lower()
        if target in MODEL_TRIGGERS:
            new_model = MODEL_TRIGGERS[target]
            if new_model != active_model:
                if active_model is not None:
                    print(f"[Stopping {active_model}]")
                    subprocess.run(["ollama", "stop", active_model], check=False)
                print(f"[Switched to {new_model}]")
                active_model = new_model
        else:
            print(f"[Unknown model alias '{target}'. Known: {', '.join(MODEL_TRIGGERS.keys())}]")
        
        if len(parts) > 2:
            question = parts[2].strip()
            if not question:
                continue
        else:
            continue

    if active_model is None:
        active_model = DEFAULT_MODEL

    web_context = ""
    if question.startswith("/search "):
        query = question[8:].strip()
        if not query:
            print("[Please provide a search query]")
            continue
        web_context = search_web(query)
        question = query  # the model will just see the query

    if question.startswith("/agent "):
        agent_query = question[7:].strip()
        if not agent_query:
            print("[Please provide an agent instruction]")
            continue
            
        print(f"\n[Starting agent loop for: '{agent_query}']")
        
        agent_project = detect_project(agent_query, projects)
        project_info = ""
        if agent_project:
            dirs = list(projects[agent_project].values())
            project_info = f"\n            User referenced project '{agent_project}'.\n            Project Directories: {dirs}\n            Use these paths to locate files."
            print(f"[Agent context loaded for project: '{agent_project}']")

        agent_system = f"""You are an autonomous file-editing agent.
            Your Current Working Directory is: {Path.cwd()}{project_info}
            You have access to read_file, append_file, and replace_in_file tools.
            CRITICAL INSTRUCTIONS:
            1. You MUST use the native tool calling schema. DO NOT output conversational text describing the JSON.
            2. DO NOT overwrite entire files. To edit a file, use read_file to see its contents, then use append_file for adding lines, or replace_in_file for tweaking existing lines.
            3. You may ONLY edit files explicitly requested by the user. If they mention a project, use the provided Project Directories as the base path.
            4. Provide a final summary of your changes when finished."""
        
        agent_messages = [{"role": "system", "content": agent_system}]
        agent_messages.append({"role": "user", "content": agent_query})
        
        agent_model = active_model or "llama3.1:8b"
        MAX_STEPS = 6
        steps = 0
        last_call_signatures = []   # track recent (fn_name, args_str) to detect loops
        
        while steps < MAX_STEPS:
            steps += 1
            
            try:
                resp = ollama.chat(model=agent_model, messages=agent_messages, tools=[read_file, append_file, replace_in_file], stream=False)
            except Exception as e:
                print(f"[Agent crashed: {e}]")
                break
                
            msg = resp.get("message", {})
            agent_messages.append(msg)
            
            tool_calls = msg.get("tool_calls")
            if not tool_calls:
                final_text = msg.get("content", "")
                try:
                    import json
                    objects = []
                    i = 0
                    while i < len(final_text):
                        char = final_text[i]
                        if char == '{':
                            brace_count = 1
                            start = i
                            i += 1
                            in_str = False
                            escape_next = False
                            while i < len(final_text) and brace_count > 0:
                                c = final_text[i]
                                if escape_next:
                                    escape_next = False
                                elif c == '\\':
                                    escape_next = True
                                elif c == '"':
                                    in_str = not in_str
                                elif not in_str:
                                    if c == '{':
                                        brace_count += 1
                                    elif c == '}':
                                        brace_count -= 1
                                i += 1
                            if brace_count == 0:
                                objects.append(final_text[start:i])
                        else:
                            i += 1

                    found_tools = []
                    for obj in objects:
                        try:
                            parsed = json.loads(obj)
                            if isinstance(parsed, dict) and "name" in parsed and "arguments" in parsed:
                                found_tools.append({"function": parsed})
                        except Exception:
                            pass
                            
                    if found_tools:
                        tool_calls = found_tools
                except Exception:
                    pass

            if not tool_calls:
                final_text = msg.get("content", "")
                if final_text:
                    print(f"\nAI ({agent_model}): {final_text}\n")
                history.append({"role": "user", "content": question})
                history.append({"role": "assistant", "content": final_text})
                save_exchange(question, final_text)
                break
            
            # --- Loop detection: check if model is repeating the same calls ---
            import json as _json
            current_signatures = [
                (tc["function"]["name"], _json.dumps(tc["function"]["arguments"], sort_keys=True))
                for tc in tool_calls
            ]
            if current_signatures == last_call_signatures:
                print(f"\n[Agent detected in infinite loop — same tool calls repeated. Stopping.]")
                break
            last_call_signatures = current_signatures

            for tc in tool_calls:
                fn_name = tc["function"]["name"]
                args    = tc["function"]["arguments"]
                
                if fn_name == "read_file":
                    res_body = read_file(args.get("filepath", ""))
                elif fn_name == "append_file":
                    res_body = append_file(args.get("filepath", ""), args.get("content", ""))
                elif fn_name == "replace_in_file":
                    res_body = replace_in_file(args.get("filepath", ""), args.get("target", ""), args.get("replacement", ""))
                else:
                    res_body = "Error: Unknown tool."
                    
                if res_body.startswith("Error:"):
                    res_body += (
                        "\n\nRECOVERY HINT: Your last action failed. "
                        "Use read_file to re-read the current file contents first, "
                        "then try a DIFFERENT approach. Do NOT repeat the same failing action."
                    )
                    print(f"  [Tool error — stopping batch early]")
                    agent_messages.append({
                        "role": "tool",
                        "content": res_body,
                        "name": fn_name
                    })
                    break   # ← stop the batch; let model recover on next step
                    
                agent_messages.append({
                    "role": "tool",
                    "content": res_body,
                    "name": fn_name
                })
        
        if steps >= MAX_STEPS:
            print(f"\n[Agent reached max steps ({MAX_STEPS}) and stopped.]")
            
        continue

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
        "CRITICAL INSTRUCTIONS:",
        "1. Keep your responses extremely concise and to the point. Do not write unnecessary fluff paragraphs.",
        "2. If you are provided with Web Search but it doesn't contain the specific data requested (e.g. the exact temperature or time), you MUST admit you don't know it. Do NOT hallucinate placeholders.",
        "3. The following User Information and Contexts are for your background knowledge only. Do NOT explicitly mention them unless relevant."
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
    stream = ollama.chat(model=active_model, messages=messages, stream=True)

    print(f"AI ({active_model}): ", end="", flush=True)
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