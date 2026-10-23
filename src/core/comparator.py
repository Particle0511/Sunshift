class ResultsComparator:
    @staticmethod
    def calculate_savings(usual: dict, recommended: dict) -> dict:
        def calc_pct(u, r):
            return 0 if u <= 0 else round(max(0, ((u - r) / u) * 100))

        def change_label(u, r):
           
            if u <= 0:
                return "0%"
            pct = round((r - u) / u * 100)
            if pct == 0:
                return "0%"
            return f"{'−' if pct < 0 else '+'}{abs(pct)}%"

        cost_saved = usual["cost_inr"] - recommended["cost_inr"]
        carbon_saved = usual["carbon_kg"] - recommended["carbon_kg"]
        water_saved = usual["water_liters"] - recommended["water_liters"]

        return {
            "cost_saved_inr": cost_saved,
            "cost_pct": calc_pct(usual["cost_inr"], recommended["cost_inr"]),
            "carbon_saved_kg": carbon_saved,
            "carbon_pct": calc_pct(usual["carbon_kg"], recommended["carbon_kg"]),
            "water_saved_liters": water_saved,
            "water_pct": calc_pct(usual["water_liters"], recommended["water_liters"]),
            # new, additive keys: honest signed changes (a metric can get worse)
            "cost_change": change_label(usual["cost_inr"], recommended["cost_inr"]),
            "carbon_change": change_label(usual["carbon_kg"], recommended["carbon_kg"]),
            "water_change": change_label(usual["water_liters"], recommended["water_liters"]),
            "has_tradeoff": bool(cost_saved < 0 or carbon_saved < 0 or water_saved < 0),
        }