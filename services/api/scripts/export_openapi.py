#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from botcheck_api.main import app


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Export the FastAPI OpenAPI schema to a JSON file."
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Output file path for the OpenAPI JSON schema",
    )
    args = parser.parse_args()

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    schema = app.openapi()
    output_path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote OpenAPI schema to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
