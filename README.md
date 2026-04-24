# Voices 🎙️

**Voices** is a powerful, flexible local AI assistant running entirely on your machine via Ollama. It features a web interface and offers dynamic personas, autonomous file-editing agents, vision capabilities, web searching, and context-aware responses based on your local project directories.

## ✨ Features

- **100% Local AI:** Powered by Ollama, ensuring your data and code never leave your machine.
- **Autonomous Agent Mode (`/agent`):** Give the AI a task, and it will autonomously read, write, and edit files in your project directories using native tool calling.
- **Dynamic Personas (`/voice`):** Switch between different AI personalities and system prompts on the fly.
- **Vision Integration:** Upload images to the chat and use multimodal models (like `minicpm-v`) to analyze and describe them.
- **Web Search (`/search`):** Uses a browser-automation agent (`browser-use`) to autonomously search the web and return up-to-date answers.
- **Project Context Awareness:** Link your local development folders so the AI can automatically read relevant files to answer your questions.
- **Persistent Memory:** Remembers conversations and context across sessions.
- **Instant Model Switching:** Seamlessly switch between local models like Llama 3.1, Qwen, or DeepSeek.

## 🚀 Prerequisites

Before you start, ensure you have the following installed:
1. **Python 3.x**
2. **[Ollama](https://ollama.com/)** installed and running on your system.
3. Download the necessary Ollama models. By default, the app uses `llama3.1:8b` as the main model and expects `minicpm-v` for vision tasks.
   ```bash
   ollama pull llama3.1:8b
   ollama pull minicpm-v
   ```

## 🛠️ Installation

1. Clone this repository:
   ```bash
   git clone <your-repo-url>
   cd voices
   ```

2. Install the required Python dependencies:
   ```bash
   pip install flask flask-cors ollama langchain-ollama browser-use
   ```

3. Start the application server:
   ```bash
   python server.py
   ```

4. Open your web browser and navigate to:
   ```
   http://localhost:5500
   ```

## 💬 Usage & Commands

The chat interface supports standard conversation, as well as several powerful slash (`/`) commands:

- `/agent [instruction]`: Triggers the autonomous coding agent. It will read files, append code, and replace lines in your configured project folders to accomplish the task.
- `/search [query]`: Deploys a browser agent to search the web for your query and summarize the results.
- `/voice [name]`: Switch the AI's persona (e.g., `/voice friend`). Type `/voice` alone to see all available personas.
- `/model [alias]`: Switch the active Ollama model (e.g., `/model qwen`, `/model deepseek`, `/model llama`).
- `/projects`: Lists all configured project directories that the AI currently has access to.
- `/context clear`: Clears the conversation memory context for the current day.
- `/stop`: Unloads the currently active model from your GPU/RAM.

## ⚙️ Customization

### Adding Projects
To let the AI access and edit your local codebases, add your project folders to `projects.json`. 
Format:
```json
{
  "my_project": {
    "pc": "C:/Path/To/Your/Project"
  }
}
```
Once added, simply mention the project name in your prompt or use the `/agent` command, and the AI will know where to look.

### Adding Voices (Personas)
You can create custom AI personas by adding Markdown files to the `profiles/` directory.
1. Name the file starting with `p_`, for example: `p_developer.md`.
2. Write the system prompt/instructions inside the Markdown file.
3. Switch to it in chat using `/voice developer`.
