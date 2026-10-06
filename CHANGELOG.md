# Changelog

All notable changes to `pbs_risk_mgmt.py` and its documentation are recorded here.

## 2026-10-06

### Changed (behaviour)

- `PowerGovernor` resets `used_joules` to zero on the first `check_transmission()` call made more than 86 400 s after the previous reset or after construction, the same 24 h rule as `FinancialGovernor`. Previously the energy budget never reset.
- `FinancialGovernor(strict_mode=False)` selects advisory mode: decisions report `risk_level` and the refusal reason prefixed `ADVISORY, not enforced: `, and every packet is admitted. Previously `strict_mode` was stored but never read. Callers using the default, `strict_mode=True`, get identical decisions.
- Both governors raise `ValueError` for a priority outside 0–4 (PBS-PRIO-01 v1.4 Sections 5.1 and 11). Previously any integer was accepted.

### Fixed (documentation)

- README "Shedding logic" documents each governor separately: `FinancialGovernor` at 80 / 95 / 100 % and `PowerGovernor` at 85 / 98 %, both on projected usage, and the `PowerGovernor` hard cutoff, below which only CRITICAL is admitted (`risk_level` `BLACKOUT`). The README previously gave one table for both and said the cutoff silences the radio.
- Install instructions clone the repository by its actual name and run the module directly; there is no package to `pip install`.
- Docstrings, the `PBS-PRIO-01 v1.4` reference and the demo output state what the code does.

### Added

- `tests/test_governors.py`: 32 standard-library unit tests covering every threshold boundary, projected usage, CRITICAL admission, the hard cutoff, the 24 h reset and advisory mode.
- GitHub Actions workflow `.github/workflows/tests.yml`: unit tests and the demo on Python 3.8, 3.10 and 3.12.
