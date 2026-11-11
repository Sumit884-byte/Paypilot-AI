import json
import os
from pathlib import Path

import pytest

# Tests must never see a developer's PayPal credentials or call real PayPal: skip .env and clear any exported values.
# Tests that need credentials set fake ones themselves.
os.environ["PAYSCORE_SKIP_DOTENV"] = "1"
for _var in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID", "OPENAI_API_KEY"):
    os.environ.pop(_var, None)

ROOT = Path(__file__).resolve().parent.parent
PERSONA_DIR = ROOT / "fixtures" / "personas"
PERSONA_FILES = sorted(PERSONA_DIR.glob("*.json"))


@pytest.fixture(scope="session")
def personas():
    return {p.stem: json.loads(p.read_text(encoding="utf-8")) for p in PERSONA_FILES}


@pytest.fixture(scope="session")
def example_request():
    from payscore.schema import EXAMPLE_REQUEST
    return dict(EXAMPLE_REQUEST)


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient

    from payscore.api import create_app
    return TestClient(create_app())


@pytest.fixture(scope="session")
def fallback_client(tmp_path_factory):
    from fastapi.testclient import TestClient

    from payscore.api import create_app
    return TestClient(create_app(model_dir=tmp_path_factory.mktemp("empty"), allow_fallback=True))


@pytest.fixture(scope="session")
def valid_payload():
    """A valid /score request body (copy of the documented example)."""
    from payscore.schema import EXAMPLE_REQUEST
    return dict(EXAMPLE_REQUEST)


@pytest.fixture(scope="session")
def trained_dir(tmp_path_factory):
    """A small model trained fresh into a temp dir (fast; independent of the committed artifact)."""
    from payscore.train import train
    d = tmp_path_factory.mktemp("trained_model")
    train(n_rows=6000, seed=42, out_dir=d, num_boost_round=150, early_stopping_rounds=20)
    return d
