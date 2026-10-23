
import math
import re

import pandas as pd
import pytest

from src.agent.explainer import NUM_RE, ReasonExplainer
from src.config import now_ist
from src.core.optimizer import WorkloadOptimizer

BAL = {"cost": 0.7, "carbon": 0.8, "water": 0.6}
COST, CARBON, WATER = ({"cost": 1, "carbon": 0, "water": 0}, {"cost": 0, "carbon": 1, "water": 0},
                       {"cost": 0, "carbon": 0, "water": 1})


@pytest.fixture(scope="module")
def opt():
    return WorkloadOptimizer()


CASES = [
    (1, 1, True), (10, 1, False), (600, 2, True), (10000, 5, True), (10000, 5, False),
    (250000, 3, True), (5_000_000, 1, True), (5_000_000, 30, True), (100, 30, True), (12345.6, 7, True),
]


@pytest.mark.parametrize("gpu,days,flex", CASES)
def test_invariants_hold_for_extreme_jobs(opt, gpu, days, flex):
    res = opt.find_best_placement(gpu, days, BAL, flex)
    rec, usual, meta, rows = res["recommended"], res["usual"], res["meta"], res["all_options"]
    assert meta["deadline_met"]
    assert rec["hours_from_now"] + meta["duration_hours"] <= meta["deadline_hours"]
    assert rec["finish_day"] <= min(days, 30)
    scores = [r["score"] for r in rows]
    assert rec["score"] == min(scores) and 20 <= min(scores) and max(scores) <= 100
    for r in rows:
        for k in ("cost_inr", "carbon_kg", "water_liters"):
            assert math.isfinite(r[k]) and r[k] > 0
    if not flex:
        assert rec["hours_from_now"] == 0
    assert 0 <= meta["confidence"] <= 1 and meta["confidence_label"] in {"High", "Medium", "Low"}
    assert usual["region"] == "Mumbai" and usual["hours_from_now"] == 0


def test_sliders_move_the_result_in_the_right_direction(opt):
    c, g, w = (opt.find_best_placement(10000, 5, x, True)["recommended"] for x in (COST, CARBON, WATER))
    assert c["cost_inr"] <= min(g["cost_inr"], w["cost_inr"]) * 1.02
    assert g["carbon_kg"] <= min(c["carbon_kg"], w["carbon_kg"]) * 1.02
    assert w["water_liters"] <= min(c["water_liters"], g["water_liters"]) * 1.02


def test_short_job_money_only_runs_entirely_in_cheap_solar_hours(opt):
    rec = opt.find_best_placement(600, 2, COST, True)["recommended"]      # 3-hour run
    assert rec["solar_hours_pct"] == 100 and rec["peak_hours_pct"] == 0


def test_tiny_slider_change_does_not_flip_the_answer(opt):
    a = opt.find_best_placement(10000, 5, {"cost": 70, "carbon": 80, "water": 60}, True)["recommended"]
    b = opt.find_best_placement(10000, 5, {"cost": 71, "carbon": 80, "water": 60}, True)["recommended"]
    assert a["region"] == b["region"]


def test_same_inputs_same_answer(opt):
    a, b = (opt.find_best_placement(10000, 5, BAL, True)["recommended"] for _ in range(2))
    assert (a["region"], a["start_time"], a["score"]) == (b["region"], b["start_time"], b["score"])


def test_works_when_the_weather_cache_is_stale(opt):
    later = pd.Timestamp(now_ist()) + pd.Timedelta(days=10)
    res = opt.find_best_placement(10000, 5, BAL, True, now=later)
    assert res["meta"]["ml_hours_share"] > 0.99 and res["meta"]["deadline_met"]


@pytest.mark.parametrize("bad", [0, -5, float("nan"), float("inf"), "abc", None])
def test_bad_gpu_hours_rejected(opt, bad):
    with pytest.raises(ValueError):
        opt.find_best_placement(bad, 5, BAL, True)


@pytest.mark.parametrize("bad", [0, -1, float("nan"), "x"])
def test_bad_deadline_rejected(opt, bad):
    with pytest.raises(ValueError):
        opt.find_best_placement(1000, bad, BAL, True)


def test_oversized_inputs_are_capped_not_crashed(opt):
    res = opt.find_best_placement(10 ** 12, 5000, BAL, True)
    assert res["meta"]["inputs_capped"] and res["meta"]["deadline_met"]


@pytest.mark.parametrize("weights", [{"cost": 0, "carbon": 0, "water": 0}, {"cost": 1}, {}, {"cost": -3, "carbon": 2, "water": 1}])
def test_odd_weights_still_work(opt, weights):
    assert opt.find_best_placement(10000, 5, weights, True)["meta"]["deadline_met"]


def test_unknown_usual_region_falls_back(opt):
    assert opt.find_best_placement(10000, 5, BAL, True, usual_region="Atlantis")["usual"]["region"] == "Mumbai"


def test_every_region_can_be_the_usual_choice(opt):
    for region in ("Mumbai", "Delhi NCR", "Bengaluru", "Chennai", "Hyderabad"):
        res = opt.find_best_placement(10000, 5, BAL, True, usual_region=region)
        assert res["usual"]["region"] == region and res["recommended"]["score"] <= res["usual"]["score"]


def test_narration_is_grounded_on_real_optimizer_output(opt, monkeypatch):
    ex = ReasonExplainer()
    monkeypatch.setattr(ex, "_ollama_ready", lambda: False)
    texts = set()
    for w in (BAL, COST, CARBON, WATER):
        res = opt.find_best_placement(10000, 5, w, True)
        u, r, m = res["usual"], res["recommended"], res["meta"]
        facts = ex._build_facts(u, r, w, m)
        text = ex.generate_reason(u, r, w, m)
        texts.add(text)
        assert all(n.replace(",", "") in facts["numbers"] for n in NUM_RE.findall(text))
        if r["water_liters"] > u["water_liters"] * 1.01:
            assert "more cooling water" in text
        if r["carbon_kg"] > u["carbon_kg"] * 1.01:
            assert "more carbon" in text
        if not facts["same_plan"]:
            assert r["region"] in text
    assert len(texts) >= 2