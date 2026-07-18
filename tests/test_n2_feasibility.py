import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "scripts"))
import n2_feasibility as fz

def _rec(mesh, abstract=""):
    return {"concepts": mesh, "mesh": mesh, "abstract": abstract}

def test_bridge_presence_counts_mesh_or_abstract():
    recs = [_rec(["Blood Viscosity"]), _rec([], "platelet aggregation was reduced"),
            _rec(["Raynaud Disease"]), _rec([], "")]
    frac = fz.bridge_presence_fraction(recs, ["blood viscosity", "platelet aggregation", "vascular reactivity"])
    assert abs(frac - 0.5) < 1e-9   # 2 of 4

def test_availability_fraction():
    recs = [_rec(["X"]), _rec([], "abs"), _rec([], "")]
    assert abs(fz.abstract_or_mesh_availability(recs) - (2/3)) < 1e-9

def test_phase0_verdict_go_requires_both_floors_each_side():
    go = fz.phase0_verdict({"raynaud": 0.30, "fishoil": 0.40}, {"raynaud": 0.6, "fishoil": 0.7})
    assert go["go"] is True
    nogo = fz.phase0_verdict({"raynaud": 0.12, "fishoil": 0.40}, {"raynaud": 0.6, "fishoil": 0.7})
    assert nogo["go"] is False and any("raynaud" in r and "presence" in r for r in nogo["reasons"])
