import json
from pathlib import Path
from src.config import RAW_DATA_DIR

def generate_baseline_datasets():

    tariffs = {
        "Mumbai": {"base": 8.0, "solar": 6.5, "peak": 10.0},
        "Hyderabad": {"base": 7.5, "solar": 6.0, "peak": 9.5},
        "Delhi NCR": {"base": 8.5, "solar": 7.0, "peak": 11.0},
        "Bengaluru": {"base": 8.0, "solar": 6.5, "peak": 10.5},
        "Chennai": {"base": 8.2, "solar": 6.8, "peak": 10.8}
    }
    
    
    water_stress = {
        "Mumbai": 2.5,
        "Hyderabad": 3.0,
        "Delhi NCR": 4.5,
        "Bengaluru": 4.8,
        "Chennai": 5.0
    }
    
   
    emissions = {
        "Mumbai": 0.71,
        "Hyderabad": 0.68,
        "Delhi NCR": 0.75,
        "Bengaluru": 0.65,
        "Chennai": 0.72
    }

 
    with open(RAW_DATA_DIR / "state_tod_tariffs.json", "w") as f:
        json.dump(tariffs, f, indent=4)
        
    with open(RAW_DATA_DIR / "wri_water_stress_index.json", "w") as f:
        json.dump(water_stress, f, indent=4)
        
    with open(RAW_DATA_DIR / "cea_grid_emission_factors.json", "w") as f:
        json.dump(emissions, f, indent=4)

def load_json(filename: str) -> dict:
    filepath = RAW_DATA_DIR / filename
    if not filepath.exists():
        generate_baseline_datasets()
        
    with open(filepath, "r") as f:
        return json.load(f)

if __name__ == "__main__":
    generate_baseline_datasets()