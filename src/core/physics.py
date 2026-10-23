import numpy as np

from src.config import SOLAR_REF_WM2, SOLAR_CARBON_DISCOUNT
from src.data_loader import load_json


class PhysicsEngine:
    def __init__(self):
        self.tariffs = load_json("state_tod_tariffs.json")
        self.water_stress = load_json("wri_water_stress_index.json")
        self.emissions = load_json("cea_grid_emission_factors.json")
        self.KW_PER_GPU = 0.75

  
    def get_tod_multiplier(self, hour: int) -> str:
        if 10 <= hour <= 15:
            return "solar"
        elif 18 <= hour <= 21:
            return "peak"
        return "base"

    def calculate_pue(self, temperature: float) -> float:
        base_pue = 1.2
        if temperature > 22.0:
            return base_pue + (temperature - 22.0) * 0.015
        return base_pue

    def calculate_metrics(self, gpu_hours: float, region: str, start_hour: int, temperature: float) -> dict:
        pue = self.calculate_pue(temperature)
        total_kwh = gpu_hours * self.KW_PER_GPU * pue

        time_slot = self.get_tod_multiplier(start_hour)
        rate = self.tariffs[region][time_slot]
        cost_inr = total_kwh * rate

        base_carbon = self.emissions[region]
        carbon_factor = base_carbon * 0.7 if time_slot == "solar" else base_carbon
        carbon_kg = total_kwh * carbon_factor

        temp_penalty = max(1.0, temperature / 25.0)
        wri_index = self.water_stress[region]
        water_liters = total_kwh * 1.5 * temp_penalty * (wri_index / 3.0)

        return {
            "energy_kwh": round(total_kwh, 2),
            "cost_inr": round(cost_inr, 2),
            "carbon_kg": round(carbon_kg, 2),
            "water_liters": round(water_liters, 2),
            "pue_applied": round(pue, 3),
        }

   
    # Hour-by-hour model used for optimization 
    
    def hourly_profile(self, region: str, hours, temps, solars, n_gpus: float) -> dict:
        
        hours = np.asarray(hours)
        pue = 1.2 + np.maximum(temps - 22.0, 0.0) * 0.015
        kwh = n_gpus * self.KW_PER_GPU * pue

        is_solar = (hours >= 10) & (hours <= 15)
        is_peak = (hours >= 18) & (hours <= 21)
        t = self.tariffs[region]
        rate = np.where(is_solar, t["solar"], np.where(is_peak, t["peak"], t["base"]))

       
        sun = np.clip(solars / SOLAR_REF_WM2, 0.0, 1.0)
        carbon = kwh * self.emissions[region] * (1.0 - SOLAR_CARBON_DISCOUNT * sun)

        temp_penalty = np.maximum(1.0, temps / 25.0)
        water = kwh * 1.5 * temp_penalty * (self.water_stress[region] / 3.0)

        return {"kwh": kwh, "cost": kwh * rate, "carbon": carbon, "water": water,
                "is_solar": is_solar.astype(float), "is_peak": is_peak.astype(float), "rate": rate}


if __name__ == "__main__":
    engine = PhysicsEngine()
    result = engine.calculate_metrics(gpu_hours=10000, region="Hyderabad", start_hour=14, temperature=35.0)
    print("Test Result (Hyderabad, 2 PM, 35°C):", result)