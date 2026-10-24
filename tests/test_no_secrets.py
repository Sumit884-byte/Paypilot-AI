import re

from conftest import ROOT

SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".ruff_cache", "models"}
PATTERNS = [r"client_secret\s*[:=]\s*['\"][^'\"]+", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
            r"\bA[A-Za-z0-9_-]{60,}\b", r"\bsk-[A-Za-z0-9]{20,}", r"Bearer\s+[A-Za-z0-9._-]{20,}"]


def test_no_secrets_or_env_files():
    assert not [p for p in ROOT.glob(".env") if p.is_file()]
    for p in ROOT.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(ROOT).parts) or p.suffix not in {
                ".py", ".md", ".json", ".txt", ".example", ".toml", ".ini"}:
            continue
        if p.name == "test_no_secrets.py":
            continue
        text = p.read_text(errors="ignore")
        for pat in PATTERNS:
            assert not re.search(pat, text), f"possible secret in {p}"


def test_no_paypal_network_calls_in_source():
    for p in (ROOT / "payscore").glob("*.py"):
        text = p.read_text()
        assert "api-m.paypal.com" not in text and "api-m.sandbox.paypal.com" not in text and "requests." not in text
