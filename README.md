# PBS Application-Layer Risk Management

[![tests](https://github.com/Pale-Blue-Systems/PBS-APPLICATION-LAYER-RISK-MANAGMENT/actions/workflows/tests.yml/badge.svg)](https://github.com/Pale-Blue-Systems/PBS-APPLICATION-LAYER-RISK-MANAGMENT/actions/workflows/tests.yml)

## Purpose

`pbs_risk_mgmt.py` provides two admission-control governors for outbound traffic on PBS links with a finite resource budget:

- `FinancialGovernor`: data-volume budget in MiB per 24 h period, for metered links.
- `PowerGovernor`: transmit-energy budget in joules per 24 h period, with a battery-level hard cutoff, for battery-constrained assets.

For each packet the caller passes the packet size and its PBS-PRIO-01 priority class, plus the battery level for `PowerGovernor`. The governor returns a [`TransmissionDecision`](#transmissiondecision). As the budget depletes, the governor refuses the lowest classes first. CRITICAL (0) is admitted in every state.

---

## Scope

The governors run at the application layer, between mission logic and the PBS protocol stack. They do not build, parse or modify PBS-ENV-01 envelopes. The caller transmits a packet only when `decision.allowed` is `True`.

**Use cases:**
- Metered commercial links with per-MB billing
- Battery-constrained assets with a fixed transmit-energy allocation
- Autonomous systems that need a defined degradation sequence when a resource budget runs out

---

## Installation

Requires Python 3.8 or later. The module uses only the Python standard library, so there is nothing to install with pip.

```bash
git clone https://github.com/Pale-Blue-Systems/PBS-APPLICATION-LAYER-RISK-MANAGMENT.git
cd PBS-APPLICATION-LAYER-RISK-MANAGMENT

# Run the budget simulation
python3 examples/demo_budget.py
```

To use the governors from another project, add the clone directory to `PYTHONPATH` or copy `pbs_risk_mgmt.py` into the project:

```bash
# In the clone directory:
export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"
# From any other directory:
cd ~
python3 -c "from pbs_risk_mgmt import FinancialGovernor, PowerGovernor, Priority"
```

---

## Run the tests

From the repository root:

```bash
python3 -m unittest discover -s tests -v
```

`tests/test_governors.py` uses only `unittest`. It covers every threshold boundary of both governors for all five classes, projected-usage evaluation, CRITICAL admission beyond the budget, the hard cutoff, the 24-hour reset, advisory mode and priority validation. The [tests workflow](.github/workflows/tests.yml) runs the tests and `examples/demo_budget.py` on Python 3.8, 3.10 and 3.12 for every push and pull request.

---

## Usage

### FinancialGovernor (data budget)

```python
from pbs_risk_mgmt import FinancialGovernor, Priority

gov = FinancialGovernor(daily_limit_mb=500)  # 500 MiB per 24 h period

# radio, log, video_frame and heartbeat stand for the caller's own objects.
def transmit_packet(data, priority):
    decision = gov.check_transmission(len(data), priority)
    if decision.allowed:
        radio.send(data)
    else:
        log(f"Refused ({decision.risk_level}): {decision.reason}")

transmit_packet(video_frame, Priority.BULK)    # first class refused as the budget depletes
transmit_packet(heartbeat, Priority.CRITICAL)  # admitted in every state
```

`daily_limit_mb` is in MiB (1 MiB = 1 048 576 bytes). `cost_incurred` and `get_status()` use the same unit; `get_status()` labels it `MB`.

`FinancialGovernor(daily_limit_mb, strict_mode=False)` selects advisory mode. The governor evaluates the same thresholds and returns the same `risk_level`, but admits every packet and commits its size. A packet that strict mode would refuse carries the reason `ADVISORY, not enforced: ` followed by the refusal reason. The default, `strict_mode=True`, enforces the table in [Shedding logic](#shedding-logic).

### PowerGovernor (energy budget)

```python
from pbs_risk_mgmt import PowerGovernor, Priority

# 5000 J per 24 h period for communications; radio cost 0.002 J/byte
power_gov = PowerGovernor(daily_budget_joules=5000, joules_per_byte=0.002)

# Below 20 % battery, refuse every class except CRITICAL
power_gov.set_hard_cutoff(battery_level=0.20)

decision = power_gov.check_transmission(
    packet_size_bytes=1024,
    priority=Priority.NORMAL,
    current_battery_level=0.35,
)
# decision.allowed is True, decision.risk_level is "GREEN",
# decision.cost_incurred is 2.048 (J)
```

`set_hard_cutoff()` and `current_battery_level` use the same scale; this example uses a fraction of full charge. The default cutoff is 0.0.

### TransmissionDecision

| Field | Type | Content |
|:------|:-----|:--------|
| `allowed` | `bool` | `True`: transmit the packet. The governor commits the packet's cost only when `True`. |
| `reason` | `str` | Refusal reason, or the admission text given under [Shedding logic](#shedding-logic). |
| `cost_incurred` | `float` | Packet cost in MiB (`FinancialGovernor`) or J (`PowerGovernor`), reported for admitted and refused packets; 0 for a `BLACKOUT` refusal. |
| `risk_level` | `str` | `GREEN`, `YELLOW`, `ORANGE` or `RED` (`FinancialGovernor`); `GREEN`, `YELLOW`, `RED` or `BLACKOUT` (`PowerGovernor`). |

---

## Shedding logic

Both governors evaluate thresholds on **projected usage**: the budget committed in the current period plus the cost of the packet under evaluation. A packet is refused when projected usage falls in a band that sheds its class. A refused packet commits nothing; an admitted packet commits its full cost. Lower classes are shed first, under PBS-PRIO-01 v1.4 Section 6 ("Lower-priority envelopes MAY be delayed or dropped under sustained congestion"). CRITICAL is never refused.

Each governor resets its usage to zero on the first `check_transmission()` call (or `FinancialGovernor.get_status()` call) made more than 86 400 s after the previous reset or after construction. The new period starts at that call; periods are not aligned to midnight. Elapsed time is the difference of two `time.time()` readings (system wall clock). A clock step of *s* seconds therefore moves the end of the current period: *s* seconds earlier for a forward step, *s* seconds later for a backward step.

### FinancialGovernor

Projected usage = (bytes committed + packet bytes) / (`daily_limit_mb` × 1 048 576).

| `risk_level` | Projected usage | Refused | Admitted | Refusal `reason` |
|:-------------|:----------------|:--------|:---------|:-----------------|
| **GREEN**  | < 80 %          | none | CRITICAL, HIGH, NORMAL, LOW, BULK | — |
| **YELLOW** | ≥ 80 %, < 95 %  | BULK | CRITICAL, HIGH, NORMAL, LOW | `BUDGET CAUTION: BULK Dropped` |
| **ORANGE** | ≥ 95 %, < 100 % | LOW, BULK | CRITICAL, HIGH, NORMAL | `CRITICAL RESERVE: LOW/BULK Dropped` |
| **RED**    | ≥ 100 %         | HIGH, NORMAL, LOW, BULK | CRITICAL | `BUDGET EXHAUSTED: Only CRITICAL (0) Allowed` |

In strict mode, admitted packets carry the reason `Within Budget` at every risk level. In advisory mode (`strict_mode=False`) no class is refused; see [FinancialGovernor (data budget)](#financialgovernor-data-budget).

### PowerGovernor

`check_transmission()` applies two checks in order.

1. **Hard cutoff.** If `current_battery_level` is below the cutoff, every class except CRITICAL is refused with `risk_level` `BLACKOUT` and `cost_incurred` 0. CRITICAL continues to the budget check and receives the budget risk level. A battery level equal to the cutoff passes.
2. **Energy budget.** Projected usage = (joules committed + packet bytes × `joules_per_byte`) / `daily_budget_joules`.

| `risk_level` | Condition | Refused | Admitted | Refusal `reason` |
|:-------------|:----------|:--------|:---------|:-----------------|
| **GREEN**    | projected usage < 85 %         | none | CRITICAL, HIGH, NORMAL, LOW, BULK | — |
| **YELLOW**   | projected usage ≥ 85 %, < 98 % | BULK | CRITICAL, HIGH, NORMAL, LOW | `POWER SAVE MODE: BULK Dropped` |
| **RED**      | projected usage ≥ 98 %         | HIGH, NORMAL, LOW, BULK | CRITICAL | `POWER BUDGET EMPTY` |
| **BLACKOUT** | battery level below the cutoff | HIGH, NORMAL, LOW, BULK | CRITICAL, subject to the budget check | `BATTERY CRITICAL: Hard Cutoff` |

`PowerGovernor` has no ORANGE level. Admitted packets carry the reason `Power Nominal` at every risk level.

---

## Priority Classes (PBS-PRIO-01 v1.4, Section 4)

| Value | Name | Description |
|------:|------|-------------|
| 0 | CRITICAL | Immediate life- or safety-critical data |
| 1 | HIGH | Mission-critical operational data |
| 2 | NORMAL | Routine mission data |
| 3 | LOW | Opportunistic or deferrable data |
| 4 | BULK | Non-urgent, high-volume data |

Values 5–255 are reserved and MUST NOT be used (PBS-PRIO-01 v1.4, Section 5). Both governors raise `ValueError` for a priority outside 0–4 and commit nothing.

---

## Related Specifications

- [PBS-PRIO-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-PRIO-01.md) v1.4: Priority Classification and Deterministic Handling
- [PBS-ENV-01](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN/blob/main/PBS-RFC-LIB/PBS-ENV-01.md) v1.3: Core Message Envelope (Priority is the u8 at header offset 0x01)

---

## License

Apache License 2.0

See [LICENSE](LICENSE) for full terms.
