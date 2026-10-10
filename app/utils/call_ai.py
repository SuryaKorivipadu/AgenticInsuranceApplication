from ollama import generate

MODEL_NAME = "qwen2.5vl:3b"


def call_ai(prompt: str, output_format: str | None = None) -> str:
    options: dict[str, str] = {}
    if output_format is not None:
        options["format"] = output_format
    response = generate(model=MODEL_NAME, prompt=prompt, **options)
    return response.response


def call_ai_with_image(
    prompt: str,
    image_path: str,
    output_format: str | None = None,
) -> str:
    options: dict[str, str] = {}
    if output_format is not None:
        options["format"] = output_format
    response = generate(model=MODEL_NAME, prompt=prompt, images=[image_path], **options)
    return response.response