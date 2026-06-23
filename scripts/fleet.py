# scripts/fleet.py
"""polycentric-labcoat fleet runner — standalone, provider-agnostic OpenRouter multi-model fan-out.
Bakes in lessons proven 2026-06-01: reasoning models need >=8000 max_tokens; ~google/gemini-pro-latest
400s (use a resolved id); never put the API key in code/args/logs (env only). License: MIT. Author: Allen Byrd.
"""
from __future__ import annotations
import json
import os
import re as _re
import httpx
from concurrent.futures import ThreadPoolExecutor

# Known-bad alias -> preferred replacement (extend as discovered).
_ALIAS_FALLBACK = {"~google/gemini-pro-latest": "google/gemini-2.5-pro"}
_REASONING_MIN_MAX_TOKENS = 8000
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

# Verified 2026-06: Gemini-class server cap ~300s (Vertex); OpenRouter itself has no hard wall.
_MODEL_TIMEOUTS = {"gemini": 270.0}   # stay under the 300s cap with headroom
_DEFAULT_TIMEOUT = 600.0


def timeout_for_model(model_id: str, default: float = _DEFAULT_TIMEOUT) -> float:
    """Client-side timeout sized to the model's verified server behavior."""
    mid = (model_id or "").lower()
    for key, t in _MODEL_TIMEOUTS.items():
        if key in mid:
            return t
    return default


_DETERMINISTIC_STATUS = {400, 401, 403, 404, 405, 406, 422}


def classify_failure(error: Exception) -> str:
    """'transient' (a rerun may succeed) vs 'deterministic' (a rerun fails identically -> don't burn money)."""
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        if code in _DETERMINISTIC_STATUS:
            return "deterministic"
        if code == 429 or 500 <= code <= 599:
            return "transient"
        return "deterministic"          # unknown 4xx -> treat as deterministic
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError)):
        return "transient"
    return "transient"                  # unknown error -> the always-rerun bias (bounded by max_attempts)


_COMPLETE_REASONS = {"stop", "end_turn", "eos"}


def is_complete(finish_reason) -> bool:
    """A generation is trusted complete ONLY on an explicit stop reason.
    length / content_filter / None = NOT complete (rerun); never silently promote incomplete to complete."""
    return finish_reason in _COMPLETE_REASONS


def effective_max_tokens(requested: int, *, is_reasoning: bool) -> int:
    """Reasoning models consume hidden reasoning tokens; floor their budget so visible output isn't truncated."""
    if is_reasoning:
        return max(requested, _REASONING_MIN_MAX_TOKENS)
    return requested


def resolve_model_id(model: str, available: list[str]) -> str | None:
    """Return a usable model id from `available`, applying known alias fallbacks; None if unavailable."""
    if model in available:
        return model
    fb = _ALIAS_FALLBACK.get(model)
    if fb and fb in available:
        return fb
    return None


def estimate_cost(*, in_tokens: int, out_tokens: int, in_price: float, out_price: float) -> float:
    """USD estimate from per-million-token prices."""
    return in_tokens / 1_000_000 * in_price + out_tokens / 1_000_000 * out_price


def _get_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set (env/1Password only; never hardcode).")
    return key


def run_with_retry(make_call, *, max_attempts: int = 3, should_continue=None) -> dict:
    """Tolerance-bounded always-rerun + deterministic-failure guard + known-incomplete honesty flag.
    make_call() -> a result dict containing 'finish_reason'. `should_continue` (optional) is checked
    BEFORE each attempt (e.g. a spend-tolerance gate); returning False stops with known-incomplete.
    Returns {result, completion_status in {complete, known-incomplete, deterministic-fail}, attempts, error}."""
    last_result, last_error, attempts = None, None, 0
    while attempts < max_attempts:
        if should_continue is not None and not should_continue():
            return {"result": last_result, "completion_status": "known-incomplete",
                    "attempts": attempts, "error": "stopped before attempt (should_continue=False)"}
        attempts += 1
        try:
            res = make_call()
        except Exception as e:                       # noqa: BLE001 - classify all failures
            last_error = e
            if classify_failure(e) == "deterministic":
                return {"result": None, "completion_status": "deterministic-fail",
                        "attempts": attempts, "error": str(e)}
            continue                                  # transient -> rerun
        last_result = res
        if is_complete(res.get("finish_reason")):
            return {"result": res, "completion_status": "complete", "attempts": attempts, "error": None}
        # incomplete (truncated / no stop) -> rerun until attempts exhausted
    return {"result": last_result, "completion_status": "known-incomplete",
            "attempts": attempts, "error": str(last_error) if last_error else "max attempts, still incomplete"}


