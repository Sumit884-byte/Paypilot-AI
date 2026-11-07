"""Income Passport generation, PDF, public verify, revoke, rate-limit, token hashing."""

from __future__ import annotations

import hashlib

from payscore.income_passport import reset_passport_store


def setup_function():
    reset_passport_store()


def test_generate_passport_and_pdf(client):
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
    assert body["verification_path"].startswith("/verify/income-passport/")
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


def test_duplicate_generation_blocked(client):
    payload = {"applicant_id": "PSC-PRIYA-001", "persona": "priya"}
    assert client.post("/income-passport", json=payload).status_code == 200
    second = client.post("/income-passport", json=payload)
    assert second.status_code == 409
    assert second.json()["error"] == "passport_already_active"


def test_public_verify_hides_private_fields(client):
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-PRIYA-001", "persona": "priya", "include_pdf_share": False,
    }).json()
    token = created["verification_token"]
    public = client.get(f"/verify/income-passport/{token}")
    assert public.status_code == 200
    body = public.json()
    assert body["passport_reference"] == created["passport_reference"]
    assert body["integrity_status"] == "valid"
    assert "verification_token" not in body
    assert "applicant_id" not in body
    assert "snapshot" not in body
    assert "pdf_bytes" not in body
    assert "token_hash" not in str(body)
    assert "limited_financial_summary" in body
    # PDF not shared by default
    pdf = client.get(f"/verify/income-passport/{token}/pdf")
    assert pdf.status_code == 403


def test_invalid_token(client):
    response = client.get("/verify/income-passport/this-token-is-not-real-at-all-000")
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
    public = client.get(f"/verify/income-passport/{token}")
    assert public.status_code == 200
    assert public.json()["integrity_status"] == "revoked"


def test_token_stored_as_hash_only(client):
    from payscore import income_passport as mod

    created = client.post("/income-passport", json={
        "applicant_id": "PSC-ARJUN-001", "persona": "arjun",
    }).json()
    token = created["verification_token"]
    expected = hashlib.sha256(token.encode()).hexdigest()
    record = mod._PASSPORTS[created["passport_id"]]
    assert record["token_hash"] == expected
    assert token not in record.values()
    assert token.encode() not in record["pdf_bytes"]


def test_public_pdf_when_enabled(client):
    created = client.post("/income-passport", json={
        "applicant_id": "PSC-ROHAN-001", "persona": "rohan", "include_pdf_share": True,
    }).json()
    pdf = client.get(f"/verify/income-passport/{created['verification_token']}/pdf")
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
    public = client.get(f"/verify/income-passport/{created['verification_token']}")
    assert public.status_code == 200
    assert public.json()["integrity_status"] == "expired"
