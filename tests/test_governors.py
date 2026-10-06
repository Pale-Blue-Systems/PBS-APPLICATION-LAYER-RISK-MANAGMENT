"""Unit tests for pbs_risk_mgmt (standard-library unittest only).

Run from the repository root:

    python3 -m unittest discover -s tests -v
"""

import dataclasses
import os
import sys
import unittest
from unittest import mock

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pbs_risk_mgmt  # noqa: E402
from pbs_risk_mgmt import (  # noqa: E402
    BUDGET_PERIOD_S,
    FinancialGovernor,
    PowerGovernor,
    Priority,
    TransmissionDecision,
)

MIB = 1024 * 1024
T0 = 1_800_000_000.0  # Arbitrary epoch for the patched clock, seconds

ALL_CLASSES = frozenset(Priority)
NON_CRITICAL = ALL_CLASSES - {Priority.CRITICAL}
BULK_ONLY = frozenset({Priority.BULK})
LOW_AND_BULK = frozenset({Priority.LOW, Priority.BULK})
NONE = frozenset()

# FinancialGovernor fixture: 100 MiB budget = 104 857 600 bytes.
LIMIT_MB = 100
LIMIT_BYTES = LIMIT_MB * MIB


def fin_bytes(percent):
    """Bytes equal to `percent` % of the FinancialGovernor fixture budget."""
    return LIMIT_BYTES * percent // 100


# (projected bytes, risk_level, refused classes, refusal reason)
FINANCIAL_BANDS = (
    (1, "GREEN", NONE, None),
    (fin_bytes(80) - 1, "GREEN", NONE, None),
    (fin_bytes(80), "YELLOW", BULK_ONLY, "BUDGET CAUTION: BULK Dropped"),
    (fin_bytes(95) - 1, "YELLOW", BULK_ONLY, "BUDGET CAUTION: BULK Dropped"),
    (fin_bytes(95), "ORANGE", LOW_AND_BULK, "CRITICAL RESERVE: LOW/BULK Dropped"),
    (fin_bytes(100) - 1, "ORANGE", LOW_AND_BULK, "CRITICAL RESERVE: LOW/BULK Dropped"),
    (fin_bytes(100), "RED", NON_CRITICAL, "BUDGET EXHAUSTED: Only CRITICAL (0) Allowed"),
    (fin_bytes(150), "RED", NON_CRITICAL, "BUDGET EXHAUSTED: Only CRITICAL (0) Allowed"),
)

# PowerGovernor fixture: 1000 J budget at 1 J/byte, so cost in J = bytes.
BUDGET_J = 1000.0
J_PER_BYTE = 1.0

# (projected joules, risk_level, refused classes, refusal reason)
POWER_BANDS = (
    (1, "GREEN", NONE, None),
    (849, "GREEN", NONE, None),
    (850, "YELLOW", BULK_ONLY, "POWER SAVE MODE: BULK Dropped"),
    (979, "YELLOW", BULK_ONLY, "POWER SAVE MODE: BULK Dropped"),
    (980, "RED", NON_CRITICAL, "POWER BUDGET EMPTY"),
    (1000, "RED", NON_CRITICAL, "POWER BUDGET EMPTY"),
    (1500, "RED", NON_CRITICAL, "POWER BUDGET EMPTY"),
)


class TransmissionDecisionTest(unittest.TestCase):

    def test_field_names_and_order(self):
        names = [f.name for f in dataclasses.fields(TransmissionDecision)]
        self.assertEqual(names, ["allowed", "reason", "cost_incurred", "risk_level"])

    def test_priority_classes_match_pbs_prio_01(self):
        self.assertEqual(
            [(p.name, p.value) for p in Priority],
            [("CRITICAL", 0), ("HIGH", 1), ("NORMAL", 2), ("LOW", 3), ("BULK", 4)],
        )


