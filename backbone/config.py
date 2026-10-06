"""Paths, backend choice, model settings and API-key loading.

BACKBONE_BACKEND picks the model backend:
  openai  (default) closed model through the OpenAI API, results in outputs/closed/
  ollama            local open model through Ollama, results in outputs/open/

The key is never stored in this repo. It is read from OPENAI_API_KEY, or from a file named by
OPENAI_KEY_FILE (either a bare key or KEY=VALUE lines). The ollama backend needs no key.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Optional .env in the project root (KEY=VALUE lines); real environment variables take precedence.
if (ROOT / ".env").exists():
    for _line in (ROOT / ".env").read_text(encoding="utf-8-sig").splitlines():
        if "=" in _line and not _line.lstrip().startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

BACKEND = os.environ.get("BACKBONE_BACKEND", "openai").strip().lower()
if BACKEND not in ("openai", "ollama"):
    raise RuntimeError(f"BACKBONE_BACKEND must be 'openai' or 'ollama', not {BACKEND!r}")
VARIANT = "closed" if BACKEND == "openai" else "open"

DATA_DIR = ROOT / "data"
DOCS_DIR = DATA_DIR / "documents"
OUT_DIR = ROOT / "outputs" / VARIANT
DB_PATH = Path(os.environ.get("BACKBONE_DB", OUT_DIR / "abstraction.db"))
LOG_DIR = ROOT / "logs" / VARIANT

if BACKEND == "openai":
    EXTRACT_MODEL = os.environ.get("BACKBONE_EXTRACT_MODEL", "gpt-6-luna")
    ANSWER_MODEL = os.environ.get("BACKBONE_ANSWER_MODEL", "gpt-6-luna")
    EXTRACT_PROMPT_VERSION = "extract-v1"
    EXTRACT_REASONING = "low"
    EXTRACT_WORKERS = int(os.environ.get("BACKBONE_WORKERS", "8"))
    # USD per 1M tokens, gpt-6-luna standard tier, from developers.openai.com/api/docs/pricing (checked 2026-10-05).
    # Override via env if the model or prices change. Batch API is half these rates.
    PRICE_IN = float(os.environ.get("BACKBONE_PRICE_IN_PER_M", "0.10"))
    PRICE_CACHED_IN = float(os.environ.get("BACKBONE_PRICE_CACHED_IN_PER_M", "0.01"))
    PRICE_OUT = float(os.environ.get("BACKBONE_PRICE_OUT_PER_M", "0.50"))
else:
    OLLAMA_HOST = os.environ.get("OLLAMA_HOST_URL", "http://127.0.0.1:11434")
    EXTRACT_MODEL = os.environ.get("BACKBONE_EXTRACT_MODEL", "qwen3.5:9b")
    ANSWER_MODEL = os.environ.get("BACKBONE_ANSWER_MODEL", "qwen3.5:9b")
    EXTRACT_PROMPT_VERSION = "extract-v2-local"  # v1 + rules for small-model mistakes (prompts.EXTRACT_SYSTEM_LOCAL_ADDENDUM)
    # Thinking off: tested on 4 hard documents it was ~4x slower, not more accurate, and looped on one (BH-D112).
    EXTRACT_REASONING = None
    # Ollama serves one request at a time by default (OLLAMA_NUM_PARALLEL=1); extra workers would only queue.
    EXTRACT_WORKERS = int(os.environ.get("BACKBONE_WORKERS", "1"))
    # Local inference has no per-token price.
    PRICE_IN = PRICE_CACHED_IN = PRICE_OUT = 0.0

# Ollama-only limits (harmless for openai).
# One context size for every call, so Ollama never reloads the model between steps.
NUM_CTX = int(os.environ.get("BACKBONE_NUM_CTX", "32768"))
MAX_OUTPUT_TOKENS = int(os.environ.get("BACKBONE_MAX_OUTPUT_TOKENS", "12000"))
# Tool results longer than this are truncated (with a note) so the prompt never overflows NUM_CTX,
# which Ollama would handle by silently dropping the start of the prompt.
MAX_TOOL_CHARS = int(os.environ.get("BACKBONE_MAX_TOOL_CHARS", "24000"))


def cost_usd(input_tokens, cached_input_tokens, output_tokens) -> float:
    return ((input_tokens - cached_input_tokens) * PRICE_IN + cached_input_tokens * PRICE_CACHED_IN
            + output_tokens * PRICE_OUT) / 1e6


def load_api_key() -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if key:
        return key.strip()
    path = os.environ.get("OPENAI_KEY_FILE")
    if not path:
        raise RuntimeError("Set OPENAI_API_KEY, or OPENAI_KEY_FILE pointing to a file containing the key.")
    lines = [l.strip() for l in Path(path).expanduser().read_text(encoding="utf-8-sig").splitlines()
             if l.strip() and not l.strip().startswith("#")]
    # KEY=VALUE format: prefer a name mentioning OPENAI.
    pairs = [l.split("=", 1) for l in lines if "=" in l]
    for name, value in pairs:
        if "OPENAI" in name.upper():
            return value.strip().strip('"').strip("'")
    for line in lines:
        if line.startswith("sk-"):
            return line
    if len(lines) == 1 and "=" not in lines[0]:
        return lines[0]
    raise RuntimeError(f"Could not find an OpenAI key in {path} (expected OPENAI_API_KEY=... or a bare sk-... line).")
