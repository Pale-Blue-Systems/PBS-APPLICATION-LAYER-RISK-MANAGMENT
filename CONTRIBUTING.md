# Contributing to PBS Application-Layer Risk Management

This repository holds the PBS application-layer resource governors in `pbs_risk_mgmt.py`, their tests and the budget simulation.

## Scope

Contributions must:

- Use the PBS-PRIO-01 v1.4 priority classes exactly as its Section 4 defines them: 0 CRITICAL, 1 HIGH, 2 NORMAL, 3 LOW, 4 BULK. Values 5–255 are reserved (Section 5); the governors reject them with `ValueError`.
- Preserve the shedding order: a governor refuses lower classes before higher classes and admits CRITICAL in every state.
- Update the README shedding tables and `tests/test_governors.py` in the same pull request as any change to a threshold, a reason string or a `TransmissionDecision` field.
- Follow the existing code style and documentation patterns.

## How to Contribute

1. **Open an Issue** — Describe the problem or enhancement before submitting code
2. **Fork and Branch** — Create a feature branch from `main`
3. **Submit a Pull Request** — Reference the issue and describe your changes

## Code Standards

- Python 3.8+ compatibility
- Type hints for public APIs
- Docstrings for classes and public methods
- No external dependencies beyond the Python standard library

## Testing

Run both commands from the repository root before opening a pull request:

```bash
python3 -m unittest discover -s tests -v
python3 examples/demo_budget.py
```

Add or update tests in `tests/test_governors.py` for every behaviour change. The tests use only the standard-library `unittest` module. The [tests workflow](.github/workflows/tests.yml) runs both commands on Python 3.8, 3.10 and 3.12 for every push and pull request.

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions

For questions about the PBS protocol specifications, see [PBS-PROTOCOL-OPEN](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN).
