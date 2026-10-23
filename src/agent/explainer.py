import hashlib
import re
import time
from datetime import datetime

import requests

from src.config import REGIONS
from src.formatting import describe_start, indian_number, inr

NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")
CONTRAST_RE = re.compile(r"\b(but|however|though|although|while|whereas|trade-?off|at the cost)\b", re.I)


class ReasonExplainer:
   

    def __init__(self, model: str = "phi3", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_url = f"{self.base_url}/api/generate"
        self._ready = (0.0, False)

    #  facts
    def _build_facts(self, usual: dict, rec: dict, weights=None, meta=None) -> dict:
        try:
            start_dt = datetime.strptime(rec["start_time"], "%Y-%m-%d %H:%M")
            when = describe_start(start_dt)
        except Exception:
            when = "at the recommended time"

        same_plan = (rec["region"] == usual["region"] and rec["start_time"] == usual["start_time"])
        gains, tradeoffs = [], []
        specs = [
            ("money", "cost_inr", lambda v: f"saves {inr(v)} in electricity", lambda v: f"costs {inr(v)} more"),
            ("carbon", "carbon_kg", lambda v: f"cuts {indian_number(v)} kg of carbon", lambda v: f"emits {indian_number(v)} kg more carbon"),
            ("water", "water_liters", lambda v: f"uses {indian_number(v)} L less cooling water", lambda v: f"uses {indian_number(v)} L more cooling water"),
        ]
        for name, key, gain_txt, loss_txt in specs:
            u, r = float(usual[key]), float(rec[key])
            if u <= 0:
                continue
            saved = u - r
            if saved / u >= 0.01:
                gains.append((name, gain_txt(saved)))
            elif saved / u <= -0.01:
                tradeoffs.append((name, loss_txt(-saved)))

        drivers = []
        g = lambda d, k: d.get(k)
        if g(rec, "solar_hours_pct") is not None and g(usual, "solar_hours_pct") is not None:
            if rec["solar_hours_pct"] - usual["solar_hours_pct"] >= 15:
                drivers.append(f"{rec['solar_hours_pct']:.0f}% of the run falls in cheaper solar-tariff hours versus {usual['solar_hours_pct']:.0f}% on the usual plan")
            if usual["peak_hours_pct"] - rec["peak_hours_pct"] >= 10:
                drivers.append(f"it avoids the evening peak ({rec['peak_hours_pct']:.0f}% of the run versus {usual['peak_hours_pct']:.0f}%)")
            if usual["avg_rate"] - rec["avg_rate"] >= 0.3:
                drivers.append(f"the average power rate is ₹{rec['avg_rate']:.1f} per kWh versus ₹{usual['avg_rate']:.1f}")
        if g(rec, "grid_factor") and g(usual, "grid_factor") and usual["grid_factor"] - rec["grid_factor"] >= 0.02 \
                and rec["region"] != usual["region"]:
            drivers.append(f"{rec['region']}'s grid emits {rec['grid_factor']:.2f} kg CO₂ per kWh versus {usual['grid_factor']:.2f}")
        drivers = drivers[:2]

        finish = ""
        if meta and meta.get("finish_day"):
            finish = f"finishes on day {meta['finish_day']} of {meta['deadline_days']}"
            if meta.get("deadline_met"):
                finish += ", so the deadline is met"

        priority = None
        if weights:
            top = max(weights, key=lambda k: weights[k])
            priority = {"cost": "saving money", "carbon": "cutting carbon", "water": "protecting water"}.get(top)

        seed_src = f"{rec['region']}|{rec['start_time']}|{usual['region']}|{rec['cost_inr']}|{rec['carbon_kg']}"
        facts = {
            "where": rec["region"], "usual_where": usual["region"], "when": when,
            "same_plan": same_plan, "gains": gains, "tradeoffs": tradeoffs,
            "drivers": drivers, "finish": finish, "priority": priority,
            "seed": int(hashlib.md5(seed_src.encode()).hexdigest()[:8], 16),
        }
        text_blob = " ".join([when, finish] + drivers + [t for _, t in gains] + [t for _, t in tradeoffs])
        facts["numbers"] = {n.replace(",", "") for n in NUM_RE.findall(text_blob)}
        return facts

    # template
    def _template(self, f: dict) -> str:
        if f["same_plan"] or (not f["gains"] and not f["tradeoffs"] and f["where"] == f["usual_where"]):
            return (f"The usual plan in {f['usual_where']} is already the best fit for your priorities, "
                    f"so no change is recommended.")

        gains = [t for _, t in f["gains"]]
        if not gains and not f["tradeoffs"]:
            effect = "keeps cost, carbon and water close to the usual plan"
        elif gains:
            effect = gains[0] if len(gains) == 1 else ", ".join(gains[:-1]) + " and " + gains[-1]
        else:
            effect = "improves the overall balance"
        if f["tradeoffs"]:
            trade = [t for _, t in f["tradeoffs"]]
            effect += ", though it " + (trade[0] if len(trade) == 1 else " and ".join(trade))

        place = f"{f['where']} {f['when']}"
        variant = f["seed"] % 3
        if variant == 0:
            first = f"Running the job in {place} {effect}."
        elif variant == 1:
            first = f"Compared with the usual plan in {f['usual_where']}, running in {place} {effect}."
        else:
            first = f"{place[0].upper() + place[1:]} is the better slot: it {effect}."

        second = ""
        if f["drivers"]:
            second = " This works because " + " and ".join(f["drivers"]) + "."
        if f["finish"]:
            second += f" The job {f['finish']}."
        return first + second

    #  LLM
    def _ollama_ready(self) -> bool:
        checked, ok = self._ready
        if time.time() - checked < 30:
            return ok
        try:
            tags = requests.get(f"{self.base_url}/api/tags", timeout=1.5).json()
            ok = any(m.get("name", "").startswith(self.model) for m in tags.get("models", []))
        except Exception:
            ok = False
        self._ready = (time.time(), ok)
        return ok

    def _build_prompt(self, f: dict) -> str:
        lines = [f"- Recommendation: run the job in {f['where']} {f['when']} instead of starting in {f['usual_where']} now."]
        lines += [f"- Benefit: it {t}." for _, t in f["gains"]]
        lines += [f"- Trade-off (must be mentioned): it {t}." for _, t in f["tradeoffs"]]
        lines += [f"- Reason: {d}." for d in f["drivers"]]
        if f["finish"]:
            lines.append(f"- Timing: the job {f['finish']}.")
        if f["priority"]:
            lines.append(f"- The user cares most about {f['priority']}.")
        facts = "\n".join(lines)
        return (
            "You write a short explanation for a cloud scheduling app.\n"
            "Rules: use ONLY the facts below. Never add a number, city or claim that is not listed. "
            "Write 1 or 2 plain sentences, at most 45 words, no lists, no quotes. "
            "Say estimated, never guaranteed.\n\n"
            "Example facts:\n- Recommendation: run the job in Chennai on Friday at 11 AM instead of starting in Delhi NCR now.\n"
            "- Benefit: it saves ₹9,000 in electricity.\n- Trade-off (must be mentioned): it uses 400 L more cooling water.\n"
            "Example answer: Starting in Chennai on Friday at 11 AM saves an estimated ₹9,000 in electricity, "
            "though it uses 400 L more cooling water.\n\n"
            f"Facts:\n{facts}\nAnswer:"
        )

    def _ask_llm(self, f: dict):
        payload = {
            "model": self.model, "prompt": self._build_prompt(f), "stream": False, "keep_alive": "15m",
            "options": {"temperature": 0.3, "top_p": 0.9, "seed": f["seed"] % 2_147_483_647,
                        "num_predict": 100, "stop": ["\n\n", "Facts:", "Example"]},
        }
        try:
            resp = requests.post(self.api_url, json=payload, timeout=(3, 90))
            resp.raise_for_status()
            return self._clean(resp.json().get("response", ""))
        except Exception:
            return None

    @staticmethod
    def _clean(text: str) -> str:
        text = text.strip().split("\n\n")[0]
        text = re.sub(r"^(answer|sentence|explanation)\s*:\s*", "", text, flags=re.I)
        text = re.sub(r"[*#`_\"“”]", "", text)
        text = re.sub(r"\s+", " ", text).strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        text = " ".join(sentences[:2]).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text

    def _is_grounded(self, text: str, f: dict) -> bool:
        words = text.split()
        if not (8 <= len(words) <= 60):
            return False
        if any(n.replace(",", "") not in f["numbers"] for n in NUM_RE.findall(text)):
            return False
        low = text.lower()
        if f["where"].lower() not in low:
            return False
        allowed = {f["where"].lower(), f["usual_where"].lower()}
        for city in REGIONS:
            token = city.lower()
            if token in low and token not in allowed:
                return False
        if f["tradeoffs"] and not CONTRAST_RE.search(text):
            return False
        if "guarantee" in low:
            return False
        return True

    
    def generate_reason(self, usual: dict, recommended: dict, weights=None, meta=None) -> str:
        facts = self._build_facts(usual, recommended, weights, meta)
        if self._ollama_ready():
            text = self._ask_llm(facts)
            if text and self._is_grounded(text, facts):
                return text
        return self._template(facts)


if __name__ == "__main__":
    explainer = ReasonExplainer()
    mock_usual = {"region": "Mumbai", "start_time": "2026-10-22 19:00", "cost_inr": 480000, "carbon_kg": 5900,
                  "water_liters": 38000, "solar_hours_pct": 0, "peak_hours_pct": 8, "avg_rate": 9.4, "grid_factor": 0.71}
    mock_rec = {"region": "Hyderabad", "start_time": "2026-10-23 10:00", "cost_inr": 365000, "carbon_kg": 4100,
                "water_liters": 23500, "solar_hours_pct": 40, "peak_hours_pct": 0, "avg_rate": 7.1, "grid_factor": 0.68}
    meta = {"finish_day": 3, "deadline_days": 5, "deadline_met": True}
    print(explainer.generate_reason(mock_usual, mock_rec, {"cost": .7, "carbon": .8, "water": .6}, meta))