from flask import Flask, request, Response
from control import process_message
from memory import save_exchange

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
        save_exchange(question, full_text) 

    return Response(generate(), mimetype='text/plain')