from flask import Flask, request, Response
from flask_cors import CORS
from control import process_message
from memory import save_exchange
import re

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

if __name__ == '__main__':
    app.run(port=5500, debug=True)