def _call_one_streaming(model: str, prompt: str, max_tokens: int, temperature: float, api_key: str,
                        *, capture_path: str | None = None, timeout: float = _DEFAULT_TIMEOUT) -> dict:
    """Stream a chat completion. Flush content to capture_path AS it arrives (so a mid-stream break
    preserves partial output on disk). Returns {text, finish_reason, in_tokens, out_tokens}.

    Accepted tradeoffs:
    - reruns reopen the same capture_path in "w" mode, so only the latest attempt's partial is kept (acceptable).
    - strict completion means a provider that never emits an explicit stop reason will be re-run
      (the honesty-over-cost choice: never silently promote incomplete to complete).
    - unknown exceptions default to transient, bounded by max_attempts (via run_with_retry caller).
    """
    text_parts, finish_reason, usage = [], None, {}
    # FIX C: initialize cap outside the try so finally is always safe even if open() raises.
    cap = None
    try:
        if capture_path:
            cap = open(capture_path, "w", encoding="utf-8")
        with httpx.Client() as client:
            with client.stream(
                "POST", f"{_OPENROUTER_BASE}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens, "temperature": temperature, "stream": True},
                timeout=timeout,
            ) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if choices:
                        piece = (choices[0].get("delta") or {}).get("content")
                        if piece:
                            # FIX C: scrub api_key from streamed content before writing to disk or memory.
                            out_piece = piece.replace(api_key, "<redacted>") if api_key else piece
                            text_parts.append(out_piece)
                            if cap:
                                cap.write(out_piece); cap.flush()
                        fr = choices[0].get("finish_reason")
                        if fr:
                            finish_reason = fr
                    if chunk.get("usage"):
                        usage = chunk["usage"]
    finally:
        if cap:
            cap.close()
    return {"text": "".join(text_parts), "finish_reason": finish_reason,
            "in_tokens": usage.get("prompt_tokens", 0), "out_tokens": usage.get("completion_tokens", 0)}


def list_models(api_key: str) -> list[str]:
    """Live OpenRouter model catalogue -> list of model ids (for the 'pick your fleet' step)."""
    with httpx.Client() as client:
        r = client.get(f"{_OPENROUTER_BASE}/models",
                       headers={"Authorization": f"Bearer {api_key}"}, timeout=60.0)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]


def _safe_name(model_id: str) -> str:
    return _re.sub(r"[^A-Za-z0-9._-]", "_", model_id)


def run_fleet(prompt: str, models: list[dict], *, available: list[str],
              temperature: float = 0.4, parallel: bool = True,
              capture_dir: str | None = None, max_attempts: int = 3) -> list[dict]:
    """Fan out `prompt` across models with streaming + disk-capture + tolerance-bounded rerun.
    Each result has the original 7 keys PLUS completion_status / rerun_count / capture_path. No api key in results."""
    api_key = _get_api_key()
    # FIX A: create capture_dir once up front so _call_one_streaming never hits FileNotFoundError
    # (which run_with_retry would misclassify as transient and waste all max_attempts retrying).
    if capture_dir is not None:
        os.makedirs(capture_dir, exist_ok=True)

    def one(spec: dict) -> dict:
        spec_id = spec.get("id", "")
        mid = resolve_model_id(spec_id, available)
        base = {"model": spec_id, "ok": False, "text": "", "in_tokens": 0, "out_tokens": 0,
                "cost_est": 0.0, "error": None, "completion_status": None, "rerun_count": 0,
                "capture_path": None}
        if mid is None:
            # FIX B: set completion_status so callers can distinguish unavailable from other failures.
            base["error"] = f"model unavailable on OpenRouter: {spec_id}"
            base["completion_status"] = "unavailable"
            return base
        mt = effective_max_tokens(spec.get("max_tokens", 8000), is_reasoning=spec.get("reasoning", False))
        cap = f"{capture_dir.rstrip('/')}/{_safe_name(mid)}.partial" if capture_dir else None
        outcome = run_with_retry(
            lambda: _call_one_streaming(mid, prompt, mt, temperature, api_key,
                                        capture_path=cap, timeout=timeout_for_model(mid)),
            max_attempts=max_attempts)
        res = outcome["result"] or {}
        text = res.get("text", "")
        if api_key and isinstance(text, str):
            text = text.replace(api_key, "<redacted>")
        cost = estimate_cost(in_tokens=res.get("in_tokens", 0), out_tokens=res.get("out_tokens", 0),
                             in_price=spec.get("in_price", 0.0), out_price=spec.get("out_price", 0.0))
        err = outcome["error"].replace(api_key, "<redacted>") if (outcome["error"] and api_key) else outcome["error"]
        return {"model": mid, "ok": outcome["completion_status"] == "complete", "text": text,
                "in_tokens": res.get("in_tokens", 0), "out_tokens": res.get("out_tokens", 0),
                "cost_est": cost, "error": err, "completion_status": outcome["completion_status"],
                "rerun_count": outcome["attempts"], "capture_path": cap}

    if parallel and len(models) > 1:
        with ThreadPoolExecutor(max_workers=min(8, len(models))) as ex:
            return list(ex.map(one, models))
    return [one(m) for m in models]
