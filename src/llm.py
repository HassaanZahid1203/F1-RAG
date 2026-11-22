"""
Small wrapper so the rest of the project can call an LLM without caring
which provider is behind it. Settings come from the .env file:

    LLM_PROVIDER=gemini            # main model that answers questions
    LLM_MODEL=gemini-3.5-flash
    FALLBACK_PROVIDER=groq         # optional: used if the main model stays unavailable
    FALLBACK_MODEL=openai/gpt-oss-120b
    GEMINI_API_KEY=...
    GROQ_API_KEY=...

Temperature is 0 by default so answers are as repeatable as possible.
Rate limits (429) and temporary server errors (5xx) are retried with a
growing wait. If the main model is still unavailable after `attempts` tries,
the fallback model answers instead, and `last_model` records which one did.
For evaluation runs, create LLM(fallback=False) so every answer comes from
the same model.
"""
import os
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

TRANSIENT = ("429", "rate", "quota", "resource_exhausted",
             "500", "502", "503", "504", "unavailable", "overloaded", "high demand")


DAILY_QUOTA = ("per day", "perday", "requests per day", "tokens per day")


def is_daily_quota(error):
    """A DAILY quota error will not clear by waiting a few seconds, so never retry it."""
    msg = str(error).lower()
    return any(t in msg for t in DAILY_QUOTA)


def is_transient(error):
    msg = str(error).lower()
    return any(t in msg for t in TRANSIENT)


def _strip_reasoning(text):
    """Some reasoning models return their thinking inside <think>...</think>; drop it."""
    import re
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()


MAX_QUOTA_WAIT = 20 * 60   # seconds; wait automatically if the quota frees up within this time


def _quota_wait_seconds(error):
    """Groq's daily limit is a rolling window and the error says when to retry,
    e.g. 'Please try again in 3m24.3s'. Return that wait in seconds, or None."""
    import re
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", str(error))
    if not m:
        return None
    h, mins, secs = m.groups()
    return int(h or 0) * 3600 + int(mins or 0) * 60 + float(secs)


def _retry(fn, attempts):
    wait = 5
    quota_waits = 0
    i = 0
    while i < attempts:
        try:
            return fn()
        except Exception as e:
            if is_daily_quota(e):
                secs = _quota_wait_seconds(e)
                if secs is not None and secs <= MAX_QUOTA_WAIT and quota_waits < 6:
                    quota_waits += 1
                    print(f"   daily token window frees up in {secs/60:.1f} min, waiting ...", flush=True)
                    time.sleep(secs + 5)
                    continue
                raise RuntimeError(
                    "DAILY QUOTA REACHED for this model on the free tier. Finished work is saved: "
                    "re-run the same command later (Groq frees tokens on a rolling 24-hour window).\n"
                    "Original error: " + str(e)[:300]) from e
            if is_transient(e) and i < attempts - 1:
                print(f"   temporary error ({str(e)[:60]}...), waiting {wait}s ...", flush=True)
                time.sleep(wait)
                wait = min(wait * 2, 60)
                i += 1
                continue
            raise


class LLM:
    def __init__(self, provider=None, model=None, temperature=0.0, fallback=True, attempts=None):
        self.provider = (provider or os.getenv("LLM_PROVIDER", "gemini")).lower()
        self.model = model or os.getenv("LLM_MODEL")
        self.temperature = temperature
        if not self.model:
            raise ValueError("LLM_MODEL is not set in .env. Run: python src/check_llm.py")
        # With a fallback available, give up on the main model sooner.
        fb = (os.getenv("FALLBACK_PROVIDER"), os.getenv("FALLBACK_MODEL"))
        self._fallback_args = fb if (fallback and all(fb) and fb != (self.provider, self.model)) else None
        self.attempts = attempts or (3 if self._fallback_args else 6)
        self._fallback = None
        self.last_model = None
        self.last_tokens = None       # total tokens of the last call (if the provider reports it)
        # Hidden "reasoning" tokens count against free-tier token limits, so keep them low.
        # gpt-oss: low/medium/high.  qwen3: none/default.  Override in .env if needed.
        self._extra = {}
        if self.provider == "groq":
            if "gpt-oss" in self.model:
                self._extra = {"reasoning_effort": os.getenv("GPT_OSS_REASONING", "low")}
            elif "qwen" in self.model:
                self._extra = {"reasoning_effort": os.getenv("QWEN_REASONING", "none")}

        if self.provider == "gemini":
            from google import genai
            self.client = genai.Client(api_key=_key("GEMINI_API_KEY"))
        elif self.provider == "groq":
            from groq import Groq
            self.client = Groq(api_key=_key("GROQ_API_KEY"))
        else:
            raise ValueError(f"Unknown provider: {self.provider}")

    @property
    def name(self):
        return f"{self.provider}/{self.model}"

    def generate(self, prompt: str, system: str = "") -> str:
        try:
            out = self._generate(prompt, system)
            self.last_model = self.name
            return out
        except Exception as e:
            if not (self._fallback_args and (is_transient(e) or is_daily_quota(e)
                                             or "daily quota" in str(e).lower())):
                raise
            if self._fallback is None:
                self._fallback = LLM(*self._fallback_args, temperature=self.temperature, fallback=False)
            print(f"   {self.model} unavailable -> using fallback {self._fallback.model}", flush=True)
            out = self._fallback.generate(prompt, system)
            self.last_model = self._fallback.name
            return out

    def _generate(self, prompt, system):
        if self.provider == "gemini":
            from google.genai import types
            cfg = types.GenerateContentConfig(temperature=self.temperature,
                                              system_instruction=system or None)
            resp = _retry(lambda: self.client.models.generate_content(
                model=self.model, contents=prompt, config=cfg), self.attempts)
            um = getattr(resp, "usage_metadata", None)
            self.last_tokens = getattr(um, "total_token_count", None) if um else None
            return _strip_reasoning(resp.text or "")

        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]

        def call():
            return self.client.chat.completions.create(
                model=self.model, messages=messages, temperature=self.temperature, **self._extra)
        try:
            resp = _retry(call, self.attempts)
        except Exception as e:
            # If the model rejects the reasoning setting, drop it and try again once.
            if self._extra and "reasoning" in str(e).lower() and "quota" not in str(e).lower():
                print(f"   ({self.model} does not accept {self._extra}; retrying without it)", flush=True)
                self._extra = {}
                resp = _retry(call, self.attempts)
            else:
                raise
        usage = getattr(resp, "usage", None)
        self.last_tokens = getattr(usage, "total_tokens", None) if usage else None
        return _strip_reasoning(resp.choices[0].message.content or "")


def _key(name):
    k = os.getenv(name)
    if not k or k.startswith("paste-"):
        raise ValueError(f"{name} is missing from .env")
    return k
