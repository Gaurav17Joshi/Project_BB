"""Local-model backend (Ollama /api/chat): structured JSON calls, tool-calling loop, per-call logging.

Selected with BACKBONE_BACKEND=ollama. Same interface as llm_openai (call_json, run_tools).
JSON-schema output is enforced by Ollama's grammar-constrained decoding (`format`).
"""
import json
import threading
import time

import httpx

from . import config

_lock = threading.Lock()
_http = httpx.Client(timeout=httpx.Timeout(1800.0, connect=10.0))


def _chat(payload: dict) -> dict:
    r = _http.post(f"{config.OLLAMA_HOST}/api/chat", json=payload)
    r.raise_for_status()
    return r.json()


def _log(step: str, model: str, resp: dict, latency: float, extra: dict | None = None) -> dict:
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "step": step,
        "model": model,
        "latency_s": round(latency, 3),
        "input_tokens": resp.get("prompt_eval_count"),
        "cached_input_tokens": 0,
        "output_tokens": resp.get("eval_count"),
        "reasoning_tokens": None,
        "load_s": round(resp.get("load_duration", 0) / 1e9, 3),
        "gen_tokens_per_s": round(resp["eval_count"] / (resp["eval_duration"] / 1e9), 1)
        if resp.get("eval_count") and resp.get("eval_duration") else None,
        **(extra or {}),
    }
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _lock, open(config.LOG_DIR / "llm_calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def _options(temperature=0.0):
    # num_predict caps runaway generations (seen with thinking on: a >10 min reasoning loop on one document).
    return {"temperature": temperature, "num_ctx": config.NUM_CTX, "num_predict": config.MAX_OUTPUT_TOKENS}


def call_json(step: str, model: str, system: str, user: str, schema: dict, name: str,
              reasoning_effort: str | None = None, extra_log: dict | None = None):
    """One schema-constrained call. `reasoning_effort` set -> model thinks first. Returns (parsed_json, usage)."""
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    # Greedy decoding occasionally loops until the output cap (truncated JSON). A retry at temperature 0 would loop
    # identically, so retries use a little sampling.
    for attempt, temp in enumerate((0.0, 0.3, 0.6)):
        payload = {"model": model, "stream": False, "format": schema, "options": _options(temp),
                   "think": bool(reasoning_effort), "messages": msgs}
        t0 = time.perf_counter()
        resp = _chat(payload)
        rec = _log(step, model, resp, time.perf_counter() - t0, {**(extra_log or {}), "attempt": attempt, "temperature": temp})
        try:
            return json.loads(resp["message"]["content"]), rec
        except json.JSONDecodeError:
            if attempt == 2:
                raise


def _cap(text: str) -> str:
    if len(text) <= config.MAX_TOOL_CHARS:
        return text
    return text[:config.MAX_TOOL_CHARS] + f"\n...[truncated {len(text) - config.MAX_TOOL_CHARS} chars; call a narrower tool]"


def run_tools(step: str, model: str, system: str, user: str, tools: list, dispatch,
              reasoning_effort: str | None = "low", max_turns: int = 12):
    """Tool-calling loop. Returns (final_text, tool_trace, usage_records)."""
    ol_tools = [{"type": "function", "function": {k: t[k] for k in ("name", "description", "parameters")}} for t in tools]
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    trace, usage = [], []
    for _ in range(max_turns):
        payload = {"model": model, "stream": False, "messages": messages, "tools": ol_tools,
                   "options": _options(), "think": bool(reasoning_effort)}
        t0 = time.perf_counter()
        resp = _chat(payload)
        usage.append(_log(step, model, resp, time.perf_counter() - t0))
        msg = resp["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content", ""), trace, usage
        messages.append({"role": "assistant", "content": msg.get("content", ""), "tool_calls": calls})
        for c in calls:
            name = c["function"]["name"]
            args = c["function"].get("arguments") or {}
            if isinstance(args, str):
                args = json.loads(args or "{}")
            try:
                result = dispatch(name, args)
            except Exception as e:  # surface tool errors to the model instead of crashing
                result = {"error": f"{type(e).__name__}: {e}"}
            trace.append({"tool": name, "args": args})
            messages.append({"role": "tool", "tool_name": name, "content": _cap(json.dumps(result, default=str))})
    # out of turns: ask for a final answer without tools
    messages.append({"role": "user", "content": "Stop calling tools now and write the final answer from what you have."})
    t0 = time.perf_counter()
    resp = _chat({"model": model, "stream": False, "messages": messages, "options": _options(),
                  "think": bool(reasoning_effort)})
    usage.append(_log(step, model, resp, time.perf_counter() - t0))
    return resp["message"].get("content", ""), trace, usage
