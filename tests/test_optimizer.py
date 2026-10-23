import math

import pytest

from src.core.optimizer import WorkloadOptimizer

WEIGHTS = {"cost": 0.8, "carbon": 0.1, "water": 0.1}


@pytest.fixture(scope="module")
def optimizer():
    return WorkloadOptimizer()


def test_urgent_job_starts_immediately(optimizer):
    res = optimizer.find_best_placement(gpu_hours=5000, deadline_days=2, weights=WEIGHTS, is_flexible=False)
    assert res["recommended"]["start_time"] == res["usual"]["start_time"]


def test_recommendation_never_scores_worse_than_usual(optimizer):
    res = optimizer.find_best_placement(gpu_hours=5000, deadline_days=3, weights=WEIGHTS, is_flexible=True)
    assert res["recommended"]["score"] <= res["usual"]["score"]


@pytest.mark.parametrize("gpu_hours,days", [(2000, 1), (10000, 5), (50000, 3), (500, 7)])
def test_deadline_is_always_met(optimizer, gpu_hours, days):
    res = optimizer.find_best_placement(gpu_hours, days, WEIGHTS, is_flexible=True)
    meta, rec = res["meta"], res["recommended"]
    assert meta["deadline_met"]
    assert rec["hours_from_now"] + meta["duration_hours"] <= days * 24


def test_sliders_change_the_answer(optimizer):
    picks = set()
    for w in ({"cost": 1, "carbon": 0, "water": 0}, {"cost": 0, "carbon": 1, "water": 0},
              {"cost": 0, "carbon": 0, "water": 1}):
        r = optimizer.find_best_placement(10000, 5, w, True)["recommended"]
        picks.add((r["region"], r["start_time"]))
    assert len(picks) >= 2


def test_same_inputs_give_same_answer(optimizer):
    a = optimizer.find_best_placement(10000, 5, WEIGHTS, True)["recommended"]
    b = optimizer.find_best_placement(10000, 5, WEIGHTS, True)["recommended"]
    assert (a["region"], a["start_time"]) == (b["region"], b["start_time"])


def test_scores_fit_the_chart_scale(optimizer):
    res = optimizer.find_best_placement(10000, 5, WEIGHTS, True)
    scores = [o["score"] for o in res["all_options"]]
    assert 20 <= min(scores) and max(scores) <= 100
    assert res["recommended"]["score"] == min(scores)


def test_confidence_is_reported(optimizer):
    meta = optimizer.find_best_placement(10000, 5, WEIGHTS, True)["meta"]
    assert 0 <= meta["confidence"] <= 1
    assert meta["confidence_label"] in {"High", "Medium", "Low"}