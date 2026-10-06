"""Answer a question from the saved abstraction: the model plans with tools, code computes, the model writes."""
import inspect
import json
import time

from . import config, llm, prompts, queries, verify

_STR = {"type": "string"}
_DATE = {"type": "string", "description": "YYYY-MM-DD"}
_PAT = {"type": "string", "description": "patient name or MRN (optional if only one patient)"}
_STRS = {"type": "array", "items": {"type": "string"}}

TOOL_PARAMS = {
    "list_patients": {},
    "find_patient": {"query": _STR},
    "treatment_goals": {"patient": _PAT},
    "session_counts": {"patient": _PAT, "start": _DATE, "end": _DATE},
    "weekly_summary": {"patient": _PAT, "start": _DATE, "end": _DATE, "service_types": _STRS},
    "goal_compliance": {"patient": _PAT, "start": _DATE, "end": _DATE},
    "day_detail": {"patient": _PAT, "date": _DATE},
    "contacts": {"patient": _PAT, "start": _DATE, "end": _DATE, "service_types": _STRS,
                 "inclusion": {**_STRS, "description": "subset of included, excluded, uncertain"}},
    "measures": {"patient": _PAT},
    "observations": {"patient": _PAT, "domains": {**_STRS, "description": "mood, anxiety, sleep, functioning_activity, "
                     "avoidance, work_return, engagement, safety, family_support, overall_progress, other"},
                     "start": _DATE, "end": _DATE,
                     "observer_types": {**_STRS, "description": "clinician, patient_self_report, collateral_informant, administrative"}},
    "issues": {"patient": _PAT, "kinds": _STRS},
    "compliance_all": {"start": _DATE, "end": _DATE},
    "consecutive_weeks_below": {"n": {"type": "integer"}, "start": _DATE, "end": _DATE},
    "plan_change_comparison": {"patient": _PAT, "change_date": _DATE},
    "get_document_passage": {"doc_id": _STR, "quote": _STR, "line": {"type": "integer"}, "context": {"type": "integer"}},
    "search_documents": {"text": _STR, "patient": _PAT},
    "document_index": {"patient": _PAT},
}
REQUIRED = {"find_patient": ["query"], "day_detail": ["date"], "get_document_passage": ["doc_id"], "search_documents": ["text"]}


def tools():
    out = []
    for name, params in TOOL_PARAMS.items():
        doc = inspect.getdoc(getattr(queries, name)) or name
        out.append({"type": "function", "name": name, "description": doc,
                    "parameters": {"type": "object", "properties": params, "required": REQUIRED.get(name, []),
                                   "additionalProperties": False}})
    return out


def answer(con, question: str, qid: str | None = None, save_dir=None) -> dict:
    t0 = time.perf_counter()
    ctx = {"patients": queries.list_patients(con)}
    user = (f"Question: {question}\n\nCollection context (from the abstraction): {json.dumps(ctx, default=str)}\n"
            "Use the tools to gather every figure and source you need, then answer.")

    def dispatch(name, args):
        return getattr(queries, name)(con, **{k: v for k, v in args.items() if v is not None})

    text, trace, usage = llm.run_tools("answer", config.ANSWER_MODEL, prompts.ANSWER_SYSTEM, user, tools(), dispatch,
                                       reasoning_effort="medium")
    docs = {r["doc_id"]: r["text"] for r in con.execute("SELECT doc_id, text FROM documents")}
    checks = verify.check_citations(text, docs)
    first_pass_bad = [c for c in checks if not c["verified"]]
    if first_pass_bad:  # one repair pass, with tools, then re-check
        bad = "\n".join(f"- [{', '.join(c['cited']) or 'no doc cited'}] “{c['quote']}”" for c in first_pass_bad)
        text, trace2, usage2 = llm.run_tools(
            "answer_repair", config.ANSWER_MODEL, prompts.ANSWER_SYSTEM,
            prompts.REPAIR_USER.format(question=question, bad=bad, draft=text), tools(), dispatch, reasoning_effort="low")
        trace += trace2
        usage += usage2
        checks = verify.check_citations(text, docs)
    still_bad = [c for c in checks if not c["verified"]]
    latency = time.perf_counter() - t0
    result = {
        "id": qid, "question": question, "answer": text, "tool_calls": trace, "latency_s": round(latency, 2),
        "citations": {"checked": len(checks), "verified": len(checks) - len(still_bad),
                      "repaired_after_first_pass": len(first_pass_bad) - len(still_bad) if first_pass_bad else 0,
                      "unverified": still_bad},
        "llm_calls": len(usage), "input_tokens": sum(u["input_tokens"] or 0 for u in usage),
        "output_tokens": sum(u["output_tokens"] or 0 for u in usage), "model": config.ANSWER_MODEL,
        "cached_input_tokens": sum(u["cached_input_tokens"] or 0 for u in usage),
    }
    result["cost_usd"] = round(config.cost_usd(result["input_tokens"], result["cached_input_tokens"], result["output_tokens"]), 5)
    if save_dir:
        save_dir.mkdir(parents=True, exist_ok=True)
        name = qid or time.strftime("q-%Y%m%d-%H%M%S")
        (save_dir / f"{name}.json").write_text(json.dumps(result, indent=1, default=str), encoding="utf-8")
        calls = "\n".join(f"- `{c['tool']}({json.dumps(c['args'])})`" for c in trace)
        cit = result["citations"]
        cit_line = (f"Citation check: {cit['verified']}/{cit['checked']} quotations found verbatim in the cited documents"
                    + (f" (first draft had {len(first_pass_bad)} unverified; one repair pass run)" if first_pass_bad else "") + ".")
        if still_bad:
            cit_line += "\n\nNot verified:\n" + "\n".join(f"- [{', '.join(c['cited'])}] “{c['quote']}”" for c in still_bad)
        (save_dir / f"{name}.md").write_text(
            f"# {name}\n\n**Question.** {question}\n\n{text}\n\n---\n{cit_line}\n\n<details><summary>Run details</summary>\n\n"
            f"Model `{config.ANSWER_MODEL}` · {result['llm_calls']} LLM calls · {result['input_tokens']} in / "
            f"{result['output_tokens']} out tokens · {result['latency_s']} s\n\nTool calls:\n{calls}\n</details>\n",
            encoding="utf-8")
    con.execute("INSERT INTO runs(kind, started_at, seconds, details_json) VALUES (?,?,?,?)",
                ("ask", time.strftime("%Y-%m-%dT%H:%M:%S"), latency,
                 json.dumps({k: result[k] for k in ("id", "question", "llm_calls", "input_tokens", "output_tokens",
                                                     "citations", "tool_calls")}, default=str)))
    con.commit()
    return result
