import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import pytest
import north_star

def test_three_pillars_named_and_described():
    ps = north_star.pillars()
    assert len(ps) == 3
    names = [name.lower() for name, _essence in ps]
    assert any("curiosity" in n for n in names)
    assert any("skepticism" in n for n in names)
    assert any("dreaming bigger" in n for n in names)
    # each pillar carries a non-trivial essence line
    assert all(isinstance(essence, str) and len(essence) > 30 for _name, essence in ps)

def test_pillars_is_immutable_tuple():
    assert isinstance(north_star.PILLARS, tuple)
    assert north_star.pillars() is north_star.PILLARS

def test_honesty_stake_states_both_halves():
    stake = north_star.honesty_stake()
    assert isinstance(stake, str) and len(stake) > 60
    low = stake.lower()
    # half 1: ambition unbounded in the engine
    assert "unbounded" in low and ("ambition" in low or "bold" in low)
    # half 2: claims bounded by verification
    assert ("claim" in low) and ("verif" in low or "primary source" in low)
    # the moat framing (overclaiming forbidden -> trustworthiness)
    assert "trust" in low

def test_honesty_stake_is_the_module_constant():
    assert north_star.honesty_stake() is north_star.HONESTY_STAKE

def test_every_pipeline_phase_0_to_6_has_a_hook():
    # "enforced-lite" made real: every gate must have a defined reflection hook
    assert set(north_star.PHASE_HOOKS) == {0, 1, 2, 3, 4, 5, 6}
    for n in range(7):
        hook = north_star.reflection_for_phase(n)
        assert isinstance(hook, str) and len(hook) > 30

def test_reflection_for_phase_rejects_unknown_phase():
    with pytest.raises(ValueError):
        north_star.reflection_for_phase(7)
    with pytest.raises(ValueError):
        north_star.reflection_for_phase(-1)

def test_phase4_hook_encodes_the_honesty_invariant():
    # Phase 4 (adversarial validation) must restate audit-v2's rule, in spirit
    h4 = north_star.reflection_for_phase(4).lower()
    assert "known-incomplete" in h4 and "confirmed" in h4

def test_early_phases_lean_curiosity_late_phases_lean_application():
    # Phase 0/1 (scope/harvest) evoke digging wider; Phase 5 (synthesize) evokes applying
    assert "deep" in north_star.reflection_for_phase(0).lower() or \
           "broad" in north_star.reflection_for_phase(0).lower()
    assert "verif" in north_star.reflection_for_phase(3).lower() or \
           "skeptic" in north_star.reflection_for_phase(3).lower() or \
           "primary source" in north_star.reflection_for_phase(3).lower()

def test_north_star_doc_exists_and_holds_the_core():
    doc = pathlib.Path(__file__).resolve().parent.parent / "references" / "north-star.md"
    assert doc.exists(), "references/north-star.md is the human-facing deliverable"
    text = doc.read_text(encoding="utf-8")
    # the FULL verbatim NORTH STAR line from the charter (incl. the "Rinse and repeat." close, so a
    # future truncation of the charter quote is caught)
    assert ("A repeating cycle of mandatory intense curiosity, obsessive skepticism in the pursuit of "
            "validated truth, and religious devotion to dreaming bigger. Rinse and repeat.") in text
    # the three pillar names appear
    assert "intense curiosity" in text
    assert "obsessive skepticism" in text
    assert "dreaming bigger" in text
    # the honesty stake essence + the pointer to the machine form
    assert "unbounded" in text.lower() and "verif" in text.lower()
    assert "scripts/north_star.py" in text
    # the enforced-lite per-phase hooks are referenced
    assert "enforced-lite" in text.lower() or "per-phase" in text.lower()
