"""Income Passport generation, PDF, public verify, revoke, rate-limit, token hashing."""

from __future__ import annotations

import hashlib

from payscore.income_passport import reset_passport_store


def setup_function():
    reset_passport_store()


def test_generate_passport_and_pdf(client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_FRONTEND_URL", "https://demo.example/")
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "test-signing-key")
    response = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001",
        "persona": "priya",
        "ttl_days": 30,
        "include_pdf_share": False,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["passport_reference"].startswith("IPP-")
    assert body["verification_token"]
    assert body["verification_path"] == f"/verify/income-passport/{body['verification_token']}"
    assert body["verification_url"] == f"https://demo.example/verify/income-passport/{body['verification_token']}"
    assert "applicant_id" in body
    # Snapshot classifies income — fixture, not independently bank-verified.
    total = body["snapshot"]["income_summary"]["total_verified_income_inr"]
    assert total["classification"] == "fixture_aggregate"
    assert isinstance(total["value"], (int, float))

    pdf = client.get(
        f"/income-passport/{body['passport_id']}/pdf",
        params={"applicant_id": "PSC-PRIYA-001"},
    )
    assert pdf.status_code == 200
    assert pdf.headers["content-type"].startswith("application/pdf")
    assert pdf.content.startswith(b"%PDF")
    assert b"Income Passport" in pdf.content
    assert body["passport_reference"].encode() in pdf.content
    expected_url = body["verification_url"].encode()
    assert expected_url in pdf.content
    assert body["verification_token"].encode() in pdf.content
    assert b"/Subtype /Link" in pdf.content
    assert b"/S /URI" in pdf.content


def test_pdf_uses_path_when_frontend_origin_missing(client, monkeypatch):
    monkeypatch.delenv("PAYSCORE_FRONTEND_URL", raising=False)
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    assert "verification_url" not in created
    assert created["verification_path"].startswith("/verify/income-passport/")
    pdf = client.get(
        f"/income-passport/{created['passport_id']}/pdf",
        params={"applicant_id": "PSC-PRIYA-001"},
    )
    assert pdf.status_code == 200
    assert created["verification_path"].encode() in pdf.content
    assert created["verification_token"].encode() in pdf.content


def test_token_exists_before_pdf_generation(client, monkeypatch):
    """Regression: PDF must receive the real token, not a placeholder."""
    monkeypatch.setenv("PAYSCORE_FRONTEND_URL", "http://frontend.test")
    from payscore import income_passport as mod
    from payscore import income_passport_pdf as pdf_mod

    captured: dict = {}
    original = pdf_mod.build_passport_pdf

    def wrapper(**kwargs):
        captured.update(kwargs)
        assert kwargs.get("verification_url")
        assert "{token}" not in str(kwargs.get("verification_url"))
        return original(**kwargs)

    monkeypatch.setattr(pdf_mod, "build_passport_pdf", wrapper)
    monkeypatch.setattr(mod, "build_passport_pdf", wrapper)

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    assert captured["verification_url"].endswith(created["verification_token"])
    assert created["verification_token"] in captured["verification_url"]


def test_duplicate_generation_blocked(client):
    payload = {"applicant_id": "PSC-PRIYA-001", "persona": "priya"}
    assert client.post("/income-passport", json=payload).status_code == 200
    second = client.post("/income-passport", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "passport_already_active"


def test_public_verify_hides_private_fields(client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "test-signing-key")
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya", "include_pdf_share": False,
    }).json()
    token = created["verification_token"]
    public = client.get(f"/api/verify/income-passport/{token}")
    assert public.status_code == 200
    body = public.json()
    assert body["passport_reference"] == created["passport_reference"]
    assert body["integrity_status"] == "valid"
    assert body["content_integrity"] == "valid"
    assert "verification_token" not in body
    assert "applicant_id" not in body
    assert "snapshot" not in body
    assert "pdf_bytes" not in body
    assert "token_hash" not in str(body)
    assert "content_hmac" not in str(body)
    assert "signing" not in str(body).lower()
    assert "limited_financial_summary" in body
    # PDF not shared by default
    pdf = client.get(f"/api/verify/income-passport/{token}/pdf")
    assert pdf.status_code == 403


