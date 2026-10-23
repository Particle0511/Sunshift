import hashlib
import math

import numpy as np
import pandas as pd

from src.config import (REGIONS, DEFAULT_N_GPUS, MAX_SEARCH_HOURS, DEADLINE_BUFFER_FRAC,
                        MIN_DEADLINE_BUFFER_H, N_SCENARIOS, RISK_AVERSION, CONFIDENCE_EPS,
                        MAX_GPU_HOURS, MAX_DEADLINE_DAYS, now_ist)
from src.core.physics import PhysicsEngine
from src.models.forecaster import ClimateForecaster

HOUR = pd.Timedelta(hours=1)


class WorkloadOptimizer:
    def __init__(self):
        self.physics = PhysicsEngine()
        self.forecaster = ClimateForecaster()

   
    @staticmethod
    def _plan_job(gpu_hours, deadline_days, is_flexible, n_gpus):
        deadline_h = max(1, int(round(float(deadline_days) * 24)))
        buffer_h = max(MIN_DEADLINE_BUFFER_H, int(round(DEADLINE_BUFFER_FRAC * deadline_h)))
        usable_h = max(1, deadline_h - buffer_h)

        n_gpus = int(n_gpus or DEFAULT_N_GPUS)
        duration_h = max(1, math.ceil(gpu_hours / n_gpus))
        scaled = False
        if duration_h > usable_h:            # cluster too small for the deadline -> assume more GPUs
            n_gpus = math.ceil(gpu_hours / usable_h)
            duration_h = max(1, math.ceil(gpu_hours / n_gpus))
            scaled = True

        last_start = deadline_h - buffer_h - duration_h
        window = 1 if (not is_flexible or last_start < 0) else min(MAX_SEARCH_HOURS, last_start + 1)
        return {"deadline_h": deadline_h, "buffer_h": buffer_h, "n_gpus": n_gpus,
                "duration_h": duration_h, "window": window, "n_gpus_scaled": scaled}

    @staticmethod
    def _normalise_weights(weights):
        w = np.array([max(0.0, float(weights.get(k, 0))) for k in ("cost", "carbon", "water")])
        return w / w.sum() if w.sum() > 0 else np.full(3, 1 / 3)

    @staticmethod
    def _cumsum0(x):
        return np.concatenate([np.zeros((x.shape[0], 1)), np.cumsum(x, axis=1)], axis=1)

  
    def find_best_placement(self, gpu_hours: float, deadline_days: int, weights: dict,
                            is_flexible: bool, usual_region: str = "Mumbai",
                            n_gpus: int = None, n_scenarios: int = None,
                            seed: int = None, now=None) -> dict:
        try:
            gpu_hours, deadline_days = float(gpu_hours), float(deadline_days)
        except (TypeError, ValueError):
            raise ValueError("gpu_hours and deadline_days must be numbers")
        if not (math.isfinite(gpu_hours) and gpu_hours > 0):
            raise ValueError("gpu_hours must be a positive number")
        if not (math.isfinite(deadline_days) and deadline_days > 0):
            raise ValueError("deadline_days must be a positive number")
        inputs_capped = gpu_hours > MAX_GPU_HOURS or deadline_days > MAX_DEADLINE_DAYS
        gpu_hours, deadline_days = min(gpu_hours, MAX_GPU_HOURS), min(deadline_days, MAX_DEADLINE_DAYS)
        if deadline_days == int(deadline_days):
            deadline_days = int(deadline_days)

        now = pd.Timestamp(now or now_ist()).replace(minute=0, second=0, microsecond=0)
        plan = self._plan_job(gpu_hours, deadline_days, is_flexible, n_gpus)
        D, W = plan["duration_h"], plan["window"]
        need = W - 1 + D                                   # forecast hours required
        w = self._normalise_weights(weights)
        S = N_SCENARIOS if n_scenarios is None else int(n_scenarios)
        if usual_region not in REGIONS:
            usual_region = next(iter(REGIONS))
        if seed is None:
            key = f"{gpu_hours}|{deadline_days}|{is_flexible}|{w.round(4).tolist()}|{now:%Y%m%d%H}"
            seed = int(hashlib.md5(key.encode()).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)

        regions = list(REGIONS)
        day_idx = (np.arange(need) + now.hour) // 24
        n_days = int(day_idx.max()) + 1

        cost, carbon, water, energy = [], [], [], []
        solar_pct, peak_pct, avg_temp, ml_share = [], [], [], []
        for region in regions:
            f = self.forecaster.get_forecast(region, hours_ahead=need, now=now)
            hours = f["time"].dt.hour.to_numpy()
            t0, s0 = f["temperature"].to_numpy(), f["solar_radiation"].to_numpy()
            sig_t, sig_s = f["sigma_temp"].to_numpy(), f["sigma_solar"].to_numpy()
            ml_share.append(float((f["source"] == "ml").mean()))

           
            eps_t = 0.85 * rng.standard_normal((S, n_days))[:, day_idx] + 0.35 * rng.standard_normal((S, need))
            eps_s = 0.85 * rng.standard_normal((S, n_days))[:, day_idx] + 0.35 * rng.standard_normal((S, need))
            temps = np.vstack([t0, t0 + eps_t * sig_t])
            sols = np.clip(np.vstack([s0, s0 + eps_s * sig_s]), 0.0, None)

            p = self.physics.hourly_profile(region, hours, temps, sols, plan["n_gpus"])
            cs = {k: self._cumsum0(p[k]) for k in ("cost", "carbon", "water", "kwh")}
            win = lambda a: a[:, D:D + W] - a[:, :W]       # job total for every start hour
            cost.append(win(cs["cost"])); carbon.append(win(cs["carbon"]))
            water.append(win(cs["water"])); energy.append(win(cs["kwh"]))

            c1 = np.concatenate([[0], np.cumsum(p["is_solar"])])
            c2 = np.concatenate([[0], np.cumsum(p["is_peak"])])
            solar_pct.append((c1[D:D + W] - c1[:W]) / D * 100)
            peak_pct.append((c2[D:D + W] - c2[:W]) / D * 100)
            ct = np.concatenate([[0], np.cumsum(t0)])
            avg_temp.append((ct[D:D + W] - ct[:W]) / D)

        M = {"cost": np.stack(cost, 1), "carbon": np.stack(carbon, 1), "water": np.stack(water, 1)}  # (S+1, R, W)
        kwh = np.stack(energy, 1)


        score = 0.0
        for wi, k in zip(w, ("cost", "carbon", "water")):
            base = M[k][0]
            lo, span = base.min(), base.max() - base.min()
            score = score + wi * (M[k] - lo) / (span if span > 1e-9 else 1.0)
        sc = score[1:] if S > 0 else score[:1]
        robust = sc.mean(axis=0) + RISK_AVERSION * sc.std(axis=0)           # (R, W)

        wr, ww = np.unravel_index(int(np.argmin(robust)), robust.shape)
        best_each = sc.reshape(sc.shape[0], -1).min(axis=1)
        confidence = float(np.mean((sc[:, wr, ww] - best_each) <= CONFIDENCE_EPS))
        label = "High" if confidence >= 0.8 else "Medium" if confidence >= 0.5 else "Low"

        disp = 20 + 80 * np.clip(robust, 0, 1)    
        emissions = self.physics.emissions
        rows = []
        for r, region in enumerate(regions):
            for i in range(W):
                start = now + i * HOUR
                end = start + D * HOUR
                kw = float(kwh[0, r, i])
                rows.append({
                    "region": region,
                    "start_time": start.strftime("%Y-%m-%d %H:00"),
                    "finish_time": end.strftime("%Y-%m-%d %H:00"),
                    "hours_from_now": i,
                    "finish_day": int(math.ceil((i + D) / 24)),
                    "cost_inr": round(float(M["cost"][0, r, i]), 2),
                    "carbon_kg": round(float(M["carbon"][0, r, i]), 2),
                    "water_liters": round(float(M["water"][0, r, i]), 2),
                    "energy_kwh": round(kw, 1),
                    "avg_rate": round(float(M["cost"][0, r, i]) / kw, 2),
                    "solar_hours_pct": round(float(solar_pct[r][i]), 1),
                    "peak_hours_pct": round(float(peak_pct[r][i]), 1),
                    "avg_temp": round(float(avg_temp[r][i]), 1),
                    "grid_factor": emissions[region],
                    "score": round(float(disp[r, i]), 1),
                    "score_raw": round(float(robust[r, i]), 4),
                })

        index = {(row["region"], row["hours_from_now"]): row for row in rows}
        best = dict(index[(regions[wr], int(ww))])
        best["confidence"] = round(confidence, 2)
        best["confidence_label"] = label
        usual = dict(index[(usual_region, 0)])

        meta = {
            "deadline_days": deadline_days, "deadline_hours": plan["deadline_h"],
            "duration_hours": D, "n_gpus": plan["n_gpus"], "n_gpus_scaled": plan["n_gpus_scaled"],
            "search_window_hours": W, "n_scenarios": S, "confidence": round(confidence, 2),
            "confidence_label": label, "finish_day": best["finish_day"],
            "deadline_met": best["hours_from_now"] + D <= plan["deadline_h"],
            "ml_hours_share": round(float(np.mean(ml_share)), 2),
            "inputs_capped": inputs_capped,
            "usual_region": usual_region, "weights": dict(zip(("cost", "carbon", "water"), w.round(3).tolist())),
        }
        return {"recommended": best, "usual": usual, "all_options": rows, "meta": meta}


if __name__ == "__main__":
    optimizer = WorkloadOptimizer()
    scenarios = {
        "Balanced (70/80/60)": {"cost": 0.7, "carbon": 0.8, "water": 0.6},
        "Money only": {"cost": 1, "carbon": 0, "water": 0},
        "Carbon only": {"cost": 0, "carbon": 1, "water": 0},
        "Water only": {"cost": 0, "carbon": 0, "water": 1},
    }
    for name, wts in scenarios.items():
        res = optimizer.find_best_placement(10000, 5, wts, is_flexible=True)
        u, r, m = res["usual"], res["recommended"], res["meta"]
        print(f"\n[{name}] -> {r['region']} at {r['start_time']}  (finishes day {r['finish_day']} of {m['deadline_days']}, "
              f"confidence {m['confidence_label']} {m['confidence']:.0%})")
        print(f"   usual   {u['region']:<10} Rs {u['cost_inr']:>10,.0f} | {u['carbon_kg']:>7,.0f} kg | {u['water_liters']:>8,.0f} L")
        print(f"   chosen  {r['region']:<10} Rs {r['cost_inr']:>10,.0f} | {r['carbon_kg']:>7,.0f} kg | {r['water_liters']:>8,.0f} L")