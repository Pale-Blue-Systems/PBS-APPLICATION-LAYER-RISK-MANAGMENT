import sys
import os
import time

# Add parent directory to path so we can import the module without installing it
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pbs_risk_mgmt import FinancialGovernor, Priority

def run_simulation():
    print("==================================================")
    print("      PBS RISK MANAGEMENT: BUDGET SIMULATION      ")
    print("==================================================")
    print("SCENARIO: 100 MB Daily Limit (Metered Commercial Link)")
    print("--------------------------------------------------")

    # Initialize Governor (100 MB Limit)
    gov = FinancialGovernor(daily_limit_mb=100)
    
    # Define typical packet sizes
    SIZES = {
        "HEARTBEAT": 128,             # Tiny (Bytes)
        "LOGS":      50 * 1024,       # 50 KB
        "BULK":      5 * 1024 * 1024  # 5 MB (Heavy!)
    }

    # Simulate 25 BULK Transmissions (5MB each)
    # This totals 125 MB (Will exceed the 100 MB limit)
    for i in range(1, 26):
        time.sleep(0.05) # Just for effect
        
        # 1. Attempt to send Heavy BULK data (Priority 4)
        decision = gov.check_transmission(SIZES["BULK"], Priority.BULK)
        
        # Format the output for readability
        pct = (gov.used_bytes / gov.daily_limit_bytes) * 100
        bar = "█" * int(pct / 5) + "░" * (20 - int(pct / 5))
        
        if decision.allowed:
            status = "✅ SENT "
            print(f"[{bar}] {pct:5.1f}% | BULK    | {status} | Cost: +5.0 MB")
        else:
            status = "❌ BLOCK"
            print(f"[{bar}] {pct:5.1f}% | BULK    | {status} | {decision.reason}")
            
            # 2. If BULK is blocked, try to send a Heartbeat (Priority CRITICAL)
            hb_decision = gov.check_transmission(SIZES["HEARTBEAT"], Priority.CRITICAL)
            if hb_decision.allowed:
                 print(f"                                   -> Fallback: CRITICAL HEARTBEAT sent (Risk: {hb_decision.risk_level})")

    print("\n--------------------------------------------------")
    print("SIMULATION COMPLETE")
    print("Notice how BULK (4) was cut at 80%, but CRITICAL (0) kept flowing.")

if __name__ == "__main__":
    run_simulation()