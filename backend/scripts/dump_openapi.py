"""Write the API's OpenAPI schema to ``packages/core/openapi.json``.

That file is the contract the shared TypeScript package generates its types
from, and ``tests/test_openapi_contract.py`` fails when it drifts from the
running app. Re-run this after any change to a route or response schema::

    python -m scripts.dump_openapi
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.main import app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "packages" / "core" / "openapi.json"

# release-please rewrites the app version on every release; leaving it in the
# snapshot would turn each release into a spurious contract change.
VERSION_PLACEHOLDER = "0.0.0"


def build_contract_schema() -> dict[str, Any]:
    schema = app.openapi()
    return {**schema, "info": {**schema["info"], "version": VERSION_PLACEHOLDER}}


def render_contract(schema: dict[str, Any]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


if __name__ == "__main__":
    CONTRACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONTRACT_PATH.write_text(render_contract(build_contract_schema()), encoding="utf-8")
    print(f"wrote {CONTRACT_PATH}")
