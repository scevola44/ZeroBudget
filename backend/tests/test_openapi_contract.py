"""The committed OpenAPI snapshot must match the running app.

``packages/core`` generates its TypeScript types from that snapshot, so a route
or response-schema change that is not reflected in it silently leaves the web
and mobile clients on stale types.
"""

from scripts.dump_openapi import CONTRACT_PATH, build_contract_schema, render_contract


def test_committed_openapi_snapshot_matches_the_app() -> None:
    assert CONTRACT_PATH.exists(), "run `python -m scripts.dump_openapi` from backend/"

    committed = CONTRACT_PATH.read_text(encoding="utf-8")

    assert committed == render_contract(build_contract_schema()), (
        "packages/core/openapi.json is out of date with the API. "
        "Run `python -m scripts.dump_openapi` from backend/, then "
        "`npm run gen:types -w @zerobudget/core`, and commit both."
    )
