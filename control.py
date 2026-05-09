import subprocess
from pathlib import Path

from router import MODEL_TRIGGERS, DEFAULT_MODEL
from context import load_projects, detect_project, get_relevant_chunks
from memory import load_today_history, save_exchange, get_relevant_past, clear_today
from chat_core import chat_once

PROFILES_DIR = Path(__file__).parent / "profiles"

projects     = load_projects()
active_model = DEFAULT_MODEL
active_voice = "user_info"  

def get_active_model():
    global active_model
    return active_model or DEFAULT_MODEL

def process_message(question):
    """
    Takes the user question from the UI, routes it to the right command,
    and returns either a string (for fast commands) or a generator (for streams).
    """
    global active_model, active_voice

    if active_model is None:
        active_model = DEFAULT_MODEL

    # ==========================================
    # SYSTEM COMMANDS (Unchanged)
    # ==========================================
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
        model_list = "\n".join(f"- {model}" for alias, model in MODEL_TRIGGERS.items())
        return f"Active model:\n{active_model}\nAvailable Models:\n{model_list}"

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

    # ==========================================
    # INTENT RE-ROUTING
    # Let MCP handle searches and agent tasks automatically
    # ==========================================
    if question.startswith("/search "):
        query = question[8:].strip()
        if not query:
            return "[Please provide a search query]"
        question = f"Please search the web for: {query}"

    if question.startswith("/agent "):
        agent_query = question[7:].strip()
        if not agent_query:
            return "[Please provide an agent instruction]"
        question = f"Use your MCP tools to autonomously complete this task: {agent_query}"


    # ==========================================
    # MAIN PIPELINE
    # ==========================================
    def final_stream():
        project_context = ""
        detected = detect_project(question, projects)
        if detected:
            folders = list(projects[detected].values())
            project_context = get_relevant_chunks(folders, question)

        past_context = get_relevant_past(question)
        history = load_today_history()
        
        # Web context is now handled via MCP, so we pass an empty string
        stream_generator = chat_once(
            question=question, 
            active_model=active_model, 
            active_voice=active_voice, 
            history=history, 
            web_context="", 
            project_context=project_context,
            past_context=past_context
        )
        
        for chunk in stream_generator:
            yield chunk

    return final_stream()