"""OpenAI backend (Responses API): structured JSON calls, tool-calling loop, and per-call usage logging.

Selected with BACKBONE_BACKEND=openai (the default). Same interface as llm_ollama (call_json, run_tools).
"""
import json
import threading
import time

from openai import OpenAI

from . import config

_client = None
_lock = threading.Lock()


def client() -> OpenAI:
    global _client
    with _lock:
        if _client is None:
            _client = OpenAI(api_key=config.load_api_key(), max_retries=5, timeout=300)
    return _client


def _log(step: str, model: str, resp, latency: float, extra: dict | None = None) -> dict:
    u = getattr(resp, "usage", None)
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "step": step,
        "model": model,
        "latency_s": round(latency, 3),
        "input_tokens": getattr(u, "input_tokens", None),
        "cached_input_tokens": getattr(getattr(u, "input_tokens_details", None), "cached_tokens", None),
        "output_tokens": getattr(u, "output_tokens", None),
        "reasoning_tokens": getattr(getattr(u, "output_tokens_details", None), "reasoning_tokens", None),
        **(extra or {}),
    }
    config.LOG_DIR.mkdir(parents=True, exist_ok=True)
    with _lock, open(config.LOG_DIR / "llm_calls.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def call_json(step: str, model: str, system: str, user: str, schema: dict, name: str,
              reasoning_effort: str | None = "low", extra_log: dict | None = None):
    """One structured-output call. Returns (parsed_json, usage_record)."""
    kwargs = dict(
        model=model,
        input=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        text={"format": {"type": "json_schema", "name": name, "schema": schema, "strict": True}},
    )
    if reasoning_effort:
        kwargs["reasoning"] = {"effort": reasoning_effort}
    t0 = time.perf_counter()
    resp = client().responses.create(**kwargs)
    rec = _log(step, model, resp, time.perf_counter() - t0, extra_log)
    return json.loads(resp.output_text), rec


def run_tools(step: str, model: str, system: str, user: str, tools: list, dispatch,
              reasoning_effort: str | None = "low", max_turns: int = 12):
    """Tool-calling loop. `dispatch(name, args) -> json-serialisable result`.
    Returns (final_text, tool_trace, usage_records)."""
    items = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    trace, usage = [], []
    for _ in range(max_turns):
        kwargs = dict(model=model, input=items, tools=tools)
        if reasoning_effort:
            kwargs["reasoning"] = {"effort": reasoning_effort}
        t0 = time.perf_counter()
        resp = client().responses.create(**kwargs)
        usage.append(_log(step, model, resp, time.perf_counter() - t0))
        calls = [o for o in resp.output if o.type == "function_call"]
        if not calls:
            return resp.output_text, trace, usage
        items += resp.output
        for c in calls:
            args = json.loads(c.arguments or "{}")
            try:
                result = dispatch(c.name, args)
            except Exception as e:  # surface tool errors to the model instead of crashing
                result = {"error": f"{type(e).__name__}: {e}"}
            trace.append({"tool": c.name, "args": args})
            items.append({"type": "function_call_output", "call_id": c.call_id,
                          "output": json.dumps(result, default=str)})
    raise RuntimeError("tool loop did not finish")
