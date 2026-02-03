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
# PBS Protocol Constants (PBS-PRIO-01 v1.3)
# ==========================================

class Priority(IntEnum):
    """
    PBS Priority Classes per PBS-PRIO-01 Section 4.
    Lower value = Higher priority.
    Values 5-255 are reserved and MUST NOT be used.
    """
    CRITICAL = 0  # Immediate life- or safety-critical data
    HIGH     = 1  # Mission-critical operational data
    NORMAL   = 2  # Routine mission data
    LOW      = 3  # Opportunistic or deferrable data
    BULK     = 4  # Non-urgent, high-volume data

@dataclass
class TransmissionDecision:
    """Standardized response from the Governor"""
    allowed: bool
    reason: str
    cost_incurred: float  # MB or Joules
    risk_level: str       # GREEN, YELLOW, ORANGE, RED

# ==========================================
# 1. The Financial Governor (Data Budget)
# ==========================================

class FinancialGovernor:
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
        self._check_reset()
        
        # Forecast usage
        projected_usage = self.used_bytes + packet_size_bytes
        usage_percent = (projected_usage / self.daily_limit_bytes) * 100
        
        # Default State
        decision = TransmissionDecision(True, "Within Budget", packet_size_bytes / 1024 / 1024, "GREEN")

        # ---------------------------------------------------------
        # SHEDDING LOGIC (PBS-PRIO-01 Section 6/7)
        # Lower-priority envelopes MAY be delayed or dropped under
        # sustained congestion.
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
        mb_used = self.used_bytes / 1024 / 1024
        percent = (self.used_bytes / self.daily_limit_bytes) * 100
        return f"DATA USAGE: {mb_used:.2f} MB ({percent:.1f}%)"


# ==========================================
# 2. The Power Governor (Energy Budget)
# ==========================================

class PowerGovernor:
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
        """Set a battery % below which radio is silenced completely"""
        self.hard_cutoff_percent = battery_level

    def check_transmission(self, packet_size_bytes: int, priority: int, current_battery_level: float) -> TransmissionDecision:
        
        # 1. Hardware Safety Check (Hard Cutoff)
        if current_battery_level < self.hard_cutoff_percent:
            if priority > Priority.CRITICAL:
                 return TransmissionDecision(False, "BATTERY CRITICAL: Hard Cutoff", 0, "BLACKOUT")

        # 2. Budget Check
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