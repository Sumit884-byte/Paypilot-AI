"""Score a JSON file from the command line (inference script).

    python -m payscore.predict --input fixtures/personas/priya.json
Accepts a raw request body or a persona fixture (uses its ``model_input``).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from pydantic import ValidationError

from .model import DEFAULT_MODEL_DIR, Scorer
from .schema import ScoreRequest


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True)
    ap.add_argument("--model-dir", default=str(DEFAULT_MODEL_DIR))
    ap.add_argument("--no-fallback", action="store_true", help="fail instead of using the development fallback")
    a = ap.parse_args(argv)
    payload = json.loads(Path(a.input).read_text(encoding="utf-8"))
    payload = payload.get("model_input", payload)
    try:
        req = ScoreRequest.model_validate(payload)
    except ValidationError as exc:
        print(exc, file=sys.stderr)
        return 2
    scorer = Scorer.from_dir(a.model_dir, allow_fallback=not a.no_fallback)
    if not scorer.available:
        print("error: no trained model found (run `python -m payscore.train`)", file=sys.stderr)
        return 3
    print(json.dumps(scorer.score(req), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
