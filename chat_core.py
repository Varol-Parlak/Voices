import json
import asyncio
import threading
import re
from pathlib import Path
from openai import OpenAI 

from context import load_projects, detect_project, get_relevant_chunks
from memory import get_relevant_past
from mcp_client import MCPConnection
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("API_KEY")

# ==========================================
local_client = OpenAI(
    base_url="http://localhost:11434/v1",
    api_key="ollama", 
)

cloud_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=api_key , 
)

def get_active_client(model_name):
    if "/" in model_name:
        return cloud_client
    return local_client

# ==========================================

PROFILES_DIR = Path(__file__).parent / "profiles"
projects = load_projects()

mcp_script = str(Path(__file__).parent / "mcp_analyst.py")
mcp = MCPConnection(mcp_script)

_mcp_loop = asyncio.new_event_loop()

def start_background_loop(loop):
    asyncio.set_event_loop(loop)
    loop.run_forever()

threading.Thread(target=start_background_loop, args=(_mcp_loop,), daemon=True).start()

def run_mcp(coro):
    future = asyncio.run_coroutine_threadsafe(coro, _mcp_loop)
    return future.result()

def chat_once(question, active_model, active_voice, history, web_context="", project_context="", past_context=""):
    is_deepseek = "deepseek" in active_model.lower()

    system_parts = [
        "You are a helpful personal AI assistant.",
        "CRITICAL INSTRUCTIONS:",
        "1. Keep your responses clear.",
        "2. If web search doesn't contain the specific data requested, admit you don't know it.",
        "3. User Information and Contexts are background only. Don't mention them unless relevant."
    ]

    if not is_deepseek:
        system_parts.extend([
            "4. You have access to tools via MCP. Use them autonomously to explore code, read files, edit code, or search the web when necessary.",
            "5. NEVER output tool JSON in your conversational text. You MUST use the native API tool execution. Do not announce that you are using a tool, just do it.",
            f"6. SYSTEM MAP: Here are the absolute paths to the user's local projects: {json.dumps(projects)}. Use these exact absolute paths when using file tools."
        ])

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

    tools = run_mcp(mcp.get_tools())
    
    # Pick the right connection based on the model name
    ai_client = get_active_client(active_model)

    MAX_STEPS = 6
    steps = 0

    active_tools = tools if (tools and not is_deepseek) else None

    while steps < MAX_STEPS:
        api_kwargs = {
            "model": active_model,
            "messages": messages,
            "stream": True
        }
        if active_tools:
            api_kwargs["tools"] = active_tools
        if ai_client == cloud_client:
            api_kwargs["extra_body"] = {
                "reasoning": {
                    "exclude": False
                }
            }

        attempts = 0
        max_attempts = 2
        
        while attempts < max_attempts:
            try:
                response = ai_client.chat.completions.create(**api_kwargs)

                content = ""
                tool_calls = []
                is_thinking = False
                # Parse the stream as it arrives token-by-token
                for chunk in response:
                    if not chunk.choices:
                        continue
                        
                    delta = chunk.choices[0].delta

                    reasoning = getattr(delta, "reasoning", None) or getattr(delta, "reasoning_content", None)
                    if reasoning:
                        if not is_thinking:
                            yield "<think>\n"  # Open the tag for the UI
                            is_thinking = True
                        yield reasoning

                    # 1. Stream normal conversational text instantly to the UI
                    if delta.content:
                        if is_thinking:
                            yield "\n</think>\n" # Close the tag before normal text starts
                            is_thinking = False
                        content += delta.content
                        yield delta.content 

                    # 2. Quietly stitch together tool calls in the background
                    if delta.tool_calls:
                        for tc_chunk in delta.tool_calls:
                            idx = tc_chunk.index
                            
                            # Make sure our list is long enough to hold this tool call
                            while len(tool_calls) <= idx:
                                tool_calls.append({
                                    "id": "", 
                                    "type": "function", 
                                    "function": {"name": "", "arguments": ""}
                                })
                            
                            if tc_chunk.id:
                                tool_calls[idx]["id"] += tc_chunk.id
                                
                            # FIX: We MUST check if 'function' exists before reading its properties!
                            if tc_chunk.function:
                                if tc_chunk.function.name:
                                    tool_calls[idx]["function"]["name"] += tc_chunk.function.name
                                if tc_chunk.function.arguments:
                                    tool_calls[idx]["function"]["arguments"] += tc_chunk.function.arguments

                if is_thinking:
                    yield "\n</think>\n"
                    is_thinking = False
                
                # If we got here, the stream finished successfully!
                break
                
            except Exception as e:
                attempts += 1
                fallback_model = "nvidia/nemotron-3-super-120b-a12b:free"
                
                if ai_client == cloud_client and api_kwargs["model"] != fallback_model and attempts < max_attempts:
                    print(f"Cloud model {api_kwargs['model']} failed: {e}. Falling back to stable Nemotron...", flush=True)
                    yield f"\n_[Cloud model failed: {e}. Falling back to Nemotron...]_\n"
                    
                    # Update parameters for the fallback model
                    api_kwargs["model"] = fallback_model
                    is_deepseek = False
                    active_tools = tools
                    if active_tools:
                        api_kwargs["tools"] = active_tools
                    else:
                        api_kwargs.pop("tools", None)
                else:
                    # If we exhausted attempts or it's a local model, propagate the error
                    raise e
        # ==========================================
        # SAFETY NET: Catch Leaked JSON
        # ==========================================
        if not is_deepseek and not tool_calls and "{" in content and '"name"' in content:
            match = re.search(r'(\{[\s\S]*?"name"\s*:\s*"[^"]+"[\s\S]*?\})', content)
            if match:
                try:
                    parsed = json.loads(match.group(1))
                    if "name" in parsed:
                        tool_calls = [{
                            "id": "call_safetynet_123",
                            "type": "function",
                            "function": {
                                "name": parsed["name"],
                                "arguments": json.dumps(parsed.get("arguments", parsed.get("parameters", {})))
                            }
                        }]
                        content = content.replace(match.group(1), "").strip()
                except Exception:
                    pass

        # Save the AI's final intent to the chat history
        msg_dict = {"role": "assistant", "content": content}
        if tool_calls:
            msg_dict["tool_calls"] = tool_calls
        messages.append(msg_dict)

        # Execute any tools it requested, then loop back so it can read the results!
        if tool_calls:
            for tc in tool_calls:
                t_name = tc["function"]["name"]
                t_args_str = tc["function"]["arguments"]
                
                try:
                    t_args = json.loads(t_args_str)
                except Exception:
                    t_args = {}
                
                print(f"\n[{'Cloud' if '/' in active_model else 'Local'} AI is using tool: {t_name}]", flush=True)
                t_result = run_mcp(mcp.call_tool(t_name, t_args))
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": t_name,
                    "content": str(t_result)
                })
            
            steps += 1
            continue 
            
        else:
            # If no tools were called, the stream is finished and the user already saw it!
            return

    yield "\n_[Agent reached maximum steps and stopped.]_"