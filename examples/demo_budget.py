"""FinancialGovernor budget simulation.

Offers 25 BULK packets of 5 MiB (125 MiB in total) to a governor with a
100 MiB budget. After each BULK refusal it offers a 128-byte CRITICAL
heartbeat. Each row prints the usage committed before the decision and
the projected usage the decision is based on (committed + this packet).
No summary figure is hard-coded: counts, risk level and reason come from
the returned decisions, percentages from the governor state before each
call, and the final line from get_status().
"""

import os
import sys

# Import pbs_risk_mgmt from the repository root without installing it.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from pbs_risk_mgmt import FinancialGovernor, Priority  # noqa: E402

MIB = 1024 * 1024
DAILY_LIMIT_MB = 100        # MiB per 24 h period
BULK_SIZE = 5 * MIB         # bytes
HEARTBEAT_SIZE = 128        # bytes
BULK_ATTEMPTS = 25
BAR_WIDTH = 20              # characters; one character = 5 % of the budget


def usage_bar(percent):
    filled = max(0, min(BAR_WIDTH, int(percent * BAR_WIDTH / 100)))
    return "[" + "#" * filled + "." * (BAR_WIDTH - filled) + "]"


def offer(gov, step, size, priority):
    """Submit one packet, print one row, return (decision, used %, projected %)."""
    used_pct = gov.used_bytes / gov.daily_limit_bytes * 100
    projected_pct = (gov.used_bytes + size) / gov.daily_limit_bytes * 100
    decision = gov.check_transmission(size, priority)
    result = "SENT" if decision.allowed else "REFUSED"
    print(f"{step:>4}  {usage_bar(used_pct)} {used_pct:5.1f}%  {projected_pct:9.1f}%  "
          f"{priority.name:<8}  {size:>9}  {result:<7}  {decision.risk_level:<6}  {decision.reason}")
    return decision, used_pct, projected_pct


def run_simulation():
    gov = FinancialGovernor(daily_limit_mb=DAILY_LIMIT_MB)

    print("PBS RISK MANAGEMENT: FinancialGovernor budget simulation")
    print(f"Budget: {DAILY_LIMIT_MB} MiB per 24 h period ({gov.daily_limit_bytes:.0f} bytes).")
    print(f"Offer {BULK_ATTEMPTS} BULK packets of {BULK_SIZE // MIB} MiB. After each refusal, "
          f"offer one {HEARTBEAT_SIZE}-byte CRITICAL heartbeat.")
    print("Decisions use projected usage = used before + this packet.")
    print()
    print(f"{'Step':>4}  {'Used before':<29}  {'Projected':>10}  {'Class':<8}  {'Bytes':>9}  "
          f"{'Result':<7}  {'Risk':<6}  Reason")

    bulk_sent = 0
    first_refusal = None    # (step, used %, projected %, decision)
    heartbeats_offered = 0
    heartbeats_sent = 0

    for step in range(1, BULK_ATTEMPTS + 1):
        decision, used_pct, projected_pct = offer(gov, step, BULK_SIZE, Priority.BULK)
        if decision.allowed:
            bulk_sent += 1
            continue
        if first_refusal is None:
            first_refusal = (step, used_pct, projected_pct, decision)
        heartbeats_offered += 1
        hb_decision, _, _ = offer(gov, "", HEARTBEAT_SIZE, Priority.CRITICAL)
        if hb_decision.allowed:
            heartbeats_sent += 1

    bulk_refused = BULK_ATTEMPTS - bulk_sent
    print()
    print("Summary")
    print(f"  BULK sent:            {bulk_sent} of {BULK_ATTEMPTS} "
          f"({bulk_sent * BULK_SIZE // MIB} MiB)")
    print(f"  BULK refused:         {bulk_refused}")
    if first_refusal is not None:
        step, used_pct, projected_pct, decision = first_refusal
        print(f"  First BULK refusal:   step {step}: used {used_pct:.1f}%, "
              f"projected {projected_pct:.1f}%, {decision.risk_level} ({decision.reason})")
    print(f"  CRITICAL heartbeats:  {heartbeats_sent} of {heartbeats_offered} sent")
    print(f"  Final status:         {gov.get_status()}")


if __name__ == "__main__":
    run_simulation()
