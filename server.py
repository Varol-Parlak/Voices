from flask import Flask, request, Response, jsonify
from flask_cors import CORS
from control import process_message, get_active_model, get_model_info, change_model
from memory import save_exchange
import re
import os
import subprocess
import threading
import ollama
from vision.text_reader import read_text
from context import start_background_watcher

app = Flask(__name__, static_folder='templates', static_url_path='')
CORS(app)

@app.route('/')
def home():
    return app.send_static_file('index.html')

@app.route('/stream', methods=['POST'])
def stream_chat():
    data = request.json
    question = data.get('prompt', '')

    result = process_message(question)

    if isinstance(result, str):
        return Response(result, mimetype='text/plain')
    
    def generate():
        full_text = ""
        for chunk in result:
            full_text += chunk
            yield chunk
        
        clean_text = re.sub(r'^_\[.*?\]_\s*\n*', '', full_text, flags=re.DOTALL)
        save_exchange(question, clean_text.strip()) 

    return Response(generate(), mimetype='text/plain')

def preload_model(model_name):
    try:
        ollama.chat(
            model=model_name,
            messages=[{"role": "user", "content": "hello"}],
            options={"num_predict": 1},
            keep_alive="5m"
        )
    except Exception:
        pass

@app.route('/warmup_vision', methods=['POST'])
def warmup_vision():
    current_model = get_active_model()
    if current_model:
        subprocess.run(["ollama", "stop", current_model], check=False)
    threading.Thread(target=preload_model, args=('minicpm-v',), daemon=True).start()
    return jsonify({"status": "warming up minicpm-v"})

@app.route('/upload_image', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
        
    prompt = request.form.get('prompt', 'Describe this image.')
    
    if file:
        current_model = get_active_model()
        if current_model:
            subprocess.run(["ollama", "stop", current_model], check=False)

        os.makedirs('temp', exist_ok=True)
        filepath = os.path.join('temp', file.filename)
        file.save(filepath)
        
        try:
            def generate():
                full_text = ""
                try:
                    for chunk in read_text(filepath, prompt):
                        full_text += chunk
                        yield chunk
                    save_exchange(f"[Image: {file.filename}] {prompt}", full_text.strip())
                    if current_model:
                        threading.Thread(target=preload_model, args=(current_model,), daemon=True).start()
                except Exception as e:
                    yield f"Error: {str(e)}"
            return Response(generate(), mimetype='text/plain')
        except Exception as e:
            return jsonify({"error": str(e)}), 500

@app.route('/api/models', methods=['GET'])
def api_get_models():
    return jsonify(get_model_info())

@app.route('/api/model', methods=['POST'])
def api_set_model():
    data = request.json or {}
    model_alias = data.get('model')
    if not model_alias:
        return jsonify({"error": "Model alias is required"}), 400
    res = change_model(model_alias)
    if res.get("status") == "error":
        return jsonify(res), 400
    return jsonify(res)

if __name__ == '__main__':
    start_background_watcher()
    app.run(port=5500, debug=True, use_reloader=False)