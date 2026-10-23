from datetime import datetime
import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.multioutput import MultiOutputRegressor
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from src.config import CACHE_DIR, MODEL_DIR, REGIONS, MAX_HORIZON_HOURS, now_ist
from src.models.forecaster import FEATURES, NUM_FEATURES, build_features, contiguous_tail, load_hourly

EDGES = [24, 48, 72, 120, 168]
ORIGIN_START = 168
ORIGIN_STRIDE = 5
MAX_ROWS_PER_REGION = 60_000
MIN_TEMP_SIGMA, MIN_SOLAR_SIGMA = 0.4, 15.0
Y = ["y_temperature", "y_solar"]

CONFIGS = [
    dict(loss="absolute_error", max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=40, l2_regularization=1.0),
    dict(loss="absolute_error", max_iter=400, learning_rate=0.04, max_leaf_nodes=15, min_samples_leaf=100, l2_regularization=3.0),
    dict(loss="absolute_error", max_iter=250, learning_rate=0.08, max_leaf_nodes=63, min_samples_leaf=20, l2_regularization=0.5),
]

class ClimateForecasterTrainer:
    def __init__(self):
        self.model_path = MODEL_DIR / "climate_forecaster.joblib"
        self.rng = np.random.default_rng(42)

    def _series(self, region: str) -> pd.DataFrame:
        frames = []
        hist_path = CACHE_DIR / f"{region}_history.csv"
        if hist_path.exists():
            frames.append(load_hourly(hist_path))
        recent = load_hourly(CACHE_DIR / f"{region}_weather.csv")
        recent = recent[recent.index <= now_ist()]
        if frames:
            recent = recent[recent.index > frames[0].index[-1]]
            frames.append(recent)
        df = pd.concat(frames)
        df = df[~df.index.duplicated(keep="first")].sort_index()
        return contiguous_tail(df)

    def _samples(self, region: str, df: pd.DataFrame) -> pd.DataFrame:
        T = df["temperature"].to_numpy(float)
        S = df["solar_radiation"].to_numpy(float)
        n = len(df)
        if n < ORIGIN_START + 200:
            raise RuntimeError(f"Not enough weather rows for {region} ({n}). Run: python -m src.weather_client")
        origins = np.arange(ORIGIN_START, n - 2, ORIGIN_STRIDE)
        per = int(np.clip(MAX_ROWS_PER_REGION // max(len(origins), 1), 24, MAX_HORIZON_HOURS))
        o = np.repeat(origins, per)
        max_h = np.minimum(MAX_HORIZON_HOURS, n - 1 - o)
        h = 1 + np.floor(self.rng.random(len(o)) * max_h).astype(int)
        feats, target_time = build_features(region, T, S, df.index, o, h)
        origin_time = df.index[o]
        feats["origin_time"] = origin_time
        feats["target_time"] = target_time
        feats["y_temperature"] = T[o + h]
        feats["y_solar"] = S[o + h]
        c1 = df.index[int(n * 0.70)]
        c2 = df.index[int(n * 0.85)]
        gap = pd.Timedelta(hours=MAX_HORIZON_HOURS)
        ot = np.asarray(origin_time)
        feats["split"] = np.where(ot < np.datetime64(c1 - gap), "train",
                         np.where((ot >= np.datetime64(c1)) & (ot < np.datetime64(c2 - gap)), "val",
                         np.where(ot >= np.datetime64(c2), "test", "drop")))
        return feats

    def load_samples(self) -> pd.DataFrame:
        parts = []
        for region in REGIONS:
            df = self._series(region)
            print(f"  {region:<10} {len(df):>6} hourly rows ({df.index[0]:%Y-%m-%d} -> {df.index[-1]:%Y-%m-%d})")
            parts.append(self._samples(region, df))
        return pd.concat(parts, ignore_index=True)

    def build_pipeline(self, params: dict) -> Pipeline:
        pre = ColumnTransformer([
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False), ["region"]),
            ("num", "passthrough", NUM_FEATURES),
        ])
        base = HistGradientBoostingRegressor(early_stopping=False, random_state=42, **params)
        return Pipeline([("pre", pre), ("reg", MultiOutputRegressor(base))])

    @staticmethod
    def _bucket(h):
        return np.searchsorted(np.asarray(EDGES), np.clip(h, 1, EDGES[-1]), side="left")

    @staticmethod
    def _baselines(train, df):
        tr = train.assign(hr=train["target_time"].dt.hour)
        clim = tr.groupby(["region", "hr"])[Y].mean()
        mi = pd.MultiIndex.from_arrays([df["region"], df["target_time"].dt.hour])
        clim_pred = clim.reindex(mi).to_numpy()
        pers_pred = df[["t_same_hour", "s_same_hour"]].to_numpy()
        return pers_pred, clim_pred

    def _predict(self, pipe, df):
        pred = pipe.predict(df[FEATURES])
        pred[:, 1] = np.clip(pred[:, 1], 0, None)
        hr = df["target_time"].dt.hour.to_numpy()
        is_night = (hr < 6) | (hr >= 19)
        pred[is_night, 1] = 0.0
        return pred

    def _apply_routing(self, pipe, df, train, routing):
        pred = self._predict(pipe, df)
        pers, clim = self._baselines(train, df)
        bucket = self._bucket(df["horizon"].to_numpy())
        for b in range(len(EDGES)):
            m = bucket == b
            if not m.any(): continue
            if routing["temperature"][b] == "pers":
                pred[m, 0] = pers[m, 0]
            elif routing["temperature"][b] == "clim":
                pred[m, 0] = clim[m, 0]
            if routing["solar"][b] == "pers":
                pred[m, 1] = pers[m, 1]
            elif routing["solar"][b] == "clim":
                pred[m, 1] = clim[m, 1]
        return pred

    def _build_routing(self, pipe, train, eval_data):
        y, pred = eval_data[Y].to_numpy(), self._predict(pipe, eval_data)
        pers, clim = self._baselines(train, eval_data)
        bucket = self._bucket(eval_data["horizon"].to_numpy())
        routing = {"temperature": [], "solar": []}
        for b in range(len(EDGES)):
            m = bucket == b
            if m.sum() < 30:
                routing["temperature"].append("model")
                routing["solar"].append("model")
                continue
            errs_t = {"model": mean_absolute_error(y[m, 0], pred[m, 0]),
                      "pers": mean_absolute_error(y[m, 0], pers[m, 0]),
                      "clim": mean_absolute_error(y[m, 0], clim[m, 0])}
            routing["temperature"].append(min(errs_t, key=errs_t.get))
            errs_s = {"model": mean_absolute_error(y[m, 1], pred[m, 1]),
                      "pers": mean_absolute_error(y[m, 1], pers[m, 1]),
                      "clim": mean_absolute_error(y[m, 1], clim[m, 1])}
            routing["solar"].append(min(errs_s, key=errs_s.get))
        return routing

    def _relative_error(self, pipe, train, df):
        y, pred = df[Y].to_numpy(), self._predict(pipe, df)
        pers, clim = self._baselines(train, df)
        ratios = []
        for j in range(2):
            base = min(mean_absolute_error(y[:, j], pers[:, j]), mean_absolute_error(y[:, j], clim[:, j]))
            ratios.append(mean_absolute_error(y[:, j], pred[:, j]) / max(base, 1e-9))
        return float(np.mean(ratios))

    def _report_and_sigma(self, pipe, train, report_df, sigma_df, routing):
        y = report_df[Y].to_numpy()
        pred_ml = self._predict(pipe, report_df)
        pred_routed = self._apply_routing(pipe, report_df, train, routing)
        pers, clim = self._baselines(train, report_df)
        bucket = self._bucket(report_df["horizon"].to_numpy())
        names = ["temperature", "solar"]
        print("\n Held-out TEST MAE by horizon: routed | ml_only | yesterday | climatology")
        for b, edge in enumerate(EDGES):
            m = bucket == b
            if m.sum() < 30:
                continue
            line = f" <= {edge:>3}h (n={m.sum():>6}) "
            for j, nm in enumerate(names):
                line += (f" | {nm[:5]} {mean_absolute_error(y[m, j], pred_routed[m, j]):6.2f}"
                         f" {mean_absolute_error(y[m, j], pred_ml[m, j]):6.2f}"
                         f" {mean_absolute_error(y[m, j], pers[m, j]):6.2f}"
                         f" {mean_absolute_error(y[m, j], clim[m, j]):6.2f}")
            print(line)
        overall = {}
        for j, nm in enumerate(names):
            mae = mean_absolute_error(y[:, j], pred_routed[:, j])
            base = min(mean_absolute_error(y[:, j], pers[:, j]), mean_absolute_error(y[:, j], clim[:, j]))
            overall[nm] = {"mae": float(mae), "best_baseline_mae": float(base), "skill": float(1 - mae / base)}
            flag = "" if mae <= base + 0.01 else " <-- WARNING: not better than a simple baseline"
            print(f"  {nm:<12} ROUTED MAE {mae:.2f} vs best baseline {base:.2f} -> skill {100 * (1 - mae / base):+.0f}%{flag}")
        ys, ps = sigma_df[Y].to_numpy(), self._apply_routing(pipe, sigma_df, train, routing)
        sb = self._bucket(sigma_df["horizon"].to_numpy())
        floors = [MIN_TEMP_SIGMA, MIN_SOLAR_SIGMA]
        keys = ["temperature", "solar_radiation"]
        def table(mask):
            out = {}
            for j, key in enumerate(keys):
                allm = float(np.sqrt(np.mean((ys[mask, j] - ps[mask, j]) ** 2)))
                vals = []
                for b in range(len(EDGES)):
                    m = mask & (sb == b)
                    vals.append(float(np.sqrt(np.mean((ys[m, j] - ps[m, j]) ** 2))) if m.sum() >= 30 else allm)
                out[key] = np.maximum.accumulate(np.maximum(vals, floors[j])).tolist()
            return out
        everything = np.ones(len(sigma_df), dtype=bool)
        sigma = {"edges": EDGES, "global": table(everything), "regions": {}}
        reg = sigma_df["region"].to_numpy()
        for region in REGIONS:
            m = reg == region
            if m.sum() >= 100:
                sigma["regions"][region] = table(m)
        return sigma, overall

    def train_and_evaluate(self):
        print("Loading weather data and building multi-horizon samples...")
        data = self.load_samples()
        train, val, test = (data[data.split == s] for s in ("train", "val", "test"))
        print(f"\nSamples: train {len(train):,} | validation {len(val):,} | test {len(test):,}")
        if len(val) < 500 or len(test) < 500:
            print("  (little data: skipping the settings search, using the default setting)")
            configs, val = CONFIGS[:1], test
        else:
            configs = CONFIGS
        best = None
        print("\nTrying model settings (lower validation error is better; < 1.00 beats the baselines):")
        for i, params in enumerate(configs, 1):
            pipe = self.build_pipeline(params)
            pipe.fit(train[FEATURES], train[Y])
            score = self._relative_error(pipe, train, val)
            print(f"  setting {i}: {params} -> {score:.3f}")
            if best is None or score < best[0]:
                best = (score, params, pipe)
        print(f"  using setting with validation error {best[0]:.3f}")
        print("\nSelecting optimal forecasting method per horizon (ML vs baselines)...")
        routing = self._build_routing(best[2], train, val)
        print("Routing table:", routing)
        sigma_df = pd.concat([val, test]) if len(test) else val
        sigma, overall = self._report_and_sigma(best[2], train, test if len(test) else val, sigma_df, routing)
        print("\nRefitting the chosen setting on all data for production...")
        final = self.build_pipeline(best[1])
        final.fit(data[FEATURES], data[Y])
        clim = data.assign(hr=data["target_time"].dt.hour).groupby(["region", "hr"])[Y].mean()
        clim_means = clim.to_dict("index")
        artifact = {
            "pipeline": final, "features": FEATURES, "max_horizon": MAX_HORIZON_HOURS,
            "residual_std": sigma, "metrics": overall, "params": best[1],
            "routing": routing, "clim_means": clim_means,
            "trained_at": datetime.now().isoformat(timespec="seconds"),
        }
        joblib.dump(artifact, self.model_path)
        print(f"Saved model to: {self.model_path}")

if __name__ == "__main__":
    ClimateForecasterTrainer().train_and_evaluate()