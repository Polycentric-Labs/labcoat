# scripts/route_integration.py
"""Thin wrapper over the sonar-router classifier (https://github.com/Polycentric-Labs/sonar-router).
Returns its JSON verdict; degrades to a safe default (degraded=True) if the router is unavailable or returns
an unexpected shape. Assumes sonar-router is checked out as a sibling directory (i.e. ../sonar-router/
relative to the polycentric-labcoat root). License: MIT."""
from __future__ import annotations
import json, subprocess, sys, pathlib

_ROUTER = pathlib.Path(__file__).resolve().parents[2] / "sonar-router" / "scripts" / "route.py"


def _run_route_script(query: str) -> str:
    # query is passed as a subprocess ARG (no shell=True -> no shell injection; it is visible in a process
    # listing, which is acceptable because the redaction gate runs upstream of any outbound query).
    # route.py is pure CPU (~50 ms typical); 15 s is a generous ceiling for cold interpreter startup before degrade.
    return subprocess.run([sys.executable, str(_ROUTER), query],
                          capture_output=True, text=True, check=True, timeout=15).stdout


def _safe_default(rationale: str) -> dict:
    return {"recommended_tool": "perplexity_ask", "fallback": "WebFetch",
            "rationale": rationale, "degraded": True}


def route_query(query: str) -> dict:
    """Return sonar-router's routing verdict for `query`; safe default (degraded=True) if the router can't run
    or returns an unexpected shape."""
    try:
        payload = json.loads(_run_route_script(query))
        if not isinstance(payload, dict) or "recommended_tool" not in payload:
            keys = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__
            raise ValueError(f"unexpected router schema: {keys}")
        return payload
    except subprocess.CalledProcessError as e:
        router_msg = (e.stdout or "").strip() or "(no stdout)"
        return _safe_default(f"sonar-router exited {e.returncode}: {router_msg}")
    except Exception as e:
        return _safe_default(f"sonar-router unavailable ({type(e).__name__}); default route.")
