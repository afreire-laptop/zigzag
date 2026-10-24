"""Write the OpenAPI document, the authoritative transport contract, for client generation.

uv run python -m zigzag.contract openapi.json
"""

import json
import sys
import tempfile
from pathlib import Path

from zigzag.config import Config
from zigzag.main import build


def openapi_document(fixtures_path: Path) -> str:
    with tempfile.TemporaryDirectory() as data_dir:
        app = build(Config(model_mode="fixture", data_dir=Path(data_dir), fixtures_path=fixtures_path))
        return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    target = Path(argv[1] if len(argv) > 1 else "openapi.json")
    fixtures = Path(__file__).resolve().parents[4] / "fixtures" / "journeys.json"
    target.write_text(openapi_document(fixtures), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
