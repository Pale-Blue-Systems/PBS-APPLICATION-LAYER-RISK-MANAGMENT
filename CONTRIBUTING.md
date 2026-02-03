# Contributing to PBS Application-Layer Risk Management

Thank you for your interest in contributing to the Pale Blue Systems open standards ecosystem.

## Scope

This repository provides application-layer resource governors for PBS-compliant systems. Contributions should:

- Align with PBS-PRIO-01 priority semantics
- Maintain compatibility with the PBS Core v1 specification
- Follow the existing code style and documentation patterns

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

Run the demo simulation to verify your changes:

```bash
python examples/demo_budget.py
```

## License

By contributing, you agree that your contributions will be licensed under the Apache License 2.0.

## Questions

For questions about the PBS protocol specifications, see [PBS-PROTOCOL-OPEN](https://github.com/Pale-Blue-Systems/PBS-PROTOCOL-OPEN).
