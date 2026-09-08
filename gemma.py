import torch
from transformers import AutoProcessor, AutoModelForMultimodalLM

# MODEL_ID = "google/gemma-4-E2B-it-qat-mobile-transformers"
MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"

print("Loading processor...")
processor = AutoProcessor.from_pretrained(MODEL_ID)

print("Downloading/loading model...")
model = AutoModelForMultimodalLM.from_pretrained(
    MODEL_ID,
    torch_dtype="auto",
    device_map="auto",  
)

messages = [
    {
        "role": "system",
        "content": [{"type": "text", "text": "You are a helpful assistant."}],
    },
    {
        "role": "user",
        "content": [{"type": "text", "text": "Explain quantum computing in one paragraph."}],
    },
]

inputs = processor.apply_chat_template(
    messages,
    tokenize=True,
    add_generation_prompt=True,
    return_tensors="pt",
    return_dict=True,
).to(model.device)

input_len = inputs["input_ids"].shape[-1]

print("Generating...")

with torch.inference_mode():
    outputs = model.generate(
        **inputs,
        max_new_tokens=256,
        temperature=0.7,
        do_sample=True,
    )

response = processor.decode(
    outputs[0][input_len:],
    skip_special_tokens=False,
)

try:
    parsed = processor.parse_response(response)
    print(parsed)
except Exception:
    print(response)