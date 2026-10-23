from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "weather_cache"
MODEL_DIR = BASE_DIR / "src" / "models"

RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
CACHE_DIR.mkdir(parents=True, exist_ok=True)
MODEL_DIR.mkdir(parents=True, exist_ok=True)

REGIONS = {
    "Mumbai": {"lat": 19.0760, "lon": 72.8777},
    "Hyderabad": {"lat": 17.3850, "lon": 78.4867},
    "Delhi NCR": {"lat": 28.6139, "lon": 77.2090},
    "Bengaluru": {"lat": 12.9716, "lon": 77.5946},
    "Chennai": {"lat": 13.0827, "lon": 80.2707},
}

BASE_GRID_EMISSION_FACTOR = 0.716
MAX_LOOKAHEAD_HOURS = 120


HISTORY_YEARS = 2           
MAX_HORIZON_HOURS = 168      


DEFAULT_N_GPUS = 200        
MAX_SEARCH_HOURS = 72        
DEADLINE_BUFFER_FRAC = 0.10  
MIN_DEADLINE_BUFFER_H = 2

MAX_GPU_HOURS = 5_000_000    
MAX_DEADLINE_DAYS = 30


N_SCENARIOS = 40            
RISK_AVERSION = 0.25       
CONFIDENCE_EPS = 0.04        
SOLAR_REF_WM2 = 700.0        
SOLAR_CARBON_DISCOUNT = 0.30


def now_ist() -> datetime:
    """Naive current time in India (Open-Meteo data is requested in Asia/Kolkata)."""
    return (datetime.now(timezone.utc) + timedelta(hours=5, minutes=30)).replace(tzinfo=None)