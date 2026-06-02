# scripts/fleet.py
"""polycentric-labcoat fleet runner — standalone, provider-agnostic OpenRouter multi-model fan-out.
Bakes in lessons proven 2026-06-01: reasoning models need >=8000 max_tokens; ~google/gemini-pro-latest
400s (use a resolved id); never put the API key in code/args/logs (env only). License: MIT. Author: Allen Byrd.
"""
from __future__ import annotations
import os
import httpx
from concurrent.futures import ThreadPoolExecutor

# Known-bad alias -> preferred replacement (extend as discovered).
_ALIAS_FALLBACK = {"~google/gemini-pro-latest": "google/gemini-2.5-pro"}
_REASONING_MIN_MAX_TOKENS = 8000
_OPENROUTER_BASE = "https://openrouter.ai/api/v1"


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


def _call_one(model: str, prompt: str, max_tokens: int, temperature: float, api_key: str) -> dict:
    """POST a single chat completion to OpenRouter. Returns {text, in_tokens, out_tokens}."""
    with httpx.Client() as client:
        r = client.post(
            f"{_OPENROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": max_tokens, "temperature": temperature},
            timeout=180.0,
        )
        r.raise_for_status()
        data = r.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        return {"text": text, "in_tokens": usage.get("prompt_tokens", 0),
                "out_tokens": usage.get("completion_tokens", 0)}


def list_models(api_key: str) -> list[str]:
    """Live OpenRouter model catalogue -> list of model ids (for the 'pick your fleet' step)."""
    with httpx.Client() as client:
        r = client.get(f"{_OPENROUTER_BASE}/models",
                       headers={"Authorization": f"Bearer {api_key}"}, timeout=60.0)
        r.raise_for_status()
        return [m["id"] for m in r.json().get("data", [])]


def run_fleet(prompt: str, models: list[dict], *, available: list[str],
              temperature: float = 0.4, parallel: bool = True) -> list[dict]:
    """Fan out `prompt` to each model in parallel. Returns one structured dict per model.
    `models`: list of {id, reasoning(bool), in_price?, out_price?, max_tokens?}. `available`: model ids from list_models().
    Result dict (same 7 keys on EVERY branch): {model, ok, text, in_tokens, out_tokens, cost_est, error}. NEVER contains the api key.
    """
    api_key = _get_api_key()

    def one(spec: dict) -> dict:
        spec_id = spec.get("id", "")
        mid = resolve_model_id(spec_id, available)
        if mid is None:
            return {"model": spec_id, "ok": False, "text": "", "in_tokens": 0, "out_tokens": 0,
                    "cost_est": 0.0, "error": f"model unavailable on OpenRouter: {spec_id}"}
        req_tokens = spec.get("max_tokens", 8000)
        mt = effective_max_tokens(req_tokens, is_reasoning=spec.get("reasoning", False))
        try:
            resp = _call_one(mid, prompt, mt, temperature, api_key)
            cost = estimate_cost(in_tokens=resp.get("in_tokens", 0), out_tokens=resp.get("out_tokens", 0),
                                 in_price=spec.get("in_price", 0.0), out_price=spec.get("out_price", 0.0))
            # Defense-in-depth: scrub the key from model text too, in case an upstream ever reflects it.
            text = resp["text"]
            if api_key and isinstance(text, str):
                text = text.replace(api_key, "<redacted>")
            return {"model": mid, "ok": True, "text": text,
                    "in_tokens": resp.get("in_tokens", 0), "out_tokens": resp.get("out_tokens", 0),
                    "cost_est": cost, "error": None}
        except Exception as e:  # capture per-model; one failure never kills the fleet
            msg = str(e).replace(api_key, "<redacted>") if api_key else str(e)
            return {"model": mid, "ok": False, "text": "", "in_tokens": 0, "out_tokens": 0,
                    "cost_est": 0.0, "error": msg}

    if parallel and len(models) > 1:
        with ThreadPoolExecutor(max_workers=min(8, len(models))) as ex:
            return list(ex.map(one, models))
    return [one(m) for m in models]
