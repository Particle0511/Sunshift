import pytest
from src.core.physics import PhysicsEngine

def test_tod_multiplier():
    engine = PhysicsEngine()
    # 2 PM (14:00) should be cheap solar hours
    assert engine.get_tod_multiplier(14) == "solar"
    # 7 PM (19:00) should be expensive peak hours
    assert engine.get_tod_multiplier(19) == "peak"
    # 2 AM (2:00) should be standard base hours
    assert engine.get_tod_multiplier(2) == "base"

def test_pue_calculation():
    engine = PhysicsEngine()
    # At cool 20°C, PUE should stay at the baseline of 1.2
    assert engine.calculate_pue(20.0) == 1.2
    # At hot 32°C, the cooling system works harder, PUE should increase by 0.15
    assert round(engine.calculate_pue(32.0), 3) == 1.35

def test_calculate_metrics():
    engine = PhysicsEngine()
    # Test a 1000 GPU hour job in Mumbai at 2 PM, 30°C
    metrics = engine.calculate_metrics(gpu_hours=1000, region="Mumbai", start_hour=14, temperature=30.0)
    
    assert "cost_inr" in metrics
    assert "carbon_kg" in metrics
    assert "water_liters" in metrics
    
    # 1000 hours * 0.75 kW * 1.32 PUE = 990 kWh total energy
    assert metrics["energy_kwh"] == 990.0
    
    # Mumbai solar tariff is 6.5 INR/kWh. 990 * 6.5 = 6435.0 INR
    assert metrics["cost_inr"] == 6435.0

if __name__ == "__main__":
    pytest.main(["-v"])