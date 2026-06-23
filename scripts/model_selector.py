# scripts/model_selector.py
"""Deterministic core of labcoat's model-selection engine: risk-card loading, the derived
government-adjacent-safe flag, tier sizing, Sonar-split detection, and fleet-proposal enrichment.
The comparative-advantage MATCHING (which model fits which sub-question) is a Claude-reasoning step in
SKILL.md, not code. License: MIT. Author: Allen Byrd."""
from __future__ import annotations
import pathlib

_DEFAULT_CARDS = pathlib.Path(__file__).resolve().parent.parent / "references" / "model-risk-cards.md"
_COLS = ["provider", "country", "jurisdiction", "state_owned", "data_retention",
         "trains_on_inputs", "regulatory_flags", "notes"]


def load_risk_cards(path: pathlib.Path | None = None) -> dict:
    """Parse the model-risk-cards.md table into {provider: {field: value}}.
    regulatory_flags is a list (split on ';'); 'none'/empty -> []."""
    p = path or _DEFAULT_CARDS
    cards = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) != len(_COLS):
            continue
        if cells[0].lower() == "provider" or cells[0].startswith("---") or not cells[0].strip():
            continue  # header or separator row
        card = dict(zip(_COLS, cells))
        raw = card["regulatory_flags"]
        card["regulatory_flags"] = [] if raw.lower() == "none" else [f.strip() for f in raw.split(";") if f.strip()]
        cards[card["provider"]] = card
    return cards


_FIVE_EYES = {"US", "GB", "UK", "CA", "AU", "NZ"}
_EU = {"AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
       "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE"}
GOV_SAFE_JURISDICTIONS = _FIVE_EYES | _EU                      # default allowlist (operator-configurable)
_ADVERSE_REGULATORY = {"bis-entity-list", "export-controlled", "ofac-sanctioned"}


def government_adjacent_safe(card: dict, allowlist: set | None = None) -> bool:
    """Derived flag: jurisdiction in the allowlist AND no adverse regulatory flag.
    Keys on registry-checkable facts only — NEVER a model-asserted ownership %."""
    allow = allowlist if allowlist is not None else GOV_SAFE_JURISDICTIONS
    juris = (card.get("jurisdiction") or "").upper()
    if juris not in allow:
        return False
    flags = [str(f).strip().lower() for f in (card.get("regulatory_flags") or [])]
    return not any(f in _ADVERSE_REGULATORY for f in flags)


_TIER_SIZES = {"quick": (1, 2), "standard": (5, 7), "deep": (10, 15),
               "exhaustive": (15, None), "nuclear": (15, None), "skynet": (15, None)}


def tier_fleet_size(tier: str) -> tuple[int, int | None]:
    """(min, max) recommended fleet size for a tier; max None = dynamic/uncapped. Unknown -> standard."""
    return _TIER_SIZES.get((tier or "").strip().lower(), (5, 7))


_SONAR_SPLIT_THRESHOLD = 4   # more distinct sub-questions than this -> recommend many Sonar-Pro queries


def needs_sonar_split(sub_questions: list[str], threshold: int = _SONAR_SPLIT_THRESHOLD) -> bool:
    """True when there are too many distinct subjects for one deep query -> recommend a Sonar-Pro split
    (and ASK whether to upgrade any split to Perplexity Deep Research)."""
    return len([q for q in sub_questions if str(q).strip()]) > threshold


BLUNT_CRITIC_BENCHMARKS = [
    "SycEval (arXiv 2502.08177)",
    "CriticEval (arXiv 2402.13764)",
    "FindTheFlaws (arXiv 2503.22989)",
    "lechmazur/sycophancy leaderboard (GitHub)",
]

# Map an OpenRouter id prefix -> the risk-card provider key.
_PREFIX_PROVIDER = {
    "openai": "OpenAI", "anthropic": "Anthropic", "google": "Google", "meta-llama": "Meta (Llama)",
    "amazon": "Amazon (Nova)", "x-ai": "xAI (Grok)", "mistralai": "Mistral", "cohere": "Cohere",
    "deepseek": "DeepSeek", "qwen": "Alibaba (Qwen)", "moonshotai": "Moonshot (Kimi)", "z-ai": "Zhipu (GLM)",
}


def _card_for(model_id: str, cards: dict) -> dict | None:
    prefix = (model_id or "").split("/", 1)[0].lower()
    provider = _PREFIX_PROVIDER.get(prefix)
    return cards.get(provider) if provider else None


def propose_fleet(candidate_model_ids: list[str], sub_questions: list[str], *,
                  tier: str, cards: dict | None = None) -> dict:
    """Enrich a Claude-reasoning-proposed candidate list with each model's risk card, the derived
    gov-adjacent-safe flag, and an optional-only marker (Grok); attach tier size, Sonar-split advice,
    and the blunt-critic benchmark pointers. Does NOT pick models — that is the SKILL.md reasoning step."""
    crd = cards if cards is not None else load_risk_cards()
    fleet = []
    for mid in candidate_model_ids:
        card = _card_for(mid, crd)
        fleet.append({
            "id": mid,
            "risk_card": card,
            "gov_adjacent_safe": government_adjacent_safe(card) if card else None,
            "optional_only": bool(card and "optional-only" in (card.get("notes") or "").lower()),
        })
    return {
        "fleet": fleet,
        "tier_size": tier_fleet_size(tier),
        "sonar_split_recommended": needs_sonar_split(sub_questions),
        "blunt_critic_benchmarks": BLUNT_CRITIC_BENCHMARKS,
    }
