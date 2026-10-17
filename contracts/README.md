# C01 shared contracts

Proposal v0.2.0, incorporating B02 naming and frontend requirements; pending final owner agreement. No business API implementation is implied.

- `openapi.json`: generated OpenAPI 3.1 for nine endpoints, including infrastructure and USD/AMD display rates.
- `fixtures.json`: synthetic scenarios with `{schema, value}` wrappers; mocks return `value`.
- `generate.py`: editable stdlib-only source for schemas and examples.
- `integration.py`: B02/public-response mapping and frontend additions applied during generation.
- `validate.py`: OpenAPI, fixture and negative-input checks.

From repository root:

```bash
python contracts/generate.py
python -m pip install -r contracts/requirements.txt
python contracts/validate.py
```

See [normative semantics and pending owner approvals](../docs/contract-semantics.md).
