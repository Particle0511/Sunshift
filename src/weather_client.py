import time
from datetime import timedelta

import pandas as pd
import requests

from src.config import REGIONS, CACHE_DIR, HISTORY_YEARS, now_ist


class WeatherClient:
    def __init__(self):
        self.forecast_url = "https://api.open-meteo.com/v1/forecast"
        self.archive_url = "https://archive-api.open-meteo.com/v1/archive"

    def _get(self, url: str, params: dict, retries: int = 3) -> dict:
        last_err = None
        for attempt in range(retries):
            try:
                response = requests.get(url, params=params, timeout=60)
                response.raise_for_status()
                return response.json()
            except requests.RequestException as err:
                last_err = err
                time.sleep(2 * (attempt + 1))
        raise last_err

    @staticmethod
    def _to_frame(data: dict) -> pd.DataFrame:
        df = pd.DataFrame(data["hourly"])
        df.rename(columns={"temperature_2m": "temperature",
                           "shortwave_radiation": "solar_radiation"}, inplace=True)
        df["time"] = pd.to_datetime(df["time"])
        return df[["time", "temperature", "solar_radiation"]]

    def fetch_and_cache(self, region: str) -> pd.DataFrame:
        """Last 30 days + the live 5-day forecast (used directly by the optimizer)."""
        coords = REGIONS[region]
        params = {
            "latitude": coords["lat"],
            "longitude": coords["lon"],
            "hourly": "temperature_2m,shortwave_radiation",
            "past_days": 30,
            "forecast_days": 5,
            "timezone": "Asia/Kolkata",
        }
        df = self._to_frame(self._get(self.forecast_url, params))
        df.to_csv(CACHE_DIR / f"{region}_weather.csv", index=False)
        return df

    def fetch_history(self, region: str, years: int = HISTORY_YEARS) -> pd.DataFrame:
        """Several years of hourly history, used only to TRAIN the forecaster (one request per year)."""
        coords = REGIONS[region]
        end = (now_ist() - timedelta(days=6)).date()      
        start = end - timedelta(days=365 * years)
        frames, chunk_start = [], start
        while chunk_start <= end:
            chunk_end = min(chunk_start + timedelta(days=364), end)
            params = {
                "latitude": coords["lat"],
                "longitude": coords["lon"],
                "start_date": chunk_start.isoformat(),
                "end_date": chunk_end.isoformat(),
                "hourly": "temperature_2m,shortwave_radiation",
                "timezone": "Asia/Kolkata",
            }
            frames.append(self._to_frame(self._get(self.archive_url, params)))
            chunk_start = chunk_end + timedelta(days=1)
        df = pd.concat(frames, ignore_index=True).drop_duplicates("time")
        df.to_csv(CACHE_DIR / f"{region}_history.csv", index=False)
        return df


if __name__ == "__main__":
    client = WeatherClient()
    for region in REGIONS:
        print(f"Downloading live forecast for {region}...")
        client.fetch_and_cache(region)
        print(f"Downloading {HISTORY_YEARS}-year history for {region}...")
        try:
            client.fetch_history(region)
        except Exception as err:  
            print(f"  history download failed ({err}); training will use the 30-day cache only")
    print("All weather data cached in data/weather_cache/")