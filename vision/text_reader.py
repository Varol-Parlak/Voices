import ollama
import base64

def read_text(image):
    with open(image, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    response = ollama.chat(
        model='minicpm-v',
        messages=[{
            'role': 'user',
            'content': 'Transcribe all the handwritten text in this image exactly as written.',
            'images': [img_b64]
        }]
    )

    return response['message']['content']