class FinancialGovernorThresholdTest(unittest.TestCase):

    def test_every_band_and_class(self):
        for size, risk, refused, refusal_reason in FINANCIAL_BANDS:
            for priority in Priority:
                with self.subTest(bytes=size, priority=priority.name):
                    gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
                    d = gov.check_transmission(size, priority)
                    expect_allowed = priority not in refused
                    self.assertIsInstance(d, TransmissionDecision)
                    self.assertIs(d.allowed, expect_allowed)
                    self.assertEqual(d.risk_level, risk)
                    self.assertEqual(
                        d.reason, "Within Budget" if expect_allowed else refusal_reason)
                    self.assertEqual(d.cost_incurred, size / MIB)
                    self.assertEqual(gov.used_bytes, size if expect_allowed else 0)

    def test_only_four_risk_levels(self):
        levels = set()
        for percent in range(0, 151):
            gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
            levels.add(gov.check_transmission(fin_bytes(percent), Priority.CRITICAL).risk_level)
        self.assertEqual(levels, {"GREEN", "YELLOW", "ORANGE", "RED"})

    def test_cost_incurred_is_mib(self):
        gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
        self.assertEqual(gov.check_transmission(5 * MIB, Priority.BULK).cost_incurred, 5.0)


class FinancialGovernorProjectedUsageTest(unittest.TestCase):

    def test_threshold_applies_to_used_plus_packet(self):
        gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
        self.assertTrue(gov.check_transmission(fin_bytes(79), Priority.NORMAL).allowed)

        # Current usage 79 %; this packet would take it to 80 %.
        d = gov.check_transmission(fin_bytes(1), Priority.BULK)
        self.assertFalse(d.allowed)
        self.assertEqual(d.risk_level, "YELLOW")
        self.assertEqual(gov.used_bytes, fin_bytes(79))

        # One byte smaller keeps projected usage below 80 %.
        d = gov.check_transmission(fin_bytes(1) - 1, Priority.BULK)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")
        self.assertEqual(gov.used_bytes, fin_bytes(80) - 1)

    def test_admitted_packets_accumulate_refused_do_not(self):
        gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
        sent = 0
        for _ in range(25):
            if gov.check_transmission(5 * MIB, Priority.BULK).allowed:
                sent += 1
        # 15 x 5 MiB = 75 MiB admitted; the 16th would project to 80 %.
        self.assertEqual(sent, 15)
        self.assertEqual(gov.used_bytes, 75 * MIB)

    def test_critical_admitted_beyond_budget(self):
        gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
        gov.check_transmission(LIMIT_BYTES, Priority.CRITICAL)
        for _ in range(3):
            d = gov.check_transmission(10 * MIB, Priority.CRITICAL)
            self.assertTrue(d.allowed)
            self.assertEqual(d.risk_level, "RED")
        self.assertEqual(gov.used_bytes, LIMIT_BYTES + 30 * MIB)

    def test_get_status(self):
        gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
        gov.check_transmission(50 * MIB, Priority.NORMAL)
        self.assertEqual(gov.get_status(), "DATA USAGE: 50.00 MB (50.0%)")


