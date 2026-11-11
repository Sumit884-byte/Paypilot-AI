"""scripts/configure_paypal.py writes credentials into .env and never prints them."""

import importlib.util

from conftest import ROOT

spec = importlib.util.spec_from_file_location("configure_paypal", ROOT / "scripts" / "configure_paypal.py")
configure = importlib.util.module_from_spec(spec)
spec.loader.exec_module(configure)

FAKE_ID, FAKE_SECRET = "AfakeClientIdForTests123", "EfakeSecretForTests456"


def test_updated_env_replaces_keys_and_keeps_everything_else():
    text = "# comment\nPAYPAL_CLIENT_ID=\nPAYPAL_CLIENT_SECRET=old\nPAYSCORE_RBI_FETCH=false\n"
    out = configure.updated_env(text, {"PAYPAL_CLIENT_ID": "a", "PAYPAL_CLIENT_SECRET": "b"})
    assert out == "# comment\nPAYPAL_CLIENT_ID=a\nPAYPAL_CLIENT_SECRET=b\nPAYSCORE_RBI_FETCH=false\n"
    assert configure.updated_env("", {"PAYPAL_MODE": "sandbox"}) == "PAYPAL_MODE=sandbox\n"


def test_writes_env_from_example_and_never_prints_values(tmp_path, monkeypatch, capsys):
    answers = iter([FAKE_ID, FAKE_SECRET])
    monkeypatch.setattr(configure.getpass, "getpass", lambda prompt: next(answers))
    env = tmp_path / ".env"
    env.write_text("", encoding="utf-8")  # an empty .env is seeded from .env.example

    assert configure.main(["--env-file", str(env), "--no-browser", "--no-check"]) == 0

    written = env.read_text(encoding="utf-8")
    assert f"PAYPAL_CLIENT_ID={FAKE_ID}" in written and f"PAYPAL_CLIENT_SECRET={FAKE_SECRET}" in written
    assert "PAYPAL_MODE=sandbox" in written and "PAYSCORE_FRONTEND_URL=" in written
    printed = capsys.readouterr()
    assert FAKE_ID not in printed.out + printed.err and FAKE_SECRET not in printed.out + printed.err


def test_rejected_credentials_are_reported_without_the_values(monkeypatch):
    def refuse(*args, **kwargs):
        raise configure.urllib.error.HTTPError(configure.TOKEN_URL, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(configure.urllib.request, "urlopen", refuse)
    ok, reason = configure.check_sandbox(FAKE_ID, FAKE_SECRET)
    assert not ok and "401" in reason and FAKE_ID not in reason and FAKE_SECRET not in reason


def test_clipboard_relay_saves_each_value_clears_clipboard_and_never_prints(tmp_path, monkeypatch, capsys):
    clipboard = {"value": FAKE_ID}
    monkeypatch.setattr(configure, "read_clipboard", lambda: clipboard["value"])
    monkeypatch.setattr(configure, "clear_clipboard", lambda: clipboard.update(value=""))
    env = tmp_path / ".env"

    assert configure.main(["--env-file", str(env), "--from-clipboard", "id"]) == 0
    assert clipboard["value"] == ""
    clipboard["value"] = FAKE_SECRET
    assert configure.main(["--env-file", str(env), "--from-clipboard", "secret"]) == 0

    saved = configure.env_values(env)
    assert saved["PAYPAL_CLIENT_ID"] == FAKE_ID and saved["PAYPAL_CLIENT_SECRET"] == FAKE_SECRET
    assert saved["PAYPAL_MODE"] == "sandbox"
    printed = capsys.readouterr()
    assert FAKE_ID not in printed.out + printed.err and FAKE_SECRET not in printed.out + printed.err


def test_clipboard_with_spaces_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(configure, "read_clipboard", lambda: "some copied sentence")
    env = tmp_path / ".env"
    assert configure.main(["--env-file", str(env), "--from-clipboard", "secret"]) == 1
    assert not env.exists()


def test_check_only_reports_missing_values_without_printing_any(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(f"PAYPAL_CLIENT_ID={FAKE_ID}\nPAYPAL_CLIENT_SECRET=\n", encoding="utf-8")
    assert configure.main(["--env-file", str(env), "--check-only"]) == 1
    out = capsys.readouterr().out
    assert "PAYPAL_CLIENT_SECRET" in out and FAKE_ID not in out


def test_register_webhook_creates_or_reuses_and_saves_id(tmp_path, monkeypatch, capsys):
    calls = []

    def fake_json(url, token, body=None):
        calls.append(body)
        if body is None:
            return {"webhooks": [{"id": "WH-EXISTING", "url": "https://old.example/paypal/webhook"}]}
        assert [e["name"] for e in body["event_types"]] == list(configure.WEBHOOK_EVENTS)
        return {"id": "WH-NEW123"}

    monkeypatch.setattr(configure, "access_token", lambda cid, secret: "token")
    monkeypatch.setattr(configure, "_paypal_json", fake_json)
    env = tmp_path / ".env"
    env.write_text(f"PAYPAL_CLIENT_ID={FAKE_ID}\nPAYPAL_CLIENT_SECRET={FAKE_SECRET}\n", encoding="utf-8")

    assert configure.main(["--env-file", str(env), "--register-webhook", "https://demo.example/"]) == 0
    assert calls[-1]["url"] == "https://demo.example/paypal/webhook"
    assert configure.env_values(env)["PAYPAL_WEBHOOK_ID"] == "WH-NEW123"
    assert configure.main(["--env-file", str(env), "--register-webhook", "https://old.example"]) == 0
    assert configure.env_values(env)["PAYPAL_WEBHOOK_ID"] == "WH-EXISTING"
    printed = capsys.readouterr()
    assert FAKE_ID not in printed.out + printed.err and FAKE_SECRET not in printed.out + printed.err


def test_register_webhook_needs_https_and_credentials(tmp_path, capsys):
    env = tmp_path / ".env"
    env.write_text(f"PAYPAL_CLIENT_ID={FAKE_ID}\nPAYPAL_CLIENT_SECRET=\n", encoding="utf-8")
    assert configure.main(["--env-file", str(env), "--register-webhook", "https://x.example"]) == 1
    env.write_text(f"PAYPAL_CLIENT_ID={FAKE_ID}\nPAYPAL_CLIENT_SECRET={FAKE_SECRET}\n", encoding="utf-8")
    assert configure.main(["--env-file", str(env), "--register-webhook", "http://x.example"]) == 1
