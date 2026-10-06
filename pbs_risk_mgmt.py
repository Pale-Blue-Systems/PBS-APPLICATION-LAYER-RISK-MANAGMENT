"""
PBS Application-Layer Risk Management
Copyright (c) 2026 Pale Blue Systems
Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from dataclasses import dataclass
from enum import IntEnum
import time

# ==========================================
# PBS Protocol Constants (PBS-PRIO-01 v1.4)
# ==========================================

class Priority(IntEnum):
    """
    PBS Priority Classes per PBS-PRIO-01 v1.4 Section 4.
    Lower value = Higher priority.
    Values 5-255 are reserved and MUST NOT be used (Section 5).
    """
    CRITICAL = 0  # Immediate life- or safety-critical data
    HIGH     = 1  # Mission-critical operational data
    NORMAL   = 2  # Routine mission data
    LOW      = 3  # Opportunistic or deferrable data
    BULK     = 4  # Non-urgent, high-volume data

@dataclass
class TransmissionDecision:
    """Admission decision returned by a governor's check_transmission().

    Attributes:
        allowed: True if the caller may transmit the packet. The governor
            commits the packet's cost to its budget only when True.
        reason: Cause of a refusal. Admitted packets carry "Within Budget"
            (FinancialGovernor) or "Power Nominal" (PowerGovernor) at every
            risk level.
        cost_incurred: Cost of the packet in MiB (FinancialGovernor) or
            joules (PowerGovernor), reported for admitted and refused
            packets. A BLACKOUT refusal reports 0.
        risk_level: Budget state at projected usage. FinancialGovernor:
            GREEN, YELLOW, ORANGE or RED. PowerGovernor: GREEN, YELLOW or
            RED, or BLACKOUT for a refusal below the hard cutoff.
    """
    allowed: bool
    reason: str
    cost_incurred: float
    risk_level: str

# ==========================================
# 1. The Financial Governor (Data Budget)
# ==========================================

class FinancialGovernor:
    """Data-volume governor for metered links.

    Admits or refuses each outbound packet against a byte budget per 24 h
    period. Thresholds apply to projected usage: bytes committed in the
    current period plus the size of the packet under evaluation.

        Projected usage    risk_level   Refused classes
        < 80 %             GREEN        none
        80 % to < 95 %     YELLOW       BULK
        95 % to < 100 %    ORANGE       LOW, BULK
        >= 100 %           RED          HIGH, NORMAL, LOW, BULK

    CRITICAL is admitted at every risk level, including beyond 100 %.
    """

    def __init__(self, daily_limit_mb: float, strict_mode: bool = True):
        """
        Args:
            daily_limit_mb (float): Maximum allowed data per 24h period.
            strict_mode (bool): If True, strictly blocks lower priorities based on thresholds.
        """
        self.daily_limit_bytes = daily_limit_mb * 1024 * 1024
        self.used_bytes = 0
        self.strict_mode = strict_mode
        self.last_reset_time = time.time()

    def _check_reset(self):
        """Resets the counter if 24 hours have passed."""
        if time.time() - self.last_reset_time > 86400:
            self.used_bytes = 0
            self.last_reset_time = time.time()

    def check_transmission(self, packet_size_bytes: int, priority: int) -> TransmissionDecision:
        """Decide whether one packet may be sent; commit its size if admitted.

        Args:
            packet_size_bytes: Packet size in bytes.
            priority: PBS-PRIO-01 class value, 0 (CRITICAL) to 4 (BULK).

        Returns:
            TransmissionDecision. cost_incurred is the packet size in MiB.
        """
        self._check_reset()

        # Thresholds apply to projected usage: committed bytes + this packet.
        projected_usage = self.used_bytes + packet_size_bytes
        usage_percent = (projected_usage / self.daily_limit_bytes) * 100

        # Default State
        decision = TransmissionDecision(True, "Within Budget", packet_size_bytes / 1024 / 1024, "GREEN")

        # ---------------------------------------------------------
        # SHEDDING LOGIC
        # PBS-PRIO-01 v1.4 Section 6: lower-priority envelopes MAY be
        # delayed or dropped under sustained congestion. Lower classes
        # are refused first; CRITICAL is never refused.
        # ---------------------------------------------------------

        if usage_percent >= 100:
            # RED STATE: Budget Exhausted.
            decision.risk_level = "RED"
            if priority > Priority.CRITICAL:
                decision.allowed = False
                decision.reason = "BUDGET EXHAUSTED: Only CRITICAL (0) Allowed"

        elif usage_percent >= 95:
            # ORANGE STATE: Critical Reserve.
            decision.risk_level = "ORANGE"
            if priority >= Priority.LOW:
                decision.allowed = False
                decision.reason = "CRITICAL RESERVE: LOW/BULK Dropped"

        elif usage_percent >= 80:
            # YELLOW STATE: Caution.
            decision.risk_level = "YELLOW"
            if priority == Priority.BULK:
                decision.allowed = False
                decision.reason = "BUDGET CAUTION: BULK Dropped"

        # ---------------------------------------------------------

        # Commit usage only if allowed
        if decision.allowed:
            self.used_bytes += packet_size_bytes

        return decision

    def get_status(self):
        """Return usage in the current period, e.g. "DATA USAGE: 12.50 MB (12.5%)".

        MB in this string is MiB (1 048 576 bytes).
        """
        mb_used = self.used_bytes / 1024 / 1024
        percent = (self.used_bytes / self.daily_limit_bytes) * 100
        return f"DATA USAGE: {mb_used:.2f} MB ({percent:.1f}%)"


# ==========================================
# 2. The Power Governor (Energy Budget)
# ==========================================

class PowerGovernor:
    """Transmit-energy governor for battery-constrained assets.

    check_transmission() applies two checks in order:

    1. Hard cutoff. If current_battery_level is below the level set with
       set_hard_cutoff(), every class except CRITICAL is refused with
       risk_level BLACKOUT and cost_incurred 0. CRITICAL proceeds to
       check 2 and carries the budget risk level.
    2. Energy budget. Thresholds apply to projected usage: joules
       committed so far plus this packet's cost
       (packet_size_bytes * joules_per_byte).

        Projected usage    risk_level   Refused classes
        < 85 %             GREEN        none
        85 % to < 98 %     YELLOW       BULK
        >= 98 %            RED          HIGH, NORMAL, LOW, BULK

    There is no ORANGE level. CRITICAL is admitted below the hard cutoff
    and at every risk level, including beyond 100 % of the budget.
    """

    def __init__(self, daily_budget_joules: float, joules_per_byte: float):
        """
        Args:
            daily_budget_joules (float): Total energy allocated for comms.
            joules_per_byte (float): Energy cost of the radio hardware per byte sent.
        """
        self.daily_budget_joules = daily_budget_joules
        self.joules_per_byte = joules_per_byte
        self.used_joules = 0
        self.hard_cutoff_percent = 0.0

    def set_hard_cutoff(self, battery_level: float):
        """Set the battery level below which only CRITICAL is admitted.

        battery_level uses the same scale as current_battery_level in
        check_transmission(); the examples use a fraction (0.20 = 20 %).
        The comparison is strict: a battery level equal to the cutoff
        passes. The default cutoff is 0.0.
        """
        self.hard_cutoff_percent = battery_level

    def check_transmission(self, packet_size_bytes: int, priority: int, current_battery_level: float) -> TransmissionDecision:
        """Decide whether one packet may be sent; commit its energy if admitted.

        Args:
            packet_size_bytes: Packet size in bytes.
            priority: PBS-PRIO-01 class value, 0 (CRITICAL) to 4 (BULK).
            current_battery_level: Battery state of charge, on the same
                scale as the hard cutoff.

        Returns:
            TransmissionDecision. cost_incurred is the packet energy in J
            (0 for a BLACKOUT refusal).
        """

        # 1. Hard cutoff: below it, only CRITICAL proceeds to the budget check.
        if current_battery_level < self.hard_cutoff_percent:
            if priority > Priority.CRITICAL:
                 return TransmissionDecision(False, "BATTERY CRITICAL: Hard Cutoff", 0, "BLACKOUT")

        # 2. Budget check on projected usage: committed joules + this packet.
        cost_joules = packet_size_bytes * self.joules_per_byte
        projected_usage = self.used_joules + cost_joules
        usage_percent = (projected_usage / self.daily_budget_joules) * 100

        decision = TransmissionDecision(True, "Power Nominal", cost_joules, "GREEN")

        if usage_percent >= 98:
            decision.risk_level = "RED"
            if priority > Priority.CRITICAL:
                decision.allowed = False
                decision.reason = "POWER BUDGET EMPTY"

        elif usage_percent >= 85:
            decision.risk_level = "YELLOW"
            if priority >= Priority.BULK:
                decision.allowed = False
                decision.reason = "POWER SAVE MODE: BULK Dropped"

        if decision.allowed:
            self.used_joules += cost_joules

        return decision