class FinancialGovernorResetTest(unittest.TestCase):

    def test_usage_resets_after_24_hours(self):
        with mock.patch.object(pbs_risk_mgmt.time, "time", return_value=T0) as clock:
            gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
            gov.check_transmission(fin_bytes(90), Priority.CRITICAL)

            # Exactly 86 400 s later: same period, BULK still refused.
            clock.return_value = T0 + BUDGET_PERIOD_S
            self.assertFalse(gov.check_transmission(MIB, Priority.BULK).allowed)
            self.assertEqual(gov.used_bytes, fin_bytes(90))

            # More than 86 400 s later: new period starting now.
            clock.return_value = T0 + BUDGET_PERIOD_S + 1
            d = gov.check_transmission(MIB, Priority.BULK)
            self.assertTrue(d.allowed)
            self.assertEqual(d.risk_level, "GREEN")
            self.assertEqual(gov.used_bytes, MIB)
            self.assertEqual(gov.last_reset_time, T0 + BUDGET_PERIOD_S + 1)

    def test_next_period_starts_at_the_reset(self):
        t1 = T0 + BUDGET_PERIOD_S + 3600
        with mock.patch.object(pbs_risk_mgmt.time, "time", return_value=T0) as clock:
            gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
            clock.return_value = t1
            gov.check_transmission(fin_bytes(90), Priority.CRITICAL)  # resets at t1

            clock.return_value = t1 + BUDGET_PERIOD_S
            self.assertEqual(gov.used_bytes, fin_bytes(90))
            self.assertFalse(gov.check_transmission(MIB, Priority.BULK).allowed)

            clock.return_value = t1 + BUDGET_PERIOD_S + 1
            self.assertTrue(gov.check_transmission(MIB, Priority.BULK).allowed)
            self.assertEqual(gov.used_bytes, MIB)

    def test_get_status_reports_current_period(self):
        with mock.patch.object(pbs_risk_mgmt.time, "time", return_value=T0) as clock:
            gov = FinancialGovernor(daily_limit_mb=LIMIT_MB)
            gov.check_transmission(50 * MIB, Priority.NORMAL)
            clock.return_value = T0 + BUDGET_PERIOD_S + 1
            self.assertEqual(gov.get_status(), "DATA USAGE: 0.00 MB (0.0%)")

    def test_period_is_24_hours(self):
        self.assertEqual(BUDGET_PERIOD_S, 24 * 3600)


