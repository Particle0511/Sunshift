from src.agent.explainer import ReasonExplainer

USUAL = {"region": "Mumbai", "start_time": "2026-10-22 19:00", "cost_inr": 480000, "carbon_kg": 5900,
         "water_liters": 38000, "solar_hours_pct": 0, "peak_hours_pct": 8, "avg_rate": 9.4, "grid_factor": 0.71}
REC = {"region": "Hyderabad", "start_time": "2026-10-23 10:00", "cost_inr": 365000, "carbon_kg": 4100,
       "water_liters": 23500, "solar_hours_pct": 40, "peak_hours_pct": 0, "avg_rate": 7.1, "grid_factor": 0.68}
META = {"finish_day": 3, "deadline_days": 5, "deadline_met": True}


def make(monkeypatch, llm_text):
    ex = ReasonExplainer()
    monkeypatch.setattr(ex, "_ollama_ready", lambda: True)
    monkeypatch.setattr(ex, "_ask_llm", lambda facts: llm_text)
    return ex


def test_template_when_ollama_is_down(monkeypatch):
    ex = ReasonExplainer()
    monkeypatch.setattr(ex, "_ollama_ready", lambda: False)
    text = ex.generate_reason(USUAL, REC, meta=META)
    assert "Hyderabad" in text and "1,15,000" in text


def test_good_llm_answer_is_used(monkeypatch):
    good = "Hyderabad tomorrow at 10 AM saves an estimated ₹1,15,000 and cuts 1,800 kg of carbon."
    assert make(monkeypatch, good).generate_reason(USUAL, REC, meta=META) == good


def test_invented_number_is_rejected(monkeypatch):
    bad = "Hyderabad tomorrow at 10 AM saves ₹2,50,000 and cuts 1,800 kg of carbon."
    out = make(monkeypatch, bad).generate_reason(USUAL, REC, meta=META)
    assert "2,50,000" not in out and "1,15,000" in out


def test_other_city_is_rejected(monkeypatch):
    bad = "Hyderabad tomorrow at 10 AM saves ₹1,15,000, far better than Chennai."
    assert "Chennai" not in make(monkeypatch, bad).generate_reason(USUAL, REC, meta=META)


def test_tradeoff_must_be_disclosed(monkeypatch):
    rec = dict(REC, water_liters=45000)          # water gets worse
    hidden = "Hyderabad tomorrow at 10 AM saves an estimated ₹1,15,000 and cuts 1,800 kg of carbon."
    out = make(monkeypatch, hidden).generate_reason(USUAL, rec, meta=META)
    assert "more cooling water" in out


def test_guarantee_is_rejected(monkeypatch):
    bad = "Hyderabad tomorrow at 10 AM is guaranteed to save ₹1,15,000 for you."
    assert "guaranteed" not in make(monkeypatch, bad).generate_reason(USUAL, REC, meta=META)