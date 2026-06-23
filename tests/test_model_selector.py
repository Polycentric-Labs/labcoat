import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import model_selector as ms

def test_load_risk_cards_parses_every_provider():
    cards = ms.load_risk_cards()
    assert "OpenAI" in cards and "Zhipu (GLM)" in cards and "Mistral" in cards
    z = cards["Zhipu (GLM)"]
    assert z["jurisdiction"] == "CN"
    assert "BIS-Entity-List" in z["regulatory_flags"]   # split list, verified fact
    o = cards["OpenAI"]
    assert o["jurisdiction"] == "US" and o["regulatory_flags"] == []  # 'none' -> empty list


def test_gov_safe_true_for_allowlisted_no_adverse_flag():
    cards = ms.load_risk_cards()
    assert ms.government_adjacent_safe(cards["OpenAI"]) is True
    assert ms.government_adjacent_safe(cards["Mistral"]) is True   # FR in EU allowlist
    assert ms.government_adjacent_safe(cards["Cohere"]) is True    # CA in Five-Eyes

def test_gov_safe_false_for_china_and_entity_list():
    cards = ms.load_risk_cards()
    assert ms.government_adjacent_safe(cards["DeepSeek"]) is False   # CN not in allowlist
    assert ms.government_adjacent_safe(cards["Zhipu (GLM)"]) is False # CN + BIS Entity List

def test_gov_safe_adverse_flag_overrides_allowlist():
    # an allowlisted jurisdiction with an adverse regulatory flag is still NOT safe
    card = {"jurisdiction": "US", "regulatory_flags": ["BIS-Entity-List"]}
    assert ms.government_adjacent_safe(card) is False


def test_tier_fleet_size_scaled_defaults():
    assert ms.tier_fleet_size("quick") == (1, 2)
    assert ms.tier_fleet_size("standard") == (5, 7)
    assert ms.tier_fleet_size("deep") == (10, 15)

def test_tier_fleet_size_dynamic_tiers_have_no_upper_cap():
    assert ms.tier_fleet_size("nuclear") == (15, None)
    assert ms.tier_fleet_size("exhaustive") == (15, None)

def test_tier_fleet_size_unknown_defaults_to_standard():
    assert ms.tier_fleet_size("whatever") == (5, 7)


def test_needs_sonar_split_when_many_subjects():
    assert ms.needs_sonar_split(["q1", "q2", "q3", "q4", "q5"]) is True   # > threshold
    assert ms.needs_sonar_split(["q1", "q2"]) is False

def test_needs_sonar_split_at_threshold_is_false():
    # exactly the threshold (4) is NOT a split; only strictly > threshold triggers
    assert ms.needs_sonar_split(["a", "b", "c", "d"]) is False

def test_blunt_critic_benchmarks_are_pointers_not_a_hardcoded_pick():
    b = ms.BLUNT_CRITIC_BENCHMARKS
    names = " ".join(b).lower()
    assert "syceval" in names and "lechmazur" in names
    # it is data/pointers, not a model id
    assert not any("/" in x and x.count("/") == 1 and " " not in x for x in b)


def test_propose_fleet_enriches_candidates_with_cards_and_gov_safe():
    cards = ms.load_risk_cards()
    proposal = ms.propose_fleet(
        candidate_model_ids=["openai/gpt-5.2", "deepseek/deepseek-v3.2", "x-ai/grok-4.3"],
        sub_questions=["a", "b", "c", "d", "e"],
        tier="deep", cards=cards,
    )
    assert proposal["tier_size"] == (10, 15)
    assert proposal["sonar_split_recommended"] is True
    by_id = {m["id"]: m for m in proposal["fleet"]}
    assert by_id["openai/gpt-5.2"]["gov_adjacent_safe"] is True
    assert by_id["deepseek/deepseek-v3.2"]["gov_adjacent_safe"] is False
    assert by_id["x-ai/grok-4.3"]["optional_only"] is True          # Grok flagged optional
    assert "SycEval" in " ".join(proposal["blunt_critic_benchmarks"])

def test_propose_fleet_matches_provider_by_id_prefix_and_handles_unknown():
    cards = ms.load_risk_cards()
    proposal = ms.propose_fleet(["unknown/mystery-model"], ["q"], tier="standard", cards=cards)
    m = proposal["fleet"][0]
    assert m["risk_card"] is None and m["gov_adjacent_safe"] is None   # unknown provider -> no card

def test_propose_fleet_default_load_path_enriches_without_explicit_cards():
    # no cards= argument -> falls back to bundled file; OpenAI must be gov_adjacent_safe
    proposal = ms.propose_fleet(
        candidate_model_ids=["openai/gpt-5"],
        sub_questions=["x"],
        tier="standard",
    )
    m = proposal["fleet"][0]
    assert m["gov_adjacent_safe"] is True   # proves default-load path reached the bundled risk cards
