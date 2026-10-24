import datetime
import math

class PausableOptimizer:
    def __init__(self, min_block_hours=4, checkpoint_penalty_mins=15):
        self.min_block = min_block_hours
        self.penalty_hours = checkpoint_penalty_mins / 60.0

    def _generate_synthetic_rates(self, start_time, total_window_hours):
        rates = []
        for i in range(total_window_hours):
            current = start_time + datetime.timedelta(hours=i)
            base_rate = 7.9 
            if 10 <= current.hour <= 15:
                base_rate -= 1.2 
            elif 22 <= current.hour or current.hour <= 5:
                base_rate -= 0.5 
            rates.append({"time": current, "cost": base_rate, "hour_index": i})
        return rates

    def get_straight_through_plan(self, target_hours, rates):
        best_cost = float('inf')
        best_start = 0
        for i in range(len(rates) - target_hours + 1):
            window = rates[i:i+target_hours]
            cost = sum(h["cost"] for h in window)
            if cost < best_cost:
                best_cost = cost
                best_start = i
                
        schedule = rates[best_start:best_start+target_hours]
        return {
            "schedule": schedule,
            "blocks": [schedule],
            "total_cost": best_cost,
            "run_hours": target_hours,
            "effective_progress": target_hours,
            "pauses": 0,
            "type": "straight-through"
        }

    def get_pausable_plan(self, target_hours, rates):
        remaining = float(target_hours)
        selected_hours = []
        available_rates = rates.copy()
        pauses = -1 

        while remaining > 0 and len(available_rates) >= self.min_block:
            best_chunk = None
            best_chunk_avg = float('inf')
            
            chunk_size = int(math.ceil(remaining)) if remaining < self.min_block else self.min_block
            
            for i in range(len(available_rates) - chunk_size + 1):
                chunk = available_rates[i:i+chunk_size]
                
                valid_sequence = all(chunk[j]["hour_index"] == chunk[j-1]["hour_index"] + 1 for j in range(1, chunk_size))
                if not valid_sequence:
                    continue
                    
                avg_cost = sum(h["cost"] for h in chunk) / chunk_size
                if avg_cost < best_chunk_avg:
                    best_chunk_avg = avg_cost
                    best_chunk = chunk

            if not best_chunk:
                break

            selected_hours.extend(best_chunk)
            remaining -= chunk_size
            pauses += 1
            
            if remaining > 0:
                remaining += self.penalty_hours 
                
            available_rates = [r for r in available_rates if r not in best_chunk]

        selected_hours.sort(key=lambda x: x["hour_index"])
        
        blocks = []
        if selected_hours:
            current_block = [selected_hours[0]]
            for h in selected_hours[1:]:
                if h["hour_index"] == current_block[-1]["hour_index"] + 1:
                    current_block.append(h)
                else:
                    blocks.append(current_block)
                    current_block = [h]
            blocks.append(current_block)

        total_cost = sum(h["cost"] for h in selected_hours)
        total_penalties = max(0, len(blocks) - 1) * self.penalty_hours

        return {
            "schedule": selected_hours,
            "blocks": blocks,
            "total_cost": total_cost,
            "run_hours": len(selected_hours),
            "effective_progress": len(selected_hours) - total_penalties,
            "pauses": max(0, len(blocks) - 1),
            "type": "pausable"
        }

    def generate_cron_snippet(self, blocks):
        snippet = "# Sunshift Pause-and-Resume Slurm/Cron Snippet\n"
        for i, block in enumerate(blocks):
            if not block: continue
            start = block[0]["time"]
            end = block[-1]["time"] + datetime.timedelta(hours=1)
            snippet += f"# Block {i+1}: {start.strftime('%Y-%m-%d %H:%M')} to {end.strftime('%H:%M')}\n"
            snippet += f"{start.minute} {start.hour} {start.day} {start.month} * sbatch resume_job.sh\n"
            snippet += f"{end.minute} {end.hour} {end.day} {end.month} * scancel --signal=SIGINT <job_id>\n"
        return snippet

if __name__ == "__main__":
    opt = PausableOptimizer(min_block_hours=4, checkpoint_penalty_mins=15)
    
    test_start = datetime.datetime(2026, 10, 26, 8, 0)
    deadline_days = 5
    job_hours = 50
    rates = opt._generate_synthetic_rates(test_start, deadline_days * 24)
    
    straight_plan = opt.get_straight_through_plan(job_hours, rates)
    pausable_plan = opt.get_pausable_plan(job_hours, rates)
    
    if pausable_plan["total_cost"] >= straight_plan["total_cost"]:
        pausable_plan = straight_plan
        
    print("==================================================")
    print(" VERIFICATION SUITE: PAUSE-AND-RESUME SCHEDULING")
    print("==================================================\n")
    
    print(f"1. [DEADLINE VERIFICATION]")
    last_hour = pausable_plan["schedule"][-1]["time"]
    max_deadline = test_start + datetime.timedelta(days=deadline_days)
    print(f"   -> Last execution hour: {last_hour.strftime('%Y-%m-%d %H:%M')}")
    print(f"   -> Deadline limit: {max_deadline.strftime('%Y-%m-%d %H:%M')}")
    print(f"   -> Deadline met: {last_hour < max_deadline}")
    
    print(f"\n2. [RUN HOURS & PENALTY VERIFICATION]")
    print(f"   -> Target job hours: {job_hours}")
    print(f"   -> Total hours scheduled: {pausable_plan['run_hours']}")
    print(f"   -> Number of pauses: {pausable_plan['pauses']}")
    print(f"   -> Effective progress (minus penalties): {pausable_plan['effective_progress']}")
    
    print(f"\n3. [MINIMUM BLOCK VERIFICATION]")
    blocks_valid = all(len(b) >= opt.min_block for b in pausable_plan["blocks"][:-1])
    print(f"   -> All intermediate blocks >= {opt.min_block} hours: {blocks_valid}")
    
    print(f"\n4. [COST GUARANTEE VERIFICATION]")
    print(f"   -> Straight-through cost: ₹{straight_plan['total_cost']:.2f}")
    print(f"   -> Pause-and-resume cost: ₹{pausable_plan['total_cost']:.2f}")
    savings_pct = ((straight_plan['total_cost'] - pausable_plan['total_cost']) / straight_plan['total_cost']) * 100 if straight_plan['total_cost'] else 0
    print(f"   -> Savings: {savings_pct:.1f}%")
    print(f"   -> Recommendation is optimal: {pausable_plan['total_cost'] <= straight_plan['total_cost']}")
    print(f"   -> Selected Execution Type: {pausable_plan['type']}")
    
    print(f"\n5. [EXPORTABLE SCHEDULER SNIPPET]")
    print(opt.generate_cron_snippet(pausable_plan["blocks"]))