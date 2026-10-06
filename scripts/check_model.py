"""Check that the API key loads and list the GPT-6 model IDs it can use (never prints the key)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from openai import OpenAI

from backbone.config import load_api_key

key = load_api_key()
print("key loaded:", bool(key))
ids = sorted(m.id for m in OpenAI(api_key=key).models.list())
print([i for i in ids if "gpt-6" in i or "luna" in i])
