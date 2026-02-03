# PBS Application-Layer Risk Management

## Purpose

This module provides application-layer resource governors for PBS-compliant systems operating on metered or power-constrained communication links.

The governors monitor resource consumption (data volume or energy) and enforce priority-based traffic shedding per PBS-PRIO-01 before critical limits are reached.

---

## Scope

PBS-RISK-MGMT operates at the application layer, between mission logic and the PBS protocol stack. It does not modify PBS envelope semantics; it provides admission control for outbound traffic.

**Use Cases:**
- Metered commercial links with per-MB billing
- Battery-constrained assets with limited transmission energy budgets
- Autonomous systems requiring predictable degradation under resource exhaustion

---

## Installation

```bash
# Clone the repository
git clone https://github.com/Pale-Blue-Systems/PBS-APPLICATION-LAYER-RISK-MANAGEMENT.git

# Install from source
cd PBS-APPLICATION-LAYER-RISK-MANAGEMENT
pip install -e .
```

---

## Usage

### Financial Governor (Data Budget)

Enforces a daily data transmission limit with priority-based shedding.

```python
from pbs_risk_mgmt import FinancialGovernor, Priority

# Initialize with 500 MB daily limit
gov = FinancialGovernor(daily_limit_mb=500)

def transmit_packet(data, priority):
    decision = gov.check_transmission(len(data), priority)
    
    if decision.allowed:
        radio.send(data)
    else:
        # Handle blocked transmission
        log(f"Blocked: {decision.reason}")

# BULK traffic is shed first as budget depletes
transmit_packet(video_frame, Priority.BULK)
transmit_packet(heartbeat, Priority.CRITICAL)
```

### Power Governor (Energy Budget)

Enforces energy consumption limits for battery-constrained operations.

```python
from pbs_risk_mgmt import PowerGovernor, Priority

# Allocate 5000 Joules for daily comms, 0.002 J/byte radio cost
power_gov = PowerGovernor(daily_budget_joules=5000, joules_per_byte=0.002)

# Hard cutoff: silence radio below 20% battery
power_gov.set_hard_cutoff(battery_level=0.20)

decision = power_gov.check_transmission(
    packet_size_bytes=1024,
    priority=Priority.NORMAL,
    current_battery_level=0.35
)
```

---

## Shedding Logic

The governors implement priority-based traffic shedding per PBS-PRIO-01 Section 6/7.

| Risk Level | Budget Used | Action | Traffic Allowed |
|:-----------|:------------|:-------|:----------------|
| **GREEN**  | 0% – 79%   | Pass All | CRITICAL, HIGH, NORMAL, LOW, BULK |
| **YELLOW** | 80% – 94%  | Drop BULK | CRITICAL, HIGH, NORMAL, LOW |
| **ORANGE** | 95% – 99%  | Drop LOW, BULK | CRITICAL, HIGH, NORMAL |
| **RED**    | ≥ 100%     | CRITICAL Only | CRITICAL |

---

## Priority Classes (PBS-PRIO-01)

| Value | Name | Description |
|------:|------|-------------|
| 0 | CRITICAL | Immediate life- or safety-critical data |
| 1 | HIGH | Mission-critical operational data |
| 2 | NORMAL | Routine mission data |
| 3 | LOW | Opportunistic or deferrable data |
| 4 | BULK | Non-urgent, high-volume data |

Values 5–255 are reserved per PBS-PRIO-01 and MUST NOT be used.

---

## Related Specifications

- [PBS-PRIO-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-PRIO-01.md) — Priority Classification
- [PBS-ENV-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-ENV-01.md) — Core Message Envelope

---

## License

Apache License 2.0

See [LICENSE](LICENSE) for full terms.