from ollama import generate

MODEL_NAME = "qwen2.5vl:3b"

def call_ai(prompt: str) -> str:
    response = generate(
        model=MODEL_NAME,
        prompt=prompt,
    )
    return response.response

def call_ai_with_image(prompt: str, image_path: str) -> str:
    response = generate(
        model=MODEL_NAME,
        prompt=prompt,
        image=image_path
    )
    return response.response