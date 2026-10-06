"""Model backend switch. Both backends expose call_json and run_tools with the same signatures.

The backend module is imported on first use, so commands that only read the saved abstraction
(`cli.py show`, `rebuild`, the web summary) work without the openai/httpx packages or a running model.
"""
from . import config

_impl = None


def _backend():
    global _impl
    if _impl is None:
        if config.BACKEND == "ollama":
            from . import llm_ollama as _impl_mod
        else:
            from . import llm_openai as _impl_mod
        _impl = _impl_mod
    return _impl


def call_json(*args, **kwargs):
    """One schema-constrained call. Returns (parsed_json, usage_record)."""
    return _backend().call_json(*args, **kwargs)


def run_tools(*args, **kwargs):
    """Tool-calling loop. Returns (final_text, tool_trace, usage_records)."""
    return _backend().run_tools(*args, **kwargs)
