# Contributing

Issues and pull requests welcome.

## Reporting a bug

Open an issue with:

1. **The version** (from `pip show aranet-cloud` or `import aranet_cloud; aranet_cloud.__version__`).
2. **Python version** (`python --version`).
3. **A minimal reproducer** — ideally one of the existing tests in
   `tests/test_client.py` modified to demonstrate the bug.
4. **What you expected vs. what happened.**

For API-side issues (a request that succeeds in `curl` but fails through
the library, or vice versa), please include the **correlation ID** from
`AranetValidationError.correlation_id` if there is one — Aranet's support
team can trace it server-side.

## Development setup

```bash
git clone https://github.com/jasonjhofmann/aranet-cloud
cd aranet-cloud
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Lint, type-check, test
ruff check .
mypy src
pytest -v
```

## Adding support for a new endpoint

The Aranet OpenAPI spec lives at `docs/openapi.json`. If Aranet adds a
new endpoint:

1. Update `docs/openapi.json` from `https://aranet.cloud/api/openapi.json`.
2. Refresh `docs/api_enumeration.md` — it is a flattened, human-readable
   view of the schemas and paths in `openapi.json`; keep the two in sync.
3. Add a path constant to `src/aranet_cloud/const.py` under `Endpoint`.
4. Add the new response schema as a dataclass in
   `src/aranet_cloud/models.py`, with a `from_dict` classmethod that
   ignores unknown fields.
5. Add a corresponding method to `src/aranet_cloud/client.py`.
6. Re-export new public names from `src/aranet_cloud/__init__.py`.
7. Add tests in `tests/test_client.py` covering the happy path + error
   shapes for the new endpoint.

## Adding a new field to an existing schema

The `from_dict` classmethods are designed to be tolerant — adding a new
field is purely additive:

```python
@dataclass(slots=True, frozen=True)
class Sensor:
    id: str
    serial: str
    new_field: str = ""   # ← add with a sensible default

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Sensor:
        return cls(
            ...,
            new_field=_as_str(d.get("newField")),   # ← pull from the API JSON key
        )
```

Then add a test that exercises a payload containing the new field.

## Code style

- `ruff` config in `pyproject.toml`; CI enforces.
- `mypy --strict` clean; `Any` only where the API genuinely is dynamic.
- Docstrings: triple-quoted, first line a one-sentence summary, then a
  blank line, then any further detail. Prefer concrete examples over
  abstractions.
- Logging: `logging.getLogger("aranet_cloud")` at module level. DEBUG
  for per-request lines, WARNING for retried/transient failures. The
  caller owns user-facing error reporting (the lib raises typed
  exceptions rather than logging at ERROR). Never log the API key.

## Release process

1. Bump `version` in `pyproject.toml` and `src/aranet_cloud/__init__.py`.
2. Update `CHANGELOG.md` — move "Unreleased" items into a new
   `[X.Y.Z] — YYYY-MM-DD` section and refresh the compare links at the
   bottom.
3. Commit, tag `vX.Y.Z`, push the commit and the tag.
4. Publishing is automated: cutting a GitHub **Release** for the tag
   triggers `.github/workflows/publish.yml`, which runs `uv build` and
   uploads to PyPI via Trusted Publishing (OIDC — no stored token). For a
   local sanity build, `uv build` produces the same wheel + sdist under
   `dist/`.

## License

Contributions accepted under the same Apache 2.0 license as the rest of
the project.
