import json
import subprocess
import sys

import pytest
from conftest import PERSONA_FILES, ROOT


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["model_loaded"] is True
    assert body["development_fallback_active"] is False


def test_root_and_openapi(client):
    assert client.get("/").json()["endpoints"]["score"] == "POST /score"
    paths = client.get("/openapi.json").json()["paths"]
    assert "/score" in paths and "/health" in paths


def test_score_example(client, example_request):
    r = client.post("/score", json=example_request)
    assert r.status_code == 200
    b = r.json()
    assert b["applicant_id"] == example_request["applicant_id"]
    assert b["score_range"] == {"min": 300, "max": 850}
    assert b["risk_band"] in {"low", "moderate", "elevated", "high"}


def test_personas_through_api_order(client, personas):
    s = {n: client.post("/score", json=p["model_input"]).json()["score"] for n, p in personas.items()}
    assert s["priya"] > s["arjun"] > s["rohan"]
    assert s["priya"] >= 720 and s["rohan"] < 650


def test_validation_error_shape_and_no_echo(client, example_request):
    r = client.post("/score", json={**example_request, "age_years": 5, "applicant_id": "secret name@x.com"})
    assert r.status_code == 422
    b = r.json()
    assert b["error"] == "validation_error"
    assert {d["field"] for d in b["detail"]} >= {"age_years", "applicant_id"}
    assert "secret name" not in r.text


def test_unknown_field_422(client, example_request):
    assert client.post("/score", json={**example_request, "email": "a@b.c"}).status_code == 422


def test_malformed_json_422(client):
    r = client.post("/score", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_null_optionals_ok(client, example_request):
    body = {**example_request, "revenue_volatility_cv": None, "prior_defaults_count": None}
    r = client.post("/score", json=body)
    assert r.status_code == 200
    assert set(r.json()["missing_inputs"]) == {"revenue_volatility_cv", "prior_defaults_count"}


def test_fallback_mode_api(fallback_client, example_request):
    assert fallback_client.get("/health").json()["development_fallback_active"] is True
    b = fallback_client.post("/score", json=example_request).json()
    assert b["model"]["type"] == "development_fallback"


def test_503_when_no_model_and_no_fallback(tmp_path, example_request):
    from fastapi.testclient import TestClient

    from payscore.api import create_app
    c = TestClient(create_app(model_dir=tmp_path, allow_fallback=False))
    r = c.post("/score", json=example_request)
    assert r.status_code == 503 and r.json()["error"] == "model_unavailable"


def test_cors_allows_configured_origin_only(client):
    ok = client.options("/score", headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"})
    bad = client.options("/score", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    assert "access-control-allow-origin" not in bad.headers


@pytest.mark.parametrize("path", PERSONA_FILES, ids=lambda p: p.stem)
def test_cli_predict_on_persona(path):
    out = subprocess.run([sys.executable, "-m", "payscore.predict", "--input", str(path)],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert 300 <= json.loads(out.stdout)["score"] <= 850


def test_cli_rejects_invalid_input(tmp_path):
    f = tmp_path / "bad.json"
    f.write_text(json.dumps({"applicant_id": "x"}))
    out = subprocess.run([sys.executable, "-m", "payscore.predict", "--input", str(f)],
                         cwd=ROOT, capture_output=True, text=True)
    assert out.returncode == 2
