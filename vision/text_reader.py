import ollama
import base64

def read_text(image, prompt):
    with open(image, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode()

    stream = ollama.chat(
        model='minicpm-v',
        messages=[{
            'role': 'user',
            'content':prompt,
            'images': [img_b64]
        }],
        keep_alive=0,
        options={
            'num_ctx': 4096,
            'num_predict': 1024
        },
        stream=True
    )

    for chunk in stream:
        content = chunk['message'].get('content', '')
        if content:
            yield content