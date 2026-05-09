import json
import asyncio
import ollama
import threading
from pathlib import Path
from context import load_projects, detect_project, get_relevant_chunks
from memory import get_relevant_past
from mcp_client import MCPConnection

PROFILES_DIR = Path(__file__).parent / "profiles"
projects = load_projects()

# 1. Initialize MCP Client (Make sure this points to your combined mcp_analyst.py file)
mcp_script = str(Path(__file__).parent / "mcp_analyst.py")
mcp = MCPConnection(mcp_script)
_mcp_loop = asyncio.new_event_loop()

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

# Start the loop in a background thread that stays alive forever
threading.Thread(target=start_background_loop, args=(_mcp_loop,), daemon=True).start()

def run_mcp(coro):
    """Safely runs async MCP commands on the background thread."""
    future = asyncio.run_coroutine_threadsafe(coro, _mcp_loop)
    return future.result()
def chat_once(question, active_model, active_voice, history, web_context="", project_context="", past_context=""):
    system_parts = [
        "You are a helpful personal AI assistant.",
        "CRITICAL INSTRUCTIONS:",
        "1. Keep your responses clear.",
        "2. If web search doesn't contain the specific data requested, admit you don't know it.",
        "3. User Information and Contexts are background only. Don't mention them unless relevant.",
        "4. You have access to tools via MCP. Use them autonomously to explore code, read files, edit code, or search the web when necessary."
        "5. NEVER output tool JSON in your conversational text. You MUST use the native API tool execution. Do not announce that you are using a tool, just do it."
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

    # 2. Fetch available tools dynamically from your MCP server
    tools = run_mcp(mcp.get_tools())

    # 3. First pass: Ask Ollama if it wants to use tools (no streaming yet so it can output complete tool calls)
    response = ollama.chat(
        model=active_model,
        messages=messages,
        tools=tools,
        options={"num_ctx": 8192}
    )

    # 4. Tool Execution Logic
    if response.get("message", {}).get("tool_calls"):
        messages.append(response["message"]) # Save AI's tool intent
        
        for tool_call in response["message"]["tool_calls"]:
            t_name = tool_call["function"]["name"]
            t_args = tool_call["function"]["arguments"]
            
            print(f"\n[AI is using tool: {t_name}]", flush=True)
            
            # Execute tool via MCP
            t_result = run_mcp(mcp.call_tool(t_name, t_args))
            
            messages.append({
                "role": "tool",
                "content": str(t_result),
                "name": t_name
            })
        
        # Second pass: Stream the final response based on the new tool output
        stream = ollama.chat(
            model=active_model, 
            messages=messages, 
            stream=True,
            options={"num_ctx": 8192}
        )

        # Handle the true stream chunks
        thinking_open = False
        for chunk in stream:
            thinking = chunk["message"].get("thinking", "")
            content  = chunk["message"].get("content", "")

            if thinking:
                if not thinking_open:
                    yield "<think>\n"
                    thinking_open = True
                yield thinking

            if content:
                if thinking_open:
                    yield "\n</think>\n"
                    thinking_open = False
                yield content

        if thinking_open:
            yield "\n</think>\n"

    else:
        # 5. If no tools were used, avoid a second call to Ollama.
        # We already have the full text, so we artificially stream it to satisfy your Flask generator.
        content = response["message"].get("content", "")
        thinking = response["message"].get("thinking", "")
        
        if thinking:
            yield "<think>\n" + thinking + "\n</think>\n"
        
        chunk_size = 15
        for i in range(0, len(content), chunk_size):
            yield content[i:i+chunk_size]
        return