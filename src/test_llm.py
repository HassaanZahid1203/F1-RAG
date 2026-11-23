# Step 4: check the Groq API key works and list available chat models.
# Run: python src/test_llm.py
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

key = os.getenv("GROQ_API_KEY")
if not key or key.startswith("paste"):
    sys.exit("No key found. Create D:\\F1-RAG\\.env with a line: GROQ_API_KEY=your-key")
print(f"Key loaded (starts with {key[:4]}..., {len(key)} characters).")

client = Groq(api_key=key)

# Groq's model line-up changes over time, so list what is available right now.
models = sorted(m.id for m in client.models.list().data)
chat_models = [m for m in models if not any(x in m for x in ("whisper", "tts", "guard"))]
print("\nAvailable chat models:")
for m in chat_models:
    print("  ", m)

model = os.getenv("LLM_MODEL") or next((m for m in chat_models if "llama" in m and "70b" in m),
                                       chat_models[0])
print(f"\nTesting model: {model}")
reply = client.chat.completions.create(
    model=model,
    temperature=0,
    messages=[{"role": "user",
               "content": "In one sentence: what is parc fermé in Formula 1?"}],
)
print("Reply:", reply.choices[0].message.content)
print("\nStep 4 OK.")
