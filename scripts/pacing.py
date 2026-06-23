# scripts/pacing.py
"""labcoat Tier-2 pacing — the PURE rate-limit / quota state machine. No network: the shell feeds it the real
anthropic-ratelimit-* headers + OpenRouter 402/429 / GET key signals, and acts on the decision. License: MIT.
Author: Allen Byrd."""
from __future__ import annotations

_LOW_REMAINING = 1   # an anthropic-ratelimit-*-remaining at or below this -> back off (graceful pause)


def pacing_decision(signals: dict) -> dict:
    """proceed / graceful-pause(resume_after_s) / hard-stop from the live rate-limit + quota signals.
    signals (all optional): {http_status, retry_after_s, anthropic_tokens_remaining,
    anthropic_requests_remaining, monthly_cap_reached, openrouter_credits_exhausted}."""
    if (signals.get("monthly_cap_reached") or signals.get("openrouter_credits_exhausted")
            or signals.get("http_status") == 402):
        return {"state": "hard-stop", "resume_after_s": None, "reason": "monthly spend cap / credits exhausted"}
    if signals.get("http_status") == 429:
        return {"state": "graceful-pause", "resume_after_s": signals.get("retry_after_s"), "reason": "429 rate-limited"}
    # A low remaining-budget pause may carry NO Retry-After (unlike a 429), so resume_after_s can be None
    # here -> the shell must apply a default backoff interval when it is None.
    for key in ("anthropic_tokens_remaining", "anthropic_requests_remaining"):
        v = signals.get(key)
        if v is not None and v <= _LOW_REMAINING:
            return {"state": "graceful-pause", "resume_after_s": signals.get("retry_after_s"),
                    "reason": f"{key} low ({v})"}
    return {"state": "proceed", "resume_after_s": None, "reason": "within limits"}


def ramp_after_idle(since_resume_s: float, *, full_after_s: float = 300.0) -> float:
    """Throttle factor in [0,1] that ramps traffic up gradually after an idle (avoid acceleration limits):
    0.0 right after resuming, linearly to 1.0 by full_after_s, clamped to 1.0 thereafter. A non-positive
    full_after_s means 'no ramp' -> 1.0."""
    if full_after_s <= 0:
        return 1.0
    return max(0.0, min(1.0, since_resume_s / full_after_s))


def rate_limit_signals(info: dict) -> dict:
    """Map a RateLimitInfo-shaped plain dict (the shell converts the SDK dataclass to this dict, computing
    retry_after_s from resets_at with its real clock) into the signals dict pacing_decision consumes. A
    'rejected'/'blocked'/'rate_limited' status, or utilization >= 1.0, marks a throttle -> http_status 429
    (so pacing_decision yields graceful-pause); retry_after_s passes through. Defensive: a missing/unknown
    shape -> a proceed signal. Pure (no network)."""
    info = info or {}
    status = str(info.get("status") or "").lower()
    util = info.get("utilization")
    throttled = status in {"rejected", "blocked", "rate_limited"} or (
        isinstance(util, (int, float)) and util >= 1.0)
    return {"http_status": 429 if throttled else None, "retry_after_s": info.get("retry_after_s")}