class PowerGovernorThresholdTest(unittest.TestCase):

    def test_every_band_and_class(self):
        for cost, risk, refused, refusal_reason in POWER_BANDS:
            for priority in Priority:
                with self.subTest(joules=cost, priority=priority.name):
                    gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
                    d = gov.check_transmission(cost, priority, current_battery_level=1.0)
                    expect_allowed = priority not in refused
                    self.assertIsInstance(d, TransmissionDecision)
                    self.assertIs(d.allowed, expect_allowed)
                    self.assertEqual(d.risk_level, risk)
                    self.assertEqual(
                        d.reason, "Power Nominal" if expect_allowed else refusal_reason)
                    self.assertEqual(d.cost_incurred, cost * J_PER_BYTE)
                    self.assertEqual(gov.used_joules, cost if expect_allowed else 0)

    def test_no_orange_level(self):
        levels = set()
        for cost in range(0, 1501):
            gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
            levels.add(gov.check_transmission(cost, Priority.CRITICAL, 1.0).risk_level)
        self.assertEqual(levels, {"GREEN", "YELLOW", "RED"})

    def test_threshold_applies_to_used_plus_packet(self):
        gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
        self.assertTrue(gov.check_transmission(840, Priority.NORMAL, 1.0).allowed)

        # Current usage 84 %; this packet would take it to 85 %.
        d = gov.check_transmission(10, Priority.BULK, 1.0)
        self.assertFalse(d.allowed)
        self.assertEqual(d.risk_level, "YELLOW")
        self.assertEqual(gov.used_joules, 840)

        d = gov.check_transmission(9, Priority.BULK, 1.0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")
        self.assertEqual(gov.used_joules, 849)

    def test_critical_admitted_beyond_budget(self):
        gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
        gov.check_transmission(1000, Priority.CRITICAL, 1.0)
        d = gov.check_transmission(500, Priority.CRITICAL, 1.0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "RED")
        self.assertEqual(gov.used_joules, 1500)

    def test_readme_example(self):
        gov = PowerGovernor(daily_budget_joules=5000, joules_per_byte=0.002)
        gov.set_hard_cutoff(battery_level=0.20)
        d = gov.check_transmission(
            packet_size_bytes=1024, priority=Priority.NORMAL, current_battery_level=0.35)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")
        self.assertAlmostEqual(d.cost_incurred, 2.048)


class PowerGovernorResetTest(unittest.TestCase):

    def test_usage_resets_after_24_hours(self):
        with mock.patch.object(pbs_risk_mgmt.time, "time", return_value=T0) as clock:
            gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
            gov.check_transmission(990, Priority.CRITICAL, 1.0)

            # Exactly 86 400 s later: same period, RED, HIGH refused.
            clock.return_value = T0 + BUDGET_PERIOD_S
            d = gov.check_transmission(10, Priority.HIGH, 1.0)
            self.assertFalse(d.allowed)
            self.assertEqual(d.risk_level, "RED")
            self.assertEqual(gov.used_joules, 990)

            # More than 86 400 s later: new period starting now.
            clock.return_value = T0 + BUDGET_PERIOD_S + 1
            d = gov.check_transmission(10, Priority.HIGH, 1.0)
            self.assertTrue(d.allowed)
            self.assertEqual(d.risk_level, "GREEN")
            self.assertEqual(gov.used_joules, 10)
            self.assertEqual(gov.last_reset_time, T0 + BUDGET_PERIOD_S + 1)

    def test_reset_applies_on_a_blackout_call(self):
        with mock.patch.object(pbs_risk_mgmt.time, "time", return_value=T0) as clock:
            gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
            gov.set_hard_cutoff(0.20)
            gov.check_transmission(990, Priority.CRITICAL, 1.0)

            clock.return_value = T0 + BUDGET_PERIOD_S + 1
            d = gov.check_transmission(10, Priority.LOW, current_battery_level=0.10)
            self.assertEqual(d.risk_level, "BLACKOUT")
            self.assertEqual(gov.used_joules, 0)
            self.assertEqual(gov.last_reset_time, T0 + BUDGET_PERIOD_S + 1)


class PowerGovernorHardCutoffTest(unittest.TestCase):

    def setUp(self):
        self.gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
        self.gov.set_hard_cutoff(battery_level=0.20)

    def test_below_cutoff_refuses_all_but_critical(self):
        for priority in NON_CRITICAL:
            with self.subTest(priority=priority.name):
                d = self.gov.check_transmission(10, priority, current_battery_level=0.19)
                self.assertFalse(d.allowed)
                self.assertEqual(d.risk_level, "BLACKOUT")
                self.assertEqual(d.reason, "BATTERY CRITICAL: Hard Cutoff")
                self.assertEqual(d.cost_incurred, 0)
        self.assertEqual(self.gov.used_joules, 0)

    def test_below_cutoff_critical_gets_budget_decision(self):
        d = self.gov.check_transmission(10, Priority.CRITICAL, current_battery_level=0.19)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")
        self.assertEqual(d.cost_incurred, 10)
        self.assertEqual(self.gov.used_joules, 10)

        d = self.gov.check_transmission(980, Priority.CRITICAL, current_battery_level=0.0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "RED")
        self.assertEqual(self.gov.used_joules, 990)

    def test_cutoff_precedes_budget_check(self):
        # 900 J would be YELLOW on budget alone; below the cutoff it is BLACKOUT.
        d = self.gov.check_transmission(900, Priority.HIGH, current_battery_level=0.10)
        self.assertEqual(d.risk_level, "BLACKOUT")

    def test_level_equal_to_cutoff_passes(self):
        d = self.gov.check_transmission(10, Priority.BULK, current_battery_level=0.20)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")

    def test_default_cutoff_is_zero(self):
        gov = PowerGovernor(BUDGET_J, J_PER_BYTE)
        self.assertEqual(gov.hard_cutoff_percent, 0.0)
        d = gov.check_transmission(10, Priority.BULK, current_battery_level=0.0)
        self.assertTrue(d.allowed)
        self.assertEqual(d.risk_level, "GREEN")


if __name__ == "__main__":
    unittest.main()
