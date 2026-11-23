# Step 4 check: list text models available to your API keys, then send one
# test question to the model set in .env. Run: python src/check_llm.py
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from llm import LLM, load_dotenv  # noqa: F401  (load_dotenv already ran on import)

SKIP = ("image", "tts", "audio", "live", "embedding", "embed", "veo", "imagen",
        "whisper", "guard", "aqa", "banana", "music", "native", "computer",
        "omni", "video", "lyria", "robotics")


def list_gemini():
    from google import genai
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        name = m.name.replace("models/", "")
        if "generateContent" in actions and not any(s in name.lower() for s in SKIP):
            names.append(name)
    return sorted(names)


def list_groq():
    from groq import Groq
    client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return sorted(m.id for m in client.models.list().data
                  if not any(s in m.id.lower() for s in SKIP))


def has_key(name):
    k = os.getenv(name)
    return bool(k) and not k.startswith("paste-")


if __name__ == "__main__":
    for provider, keyname, lister in [("gemini", "GEMINI_API_KEY", list_gemini),
                                      ("groq", "GROQ_API_KEY", list_groq)]:
        print(f"\n=== {provider} ===")
        if not has_key(keyname):
            print(f"   no {keyname} in .env (skipped)")
            continue
        try:
            models = lister()
            print(f"   key works. {len(models)} text models available:")
            for m in models:
                print("    ", m)
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n=== test call ===")
    provider, model = os.getenv("LLM_PROVIDER"), os.getenv("LLM_MODEL")
    if not model:
        print("   Set LLM_PROVIDER and LLM_MODEL in .env (choose a model from the lists above), then run again.")
        sys.exit(0)
    print(f"   provider={provider}  model={model}")
    llm = LLM()
    answer = llm.generate("In one sentence: what is parc fermé in Formula 1?",
                          system="You are a concise assistant.")
    print("   answer:", answer)
