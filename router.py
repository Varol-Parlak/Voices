import ollama

DEFAULT_MODEL = "meta/llama-3.3-70b-instruct"

MODEL_TRIGGERS = {
    # Local models
    "qwen":          "qwen2.5-coder:7b",
    "deepseek":      "deepseek-r1:8b",
    "llama":         "llama3.1:8b",
    
    # OpenRouter Cloud models
    "gemma":         "google/gemma-4-26b-a4b:free",
    "nemo":          "nvidia/nemotron-3-super-120b-a12b:free",
    "owl":           "openrouter/owl-alpha",
    "qwen3":         "qwen/qwen3-next-80b-a3b-instruct:free",

    # NVIDIA NIM Cloud Models
    "llama3.3":      "meta/llama-3.3-70b-instruct",
    "nemotron":      "nvidia/llama-3.1-nemotron-70b-instruct",
    "llama3.1-405b": "meta/llama-3.1-405b-instruct",
    "deepseek-nim":  "deepseek-ai/deepseek-r1",
    "gemma2-27b":    "google/gemma-2-27b-it",
    "mistral-large": "mistralai/mistral-large-2-instruct",
}

def get_local_models() -> dict:
    try:
        model_list = ollama.list()
        local_models = {}
        
        models = getattr(model_list, "models", [])
        if not models and hasattr(model_list, "get"):
            models = model_list.get("models", [])
        if not models and isinstance(model_list, list):
            models = model_list
            
        reverse_triggers = {v: k for k, v in MODEL_TRIGGERS.items()}
        
        for m in models:
            name = getattr(m, "model", None)
            if not name and isinstance(m, dict):
                name = m.get("model")
            if not name:
                continue
                
            # Exclude embedding and vision models
            if "embed" in name.lower() or "minicpm" in name.lower():
                continue
                
            if name in reverse_triggers:
                alias = reverse_triggers[name]
            else:
                alias = name.split(":")[0] if ":" in name else name
                
            local_models[alias] = name
        return local_models
    except Exception as e:
        print(f"Error fetching local models: {e}")
        return {}

def route(prompt: str, current_model: str = None) -> str:
    prompt_lower = prompt.lower()
    # Check static triggers first
    for trigger, model in MODEL_TRIGGERS.items():
        if trigger in prompt_lower:
            return model
            
    # Check dynamic local models
    local_models = get_local_models()
    for alias, fullname in local_models.items():
        if alias.lower() in prompt_lower:
            return fullname
            
    return current_model or DEFAULT_MODEL

