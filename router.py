DEFAULT_MODEL = "llama3.1:8b"

MODEL_TRIGGERS = {
    "qwen":     "qwen2.5-coder:7b",
    "deepseek": "deepseek-r1:8b",
    "llama":    "llama3.1:8b",
    "gemma": "google/gemma-4-31b-it:free",
    "nemo": "nvidia/nemotron-3-super-120b-a12b:free",
    "owl": "openrouter/owl-alpha",
    "qwen3": "qwen/qwen3-next-80b-a3b-instruct:free",
}

def route(prompt: str, current_model: str = None) -> str:
    prompt_lower = prompt.lower()
    for trigger, model in MODEL_TRIGGERS.items():
        if trigger in prompt_lower:
            return model
    return current_model or DEFAULT_MODEL

