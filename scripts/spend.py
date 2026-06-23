"""labcoat spend model: two-line ESTIMATE (OpenRouter + Claude-orchestration) + a live Tracker + the
tolerance-gate logic. The per-loop over-tolerance option menu is SKILL.md prose. License: MIT. Author: Allen Byrd."""
from __future__ import annotations

# Calibration seeds (rough, low-confidence). Claude-orchestration is the DOMINANT, variable line;
# refine these from real-run telemetry (the 2026-06 meta-research: ~$1.39 OpenRouter / 33 fleet calls).
_CLAUDE_IN_PRICE = 5.0      # Opus-class $/Mtok input
_CLAUDE_OUT_PRICE = 25.0    # Opus-class $/Mtok output


def estimate_openrouter(model_specs: list[dict], *, in_tokens: int = 1500, out_tokens: int = 8000) -> float:
    """Projected OpenRouter fleet cost: sum over models of (in/out tokens x per-Mtok price)."""
    return sum(in_tokens / 1e6 * s.get("in_price", 0.0) + out_tokens / 1e6 * s.get("out_price", 0.0)
               for s in model_specs)


def estimate_claude_orchestration(n_agents: int, *, avg_in_tokens: int = 15000, avg_out_tokens: int = 8000,
                                  in_price: float = _CLAUDE_IN_PRICE, out_price: float = _CLAUDE_OUT_PRICE) -> float:
    """Rough heuristic for the Claude-orchestration cost (the dominant, variable line, LOW confidence):
    n_agents (harvest + fleet-orchestration + verify + validate + synth) x typical per-agent tokens x price.
    Honestly approximate — calibrate from real-run telemetry over time."""
    per_agent = avg_in_tokens / 1e6 * in_price + avg_out_tokens / 1e6 * out_price
    return n_agents * per_agent


def two_line_estimate(model_specs: list[dict], *, n_agents: int, is_loop_cycle: bool = False,
                      in_tokens: int = 1500, out_tokens: int = 8000) -> dict:
    """The two-line estimate the cost gate shows: OpenRouter fleet + Claude-orchestration + total + a
    confidence label ('tight' for a one-off; 'very-rough' for a loop cycle that can rabbit-hole)."""
    orr = round(estimate_openrouter(model_specs, in_tokens=in_tokens, out_tokens=out_tokens), 3)
    claude = estimate_claude_orchestration(n_agents)
    return {"openrouter_usd": orr, "claude_orchestration_usd": round(claude, 2),
            "total_usd": round(orr + claude, 2),
            "confidence": "very-rough" if is_loop_cycle else "tight"}


class Tracker:
    """Accumulates ACTUAL spend across a session/cycle, both lines, for the health ticker + tolerance gate."""

    def __init__(self) -> None:
        self._openrouter = 0.0
        self._claude = 0.0
        self._reserved = 0.0

    def add_openrouter(self, usd: float) -> None:
        self._openrouter += max(0.0, usd)

    def add_claude(self, *, in_tokens: int, out_tokens: int,
                   in_price: float = _CLAUDE_IN_PRICE, out_price: float = _CLAUDE_OUT_PRICE) -> None:
        self._claude += in_tokens / 1e6 * in_price + out_tokens / 1e6 * out_price

    def add_claude_cost(self, usd: float) -> None:
        """Fold a DIRECT USD figure (the Agent-SDK ResultMessage.total_cost_usd) into the Claude-orchestration
        line, alongside the token-based add_claude. None / falsy is ignored; a negative is clamped to 0 so a
        bad datapoint can never REDUCE the accumulated spend (the at-least-once / never-undercount posture)."""
        if usd:
            self._claude += max(0.0, usd)

    def openrouter(self) -> float:
        return round(self._openrouter, 3)

    def claude(self) -> float:
        return round(self._claude, 2)

    def total(self) -> float:
        return round(self._openrouter + self._claude, 2)

    def reserve(self, usd: float) -> None:
        """Reserve estimated spend BEFORE firing an outbound call (paired with append_ledger(intent, fsync=True)).
        A crash leaves the reservation standing -> spend is never under-counted (the at-least-once cost backstop)."""
        self._reserved += max(0.0, usd)

    def release(self, usd: float) -> None:
        """Drop a reservation on a CONFIRMED result (then add_* the actual committed cost). Clamped at 0 so an
        unpaired / double release can never drive the reserved pool NEGATIVE (a negative reservation would
        under-count total_with_reserved and defeat the pessimistic at-least-once cost backstop)."""
        self._reserved = max(0.0, self._reserved - usd)

    def reserved(self) -> float:
        return round(self._reserved, 2)

    def breakdown(self) -> dict:
        return {"openrouter_usd": self.openrouter(), "claude_orchestration_usd": self.claude(),
                "total_usd": self.total(), "reserved_usd": self.reserved(),
                "total_with_reserved_usd": round(self._openrouter + self._claude + self._reserved, 2)}


def tolerance_check(projected_total: float, tolerance: float) -> dict:
    """Is the projected cumulative spend within the hard TOLERANCE ceiling? over_by = how far past (0 if within)."""
    over = projected_total - tolerance
    return {"within_tolerance": projected_total <= tolerance,
            "over_by": round(over, 2) if over > 0 else 0.0, "tolerance": tolerance}


def would_next_loop_breach(spent_so_far: float, next_loop_est: float, tolerance: float) -> dict:
    """Per-loop gate: would (spent + the next loop's estimate) breach tolerance? If so, STOP that loop
    (not the session) and surface the option menu (SKILL.md). Returns the tolerance_check on the sum."""
    return tolerance_check(spent_so_far + next_loop_est, tolerance)


def quota_signals(*, http_status=None, retry_after_s=None,
                  anthropic_tokens_remaining=None, anthropic_requests_remaining=None,
                  mtd_total_usd=None, monthly_cap_usd=None,
                  openrouter_limit_remaining=None, openrouter_credits_exhausted=None) -> dict:
    """Assemble the signals dict pacing.pacing_decision consumes, deriving the two quota booleans from live
    figures: monthly_cap_reached when month-to-date spend has reached the Anthropic monthly cap, and
    openrouter_credits_exhausted when OpenRouter credits are gone (explicit flag OR limit_remaining <= 0).
    The graceful-pause vs hard-stop CLASSIFICATION stays in pacing.pacing_decision (single source of truth);
    this only FEEDS it. Pure: every live value is passed in by the shell (the Gate-3 additive detector)."""
    monthly_cap_reached = (mtd_total_usd is not None and monthly_cap_usd is not None
                           and mtd_total_usd >= monthly_cap_usd)
    credits_exhausted = bool(openrouter_credits_exhausted) or (
        openrouter_limit_remaining is not None and openrouter_limit_remaining <= 0)
    return {"http_status": http_status, "retry_after_s": retry_after_s,
            "anthropic_tokens_remaining": anthropic_tokens_remaining,
            "anthropic_requests_remaining": anthropic_requests_remaining,
            "monthly_cap_reached": monthly_cap_reached,
            "openrouter_credits_exhausted": credits_exhausted}


def requires_explicit_burn(total_usd, *, threshold: float = 25.0) -> bool:
    """R8 money gate: a paid batch whose ESTIMATED total exceeds the threshold (default $25) requires an
    explicit 'yes, burn it' operator confirmation before it may fire. Pure predicate; None -> False
    (no estimate -> the caller must still gate, but this predicate only fires on a known over-threshold)."""
    return total_usd is not None and total_usd > threshold
