import re
import shutil
import subprocess

from conftest import ROOT

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "models", "node_modules"}
# lockfiles carry npm/pip integrity hashes that look like the generic secret patterns but are public metadata
SKIP_FILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Pipfile.lock"}
PATTERNS = [r"client_secret\s*[:=]\s*['\"][^'\"]+", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\bA[A-Za-z0-9_-]{60,}\b", r"\bsk-[A-Za-z0-9]{20,}", r"Bearer\s+[A-Za-z0-9._-]{20,}"]


def _committable_files():
    """Files git would commit: tracked plus untracked-but-not-ignored. Falls back to a full walk without git."""
    if shutil.which("git") and (ROOT / ".git").exists():
        out = subprocess.run(["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             cwd=ROOT, capture_output=True, check=True).stdout.decode()
        return [ROOT / name for name in out.split("\0") if name]
    return list(ROOT.rglob("*"))


def test_no_secrets_or_env_files():
    assert not [p for p in ROOT.glob(".env") if p.is_file()]
    for p in _committable_files():
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(ROOT).parts) or p.suffix not in {
                ".py", ".md", ".json", ".txt", ".example", ".toml", ".ini"}:
            continue
        if p.name == "test_no_secrets.py" or p.name in SKIP_FILES:
            continue
        text = p.read_text(errors="ignore")
        for pat in PATTERNS:
            assert not re.search(pat, text), f"possible secret in {p}"


PAYPAL_SECRET_VARS = ["PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID"]


def test_no_paypal_network_calls_in_source():
    for p in (ROOT / "payscore").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        # live API host and non-httpx HTTP clients are forbidden; the sandbox host is allowed
        assert "api-m.paypal.com" not in text and "requests." not in text


def test_no_hardcoded_paypal_credentials():
    for p in ROOT.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(ROOT).parts) or p.suffix not in {
                ".py", ".example", ".toml", ".ini"}:
            continue
        if p.name == "test_no_secrets.py":
            continue
        for line in p.read_text(errors="ignore").splitlines():
            stripped = line.split("#", 1)[0]
            for var in PAYPAL_SECRET_VARS:
                assert not re.search(rf"{var}\s*=\s*['\"][^'\"]", stripped), f"hardcoded value for {var} in {p}"
                assert not re.search(rf"{var}\s*:\s*['\"][^'\"]", stripped), f"hardcoded value for {var} in {p}"


def test_paypal_mode_is_sandbox_only():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert re.search(r"PAYPAL_MODE\s*=\s*sandbox", example)
    assert not re.search(r"PAYPAL_MODE\s*=\s*live", example), "live mode offered in .env.example"
    for p in (ROOT / "payscore").glob("*.py"):
        text = p.read_text(encoding="utf-8")
        assert "api-m.paypal.com" not in text, f"live PayPal host in {p}"
        assert not re.search(r"PAYPAL_MODE\s*=\s*['\"]?live\b", text), f"live mode default in {p}"
        assert "MODE_LIVE" not in text and "enable_live" not in text, f"live-mode toggle in {p}"


def test_client_refuses_live_mode_and_host():
    """Behavioural guard: the PayPal client must reject live mode and the live API host outright."""
    import httpx
    import pytest

    from payscore.paypal import PayPalClient, PayPalError

    creds = {"client_id": "test-id", "client_secret": "test-secret"}
    with pytest.raises(PayPalError, match="sandbox-only"):
        PayPalClient(api_base="https://api-m.paypal.com", **creds)
    import os
    os.environ["PAYPAL_MODE"] = "live"
    try:
        with pytest.raises(PayPalError, match="sandbox-only"):
            PayPalClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)), **creds)
    finally:
        del os.environ["PAYPAL_MODE"]
