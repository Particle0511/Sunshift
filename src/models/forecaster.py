
import joblib
import numpy as np
import pandas as pd

from src.config import MODEL_DIR, CACHE_DIR, MAX_HORIZON_HOURS, now_ist

HOUR = pd.Timedelta(hours=1)
TARGETS = ["temperature", "solar_radiation"]
NUM_FEATURES = [
    "hour_sin", "hour_cos", "doy_sin", "doy_cos", "horizon",
    "t_last", "t_mean_24h", "t_max_24h", "t_min_24h",
    "s_mean_24h", "s_max_24h", "t_same_hour", "s_same_hour",
    "t_same_hour_2d", "s_same_hour_2d", "t_mean_7d",
]
FEATURES = ["region"] + NUM_FEATURES
API_TRUST = 0.6   # a numerical weather forecast is tighter than our ML residuals


def contiguous_tail(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only the last gap-free hourly block (feature maths needs a regular grid)."""
    if len(df) < 2:
        return df
    gaps = np.where(np.diff(df.index.values) != np.timedelta64(1, "h"))[0]
    return df.iloc[gaps[-1] + 1:] if len(gaps) else df


def load_hourly(path) -> pd.DataFrame:
    raw = pd.read_csv(path, parse_dates=["time"])
    raw = (raw.dropna(subset=["time"]).drop_duplicates("time")
              .sort_values("time").set_index("time"))[TARGETS]
    full = pd.date_range(raw.index[0], raw.index[-1], freq=HOUR)
    raw = raw.reindex(full).interpolate(limit=6, limit_area="inside")
    raw.index.name = "time"
    return contiguous_tail(raw.dropna())


def build_features(region, T, S, times, origin_idx, horizons):
    ts, ss = pd.Series(T), pd.Series(S)
    t_mean = ts.rolling(24).mean().to_numpy()
    t_max = ts.rolling(24).max().to_numpy()
    t_min = ts.rolling(24).min().to_numpy()
    s_mean = ss.rolling(24).mean().to_numpy()
    s_max = ss.rolling(24).max().to_numpy()
    t_mean7 = ts.rolling(168).mean().to_numpy()

    o = np.asarray(origin_idx, dtype=int)
    h = np.asarray(horizons, dtype=int)
    target_time = pd.DatetimeIndex(times[o]) + pd.to_timedelta(h, unit="h")
    same = o + h - 24 * np.ceil(h / 24.0).astype(int)   # same clock hour, latest observed day
    same2 = same - 24                                   # ... and the day before that

    hour = np.asarray(target_time.hour)
    doy = np.asarray(target_time.dayofyear)
    feats = pd.DataFrame({
        "region": region,
        "hour_sin": np.sin(2 * np.pi * hour / 24.0),
        "hour_cos": np.cos(2 * np.pi * hour / 24.0),
        "doy_sin": np.sin(2 * np.pi * doy / 365.25),
        "doy_cos": np.cos(2 * np.pi * doy / 365.25),
        "horizon": np.minimum(h, MAX_HORIZON_HOURS),
        "t_last": T[o], "t_mean_24h": t_mean[o], "t_max_24h": t_max[o], "t_min_24h": t_min[o],
        "s_mean_24h": s_mean[o], "s_max_24h": s_max[o],
        "t_same_hour": T[same], "s_same_hour": S[same],
        "t_same_hour_2d": T[same2], "s_same_hour_2d": S[same2], "t_mean_7d": t_mean7[o],
    })
    return feats, target_time


class ClimateForecaster:
    def __init__(self):
        self.model_path = MODEL_DIR / "climate_forecaster.joblib"
        if not self.model_path.exists():
            raise FileNotFoundError("Model not found. Run: python -m src.models.train_forecaster")
        artifact = joblib.load(self.model_path)
        if not (isinstance(artifact, dict) and "pipeline" in artifact):
            raise RuntimeError("climate_forecaster.joblib is in the old format. "
                               "Re-train with: python -m src.models.train_forecaster")
        self.artifact = artifact
        self.model = artifact["pipeline"]
        self._sigma = artifact["residual_std"]
        self._cache = {}

    
    def _history(self, region: str) -> pd.DataFrame:
        path = CACHE_DIR / f"{region}_weather.csv"
        if not path.exists():
            raise FileNotFoundError(f"{path} missing. Run: python -m src.weather_client")
        mtime = path.stat().st_mtime
        hit = self._cache.get(region)
        if hit and hit[0] == mtime:
            return hit[1]
        df = load_hourly(path)
        self._cache[region] = (mtime, df)
        return df

    def _lookup_sigma(self, lead_hours, key: str, region: str) -> np.ndarray:
        edges = np.asarray(self._sigma["edges"])
        table = self._sigma["regions"].get(region, self._sigma["global"])
        vals = np.asarray(table[key])
        idx = np.searchsorted(edges, np.clip(lead_hours, 1, edges[-1]), side="left")
        return vals[idx]

   
    def get_forecast(self, region: str, hours_ahead: int = 120, now=None) -> pd.DataFrame:
        now = pd.Timestamp(now or now_ist()).replace(minute=0, second=0, microsecond=0)
        hours_ahead = int(max(1, hours_ahead))
        hist = self._history(region)
        targets = pd.date_range(now, periods=hours_ahead, freq=HOUR)

        api = hist.reindex(targets)
        use_api = (api["temperature"].notna() & api["solar_radiation"].notna()).to_numpy()
        temp = api["temperature"].to_numpy(dtype=float).copy()
        sol = api["solar_radiation"].to_numpy(dtype=float).copy()

        lead = np.arange(1, hours_ahead + 1)
        sig_t = self._lookup_sigma(lead, "temperature", region) * API_TRUST
        sig_s = self._lookup_sigma(lead, "solar_radiation", region) * API_TRUST

        need_ml = ~use_api
        if need_ml.any():
            origin_time = min(now, hist.index[-1])
            pos = int(hist.index.searchsorted(origin_time, side="right") - 1)
            if pos < 168:
                raise RuntimeError(f"Weather cache for {region} is too short. Run: python -m src.weather_client")
            gap = (targets[need_ml] - hist.index[pos]) / HOUR
            h = np.maximum(np.rint(np.asarray(gap, dtype=float)).astype(int), 1)
            feats, _ = build_features(region, hist["temperature"].to_numpy(),
                                      hist["solar_radiation"].to_numpy(), hist.index,
                                      np.full(len(h), pos), h)
            pred = self.model.predict(feats[FEATURES])
            temp[need_ml] = pred[:, 0]
            sol[need_ml] = np.clip(pred[:, 1], 0, None)
            sig_t[need_ml] = self._lookup_sigma(h, "temperature", region)
            sig_s[need_ml] = self._lookup_sigma(h, "solar_radiation", region)

        return pd.DataFrame({
            "time": targets,
            "temperature": np.round(temp, 2),
            "solar_radiation": np.round(np.clip(sol, 0, None), 2),
            "source": np.where(use_api, "open-meteo", "ml"),
            "sigma_temp": np.round(sig_t, 3),
            "sigma_solar": np.round(sig_s, 2),
        })


if __name__ == "__main__":
    forecaster = ClimateForecaster()
    df = forecaster.get_forecast("Mumbai", hours_ahead=96)
    print("--- Forecast snapshot for Mumbai ---")
    print(df.iloc[::8].to_string(index=False))
    print("\nSources:", df["source"].value_counts().to_dict())