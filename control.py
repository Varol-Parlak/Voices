import subprocess
from pathlib import Path
from router import MODEL_TRIGGERS, DEFAULT_MODEL, get_local_models
from context import load_goals, detect_goals, get_relevant_chunks, get_goal_profile, get_goal_folders, load_projects
from memory import load_today_history, save_exchange, get_relevant_past, clear_today
from chat_core import chat_once

PROFILES_DIR = Path(__file__).parent / "profiles"

goals        = load_goals()
projects     = load_projects()      # Legacy compat for /projects command
active_model = DEFAULT_MODEL
active_voice = "user_info"  
last_active_goals = []

def get_active_model():
    global active_model
    return active_model or DEFAULT_MODEL

def get_model_info():
    global active_model
    merged_models = {}
    
    # 1. Add cloud models from MODEL_TRIGGERS
    for alias, fullname in MODEL_TRIGGERS.items():
        if "/" in fullname:
            merged_models[alias] = fullname
            
    # 2. Add local models dynamically
    local_models = get_local_models()
    for alias, fullname in local_models.items():
        merged_models[alias] = fullname
        
    return {
        "active_model": active_model or DEFAULT_MODEL,
        "models": merged_models
    }

def change_model(target: str):
    global active_model
    target = target.lower()
    
    # Check if target is a key/alias or fullname in combined models
    model_info = get_model_info()
    models_dict = model_info["models"]
    
    if target in models_dict:
        new_model = models_dict[target]
    elif target in models_dict.values():
        new_model = target
    else:
        return {"status": "error", "message": f"Unknown model alias '{target}'"}
        
    if new_model != active_model:
        if active_model is not None and "/" not in active_model:
            print(f"Freeing VRAM: Stopping local model {active_model}...")
            subprocess.run(["ollama", "stop", active_model], check=False)
        active_model = new_model
        return {"status": "success", "model": active_model}
    return {"status": "already_active", "model": active_model}

def process_message(question):
    """
    Takes the user question from the UI, routes it to the right command,
    and returns either a string (for fast commands) or a generator (for streams).
    """
    global active_model, active_voice

    if active_model is None:
        active_model = DEFAULT_MODEL

    # ==========================================
    # SYSTEM COMMANDS
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



    if question == "/stop":
        if active_model:
            if "/" not in active_model:
                subprocess.run(["ollama", "stop", active_model], check=False)
                model_stopped = active_model
                active_model = None
                return f"[Stopped local model and cleared VRAM: {model_stopped}]"
            else:
                cloud_model = active_model
                active_model = None
                return f"[Disconnected from cloud model: {cloud_model}]"
        return "[No active model to stop]"

    if question == "/context clear":
        clear_today()
        global last_active_goals
        last_active_goals = []
        return "[Today's context and active goal lock cleared]"

    if question == "/goals":
        if goals:
            html_output = '<div class="projects-grid">'
            for goal_id, goal_data in goals.items():
                keywords = ", ".join(goal_data.get("keywords", []))
                folders = goal_data.get("folders", [])
                display_name = goal_id.replace("_", " ").upper()
                first_keyword = goal_data.get("keywords", [goal_id])[0]
                
                html_output += f'''
                <div class="project-card" onclick="sendCommand('/agent show me the root folder and files of {first_keyword} as bullet points')">
                    <div class="project-header">
                        <span class="project-icon">🎯</span>
                        <strong class="project-name">{display_name}</strong>
                    </div>
                    <div class="project-paths">
                '''
                for folder in folders:
                    html_output += f'<div class="path-item"><strong>path:</strong> {folder}</div>'
                html_output += f'<div class="path-item"><strong>keywords:</strong> {keywords}</div>'
                
                html_output += '</div></div>'
            html_output += '</div>'
            return html_output
        return "[No goals configured]"

    # Keep /projects as an alias for /goals
    if question == "/projects":
        return process_message("/goals")

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
        global last_active_goals
        
        # Detect which goals are mentioned in the prompt
        detected = detect_goals(question, goals)
                
        if detected:
            last_active_goals = detected
            
        current_goals = last_active_goals
        
        # Build project context and goal profile from active goals
        project_context = ""
        goal_profile = ""
        
        if current_goals:
            context_parts = []
            profile_parts = []
            
            for goal_id in current_goals:
                folders = get_goal_folders(goal_id, goals)
                if folders:
                    chunks = get_relevant_chunks(folders, question, goal_id=goal_id)
                    if chunks:
                        context_parts.append(
                            f"CRITICAL: The user is asking about or working within the goal '{goal_id}'. "
                            f"The absolute directory paths for this goal are: {folders}. "
                            f"Use these exact paths when calling your file exploration and reading tools.\n\n"
                            f"File Context from '{goal_id}':\n{chunks}"
                        )
                
                profile = get_goal_profile(goal_id, goals)
                if profile:
                    profile_parts.append(profile)
            
            if context_parts:
                project_context = "\n\n---\n\n".join(context_parts)
            if profile_parts:
                goal_profile = "\n\n".join(profile_parts)

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
            past_context=past_context,
            goal_profile=goal_profile
        )
        
        for chunk in stream_generator:
            yield chunk

    return final_stream()