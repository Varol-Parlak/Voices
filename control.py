import ollama
import subprocess
import json
from pathlib import Path

from router import MODEL_TRIGGERS, DEFAULT_MODEL
from tools import search_web, read_file, append_file, replace_in_file, list_dir
from context import load_projects, detect_project, get_relevant_chunks
from memory import load_today_history, save_exchange, get_relevant_past, clear_today

from chat_core import chat_once

PROFILES_DIR = Path(__file__).parent / "profiles"

projects     = load_projects()
active_model = DEFAULT_MODEL
active_voice = "p_friend"  

def process_message(question):
    """
    Takes the user question from the UI, routes it to the right command or agent,
    and returns either a string (for fast commands) or a generator (for streams).
    """
    global active_model, active_voice

    if active_model is None:
        active_model = DEFAULT_MODEL

    if question == "/voice":
        voices = sorted(p.stem.replace("p_", "") for p in PROFILES_DIR.glob("p_*.md"))
        return f"[Active voice: {active_voice.replace('p_', '')}]  Available: {', '.join(voices)}"

    if question.startswith("/voice "):
        parts = question.split(maxsplit=2)
        if len(parts) > 1:
            target_voice = parts[1].strip().lower()
            voice_file = PROFILES_DIR / f"p_{target_voice}.md"
            if voice_file.exists():
                active_voice = f"p_{target_voice}"
                return f"[Switched voice to '{target_voice}']"
            else:
                voices = sorted(p.stem.replace("p_", "") for p in PROFILES_DIR.glob("p_*.md"))
                return f"[Voice '{target_voice}' not found. Available: {', '.join(voices)}]"
        return "[Please provide a voice name]"

    if question == "/model":
        return f"[Active model: {active_model}]"

    if question.startswith("/model "):
        parts = question.split(maxsplit=2)
        if len(parts) > 1:
            target = parts[1].lower()
            if target in MODEL_TRIGGERS:
                new_model = MODEL_TRIGGERS[target]
                if new_model != active_model:
                    if active_model is not None:
                        subprocess.run(["ollama", "stop", active_model], check=False)
                    active_model = new_model
                    return f"[Switched to {new_model}]"
                return f"[Already using {new_model}]"
            return f"[Unknown model alias '{target}'. Known: {', '.join(MODEL_TRIGGERS.keys())}]"
        return "[Please provide a model alias]"

    if question == "/stop":
        if active_model:
            subprocess.run(["ollama", "stop", active_model], check=False)
            model_stopped = active_model
            active_model = None
            return f"[Stopped {model_stopped}]"
        return "[No active model to stop]"

    if question == "/context clear":
        clear_today()
        return "[Today's context cleared]"

    if question == "/projects":
        if projects:
            html_output = '<div class="projects-grid">'
            for kw, paths in projects.items():
                html_output += f'''
                <div class="project-card" onclick="sendCommand('/agent show me the root folder and files of {kw} as bullet points')">
                    <div class="project-header">
                        <span class="project-icon">📂</span>
                        <strong class="project-name">{kw.upper()}</strong>
                    </div>
                    <div class="project-paths">
                '''
                for label, path in paths.items():
                    html_output += f'<div class="path-item"><strong>path:</strong> {path}</div>'
                
                html_output += '</div></div>'
            html_output += '</div>'
            return html_output
        return "[No projects configured]"

    web_context = ""
    if question.startswith("/search "):
        query = question[8:].strip()
        if not query:
            return "[Please provide a search query]"
        web_context = search_web(query)
        question = query  

    if question.startswith("/agent "):
        agent_query = question[7:].strip()
        if not agent_query:
            return "[Please provide an agent instruction]"

        def agent_stream():
            agent_project = detect_project(agent_query, projects)
            project_info = ""
            if agent_project:
                dirs = list(projects[agent_project].values())
                project_info = f"\n            User referenced project '{agent_project}'.\n            Project Directories: {dirs}\n            Use these paths to locate files."
                yield f"[Agent context loaded for project: '{agent_project}']\n\n"

            agent_system = f"""You are an autonomous file-editing agent.
            Your Current Working Directory is: {Path.cwd()}{project_info}
            You have access to read_file, append_file, replace_in_file, and list_dir tools.
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
            last_call_signatures = []   
            
            while steps < MAX_STEPS:
                steps += 1
                try:
                    resp = ollama.chat(model=agent_model, messages=agent_messages, tools=[read_file, append_file, replace_in_file, list_dir], stream=False)
                except Exception as e:
                    yield f"\n[Agent died]\n"
                    break
                    
                msg = resp.get("message", {})
                agent_messages.append(msg)
                
                tool_calls = msg.get("tool_calls")
                
                # Your custom manual JSON parsing fallback logic
                if not tool_calls:
                    final_text = msg.get("content", "")
                    try:
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

                # If no tools were called, the agent is done talking to us
                if not tool_calls:
                    final_text = msg.get("content", "")
                    if final_text:
                        yield final_text
                    save_exchange(question, final_text)
                    break
                
                # Loop detection logic
                current_signatures = [
                    (tc["function"]["name"], json.dumps(tc["function"]["arguments"], sort_keys=True))
                    for tc in tool_calls
                ]
                if current_signatures == last_call_signatures:
                    break
                last_call_signatures = current_signatures

                # Execute Tools
                for tc in tool_calls:
                    fn_name = tc["function"]["name"]
                    args    = tc["function"]["arguments"]
                    
                    if fn_name == "read_file":
                        res_body = read_file(args.get("filepath", ""))
                    elif fn_name == "list_dir":
                        res_body = list_dir(args.get("folder_path", args.get("path", "")))
                    elif fn_name == "append_file":
                        res_body = append_file(args.get("filepath", ""), args.get("content", ""))
                    elif fn_name == "replace_in_file":  
                        res_body = replace_in_file(
                            filepath=args.get("filepath", ""),
                            start_line=int(args.get("start_line", 0)),
                            end_line=int(args.get("end_line", 0)),
                            new_code=args.get("new_code", "")
                        )                    
                    else:
                        res_body = "Error: Unknown tool."
                        
                    if res_body.startswith("Error:"):
                        print(f"<br><span style='color:#ff6b6b;'>_[**Tool error:** {res_body}]_</span><br>\n")
                        res_body += (
                            "\n\nRECOVERY HINT: Your last action failed. "
                            "Use read_file to re-read the current file contents first, "
                            "then try a DIFFERENT approach. Do NOT repeat the same failing action."
                        )
                        agent_messages.append({"role": "tool", "content": res_body, "name": fn_name})
                        break
                        
                    agent_messages.append({"role": "tool", "content": res_body, "name": fn_name})
            
                if steps >= MAX_STEPS:
                    yield f"\n_[Agent reached max steps ({MAX_STEPS}) and stopped.]_"

        return agent_stream()

    project_context = ""
    detected = detect_project(question, projects)
    if detected:
        folders = list(projects[detected].values())
        project_context = get_relevant_chunks(folders, question)

    past_context = get_relevant_past(question)

    history = load_today_history()
    
    stream_generator = chat_once(
        question=question, 
        active_model=active_model, 
        active_voice=active_voice, 
        history=history, 
        web_context=web_context, 
        project_context=project_context,
        past_context=past_context
    )
    
    return stream_generator