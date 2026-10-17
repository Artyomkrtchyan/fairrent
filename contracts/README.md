# C01 shared contracts

Proposal v0.1.0, pending component-owner agreement. No running API is implied.

- `openapi.json`: generated OpenAPI 3.1 for all seven endpoints.
- `fixtures.json`: synthetic scenarios with `{schema, value}` wrappers; mocks return `value`.
- `generate.py`: editable stdlib-only source for schemas and examples.
- `validate.py`: OpenAPI, fixture and negative-input checks.

From repository root:

```bash
python contracts/generate.py
python -m pip install -r contracts/requirements.txt
python contracts/validate.py
```

See [normative semantics and pending owner approvals](../docs/contract-semantics.md).