def test_invalid_token(client):
    response = client.get("/api/verify/income-passport/this-token-is-not-real-at-all-000")
    assert response.status_code == 404
    assert response.json()["error"] == "invalid_token"


def test_revoke_passport(client):
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    token = created["verification_token"]
    revoked = client.post(
        f"/income-passport/{created['passport_id']}/revoke",
        params={"applicant_id": "PSC-PRIYA-001"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["integrity_status"] == "revoked"
    public = client.get(f"/api/verify/income-passport/{token}")
    assert public.status_code == 200
    assert public.json()["integrity_status"] == "revoked"


def test_token_stored_as_hash_only(client, monkeypatch):
    from payscore import income_passport as mod

    monkeypatch.setenv("PAYSCORE_FRONTEND_URL", "http://frontend.test")
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-ARJUN-002", "persona": "arjun",
    }).json()
    token = created["verification_token"]
    expected = hashlib.sha256(token.encode()).hexdigest()
    record = mod._PASSPORTS[created["passport_id"]]
    assert record["token_hash"] == expected
    assert token not in {v for v in record.values() if isinstance(v, str)}
    # PDF intentionally embeds the public verification URL (includes the token).
    assert token.encode() in record["pdf_bytes"]


def test_public_pdf_when_enabled(client):
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-ROHAN-003", "persona": "rohan", "include_pdf_share": True,
    }).json()
    pdf = client.get(f"/api/verify/income-passport/{created['verification_token']}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")


def test_get_active_passport(client):
    assert client.get("/income-passport", params={"applicant_id": "PSC-PRIYA-001"}).status_code == 404
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    got = client.get("/income-passport", params={"applicant_id": "PSC-PRIYA-001"})
    assert got.status_code == 200
    assert got.json()["passport_id"] == created["passport_id"]
    # Token is not re-emitted on GET
    assert "verification_token" not in got.json()


def test_expired_passport_integrity(client):
    from datetime import datetime, timedelta, timezone

    from payscore import income_passport as mod

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    record = mod._PASSPORTS[created["passport_id"]]
    record["expires_at_utc"] = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat(timespec="seconds")
    public = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert public.status_code == 200
    assert public.json()["integrity_status"] == "expired"


def test_content_hmac_detects_tampering(client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "unit-test-passport-key")
    from payscore import income_passport as mod

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    record = mod._PASSPORTS[created["passport_id"]]
    assert record.get("content_hmac")
    # Unmodified passport verifies cleanly.
    ok = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert ok.status_code == 200
    assert ok.json()["integrity_status"] == "valid"
    assert ok.json()["content_integrity"] == "valid"

    # Mutate snapshot after issuance.
    record["snapshot"]["income_summary"]["total_verified_income_inr"]["value"] = 1
    tampered = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert tampered.status_code == 200
    assert tampered.json()["integrity_status"] == "tampered"
    assert tampered.json()["content_integrity"] == "tampered"


def test_missing_signature_reports_unsigned(client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "unit-test-passport-key")
    from payscore import income_passport as mod

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    record = mod._PASSPORTS[created["passport_id"]]
    record["content_hmac"] = None
    public = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert public.status_code == 200
    assert public.json()["content_integrity"] == "unsigned"
    assert public.json()["integrity_status"] == "valid"


def test_wrong_signing_key_marks_tampered(client, monkeypatch):
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "original-key")

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    monkeypatch.setenv("PAYSCORE_PASSPORT_SIGNING_KEY", "different-key")
    public = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert public.status_code == 200
    assert public.json()["content_integrity"] == "tampered"
    assert public.json()["integrity_status"] == "tampered"
    # Secrets never appear in the response.
    assert "original-key" not in public.text
    assert "different-key" not in public.text


def test_unsigned_when_signing_key_absent(client, monkeypatch):
    monkeypatch.delenv("PAYSCORE_PASSPORT_SIGNING_KEY", raising=False)
    from payscore import income_passport as mod

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya",
    }).json()
    record = mod._PASSPORTS[created["passport_id"]]
    assert record.get("content_hmac") is None
    public = client.get(f"/api/verify/income-passport/{created['verification_token']}")
    assert public.status_code == 200
    assert public.json()["content_integrity"] == "unavailable"
    assert public.json()["integrity_status"] == "valid"
