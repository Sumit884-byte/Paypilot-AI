"""Put your PayPal sandbox Client ID and Secret into .env without showing them anywhere.

    python3 scripts/configure_paypal.py        (Windows: py scripts\\configure_paypal.py)

Opens the PayPal developer dashboard in your default browser, asks you to paste both values (nothing is
echoed), writes them into .env, and checks them against PayPal's sandbox token endpoint. The values are never
printed or logged. Standard library only; works on Windows, macOS, and Linux.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = "https://developer.paypal.com/dashboard/applications/sandbox"
TOKEN_URL = "https://api-m.sandbox.paypal.com/v1/oauth2/token"
KEYS = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET")


def updated_env(text: str, values: dict[str, str]) -> str:
    """Set each key in an env file's text, keeping every other line and comment as it was."""
    lines = text.splitlines()
    remaining = dict(values)
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if key in remaining:
            lines[i] = f"{key}={remaining.pop(key)}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    return "\n".join(lines) + "\n"


def check_sandbox(client_id: str, secret: str) -> tuple[bool, str]:
    """Ask PayPal's sandbox for an access token. Returns (ok, reason) and never includes the credentials."""
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    request = urllib.request.Request(TOKEN_URL, data=b"grant_type=client_credentials", method="POST",
                                     headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return "access_token" in json.loads(response.read() or b"{}"), "PayPal issued a sandbox access token"
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            return False, ("PayPal rejected them (401). Check you copied the SANDBOX pair, not Live, "
                           "and that the Secret is complete.")
        return False, f"PayPal answered HTTP {exc.code}"
    except OSError as exc:
        return False, f"could not reach PayPal ({exc.__class__.__name__}); the values are saved, check later"


WEBHOOKS_URL = "https://api-m.sandbox.paypal.com/v1/notifications/webhooks"
# The only events payscore/paypal/repayment.py handles
WEBHOOK_EVENTS = ("PAYMENT.CAPTURE.COMPLETED", "INVOICING.INVOICE.PAID")


def _paypal_json(url: str, token: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(url, data=json.dumps(body).encode() if body is not None else None,
                                     method="POST" if body is not None else "GET",
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read() or b"{}")


def access_token(client_id: str, secret: str) -> str:
    auth = base64.b64encode(f"{client_id}:{secret}".encode()).decode()
    request = urllib.request.Request(TOKEN_URL, data=b"grant_type=client_credentials", method="POST",
                                     headers={"Authorization": f"Basic {auth}", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read())["access_token"]


def register_webhook(client_id: str, secret: str, base_url: str) -> str:
    """Register <base_url>/paypal/webhook for the handled events, or reuse an existing registration. Returns its id."""
    target = base_url.rstrip("/") + "/paypal/webhook"
    token = access_token(client_id, secret)
    for hook in _paypal_json(WEBHOOKS_URL, token).get("webhooks", []):
        if hook.get("url") == target:
            return hook["id"]
    created = _paypal_json(WEBHOOKS_URL, token, {"url": target, "event_types": [{"name": e} for e in WEBHOOK_EVENTS]})
    return created["id"]


def ask(label: str) -> str:
    while True:
        value = getpass.getpass(f"Paste the {label} (input is hidden), then press Enter: ").strip()
        if value and " " not in value:
            return value
        print("  That looks empty or has spaces. Try again.")


CLIPBOARD_KEYS = {"id": "PAYPAL_CLIENT_ID", "secret": "PAYPAL_CLIENT_SECRET"}


def _clipboard_commands() -> tuple[list[str], list[str]]:
    """(read, clear) commands for this OS's clipboard."""
    if sys.platform == "darwin":
        return ["pbpaste"], ["pbcopy"]
    if os.name == "nt":
        return (["powershell", "-NoProfile", "-Command", "Get-Clipboard -Raw"],
                ["powershell", "-NoProfile", "-Command", "Set-Clipboard -Value $null"])
    if shutil.which("wl-paste"):
        return ["wl-paste", "--no-newline"], ["wl-copy", "--clear"]
    return ["xclip", "-selection", "clipboard", "-o"], ["xclip", "-selection", "clipboard", "-i"]


def read_clipboard() -> str:
    read, _ = _clipboard_commands()
    return subprocess.run(read, capture_output=True, text=True, check=True).stdout.strip()


def clear_clipboard() -> None:
    _, clear = _clipboard_commands()
    subprocess.run(clear, input="", capture_output=True, text=True, check=False)


def env_values(env_file: Path) -> dict[str, str]:
    if not env_file.exists():
        return {}
    pairs = (line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs if not key.lstrip().startswith("#")}


def save(env_file: Path, values: dict[str, str]) -> None:
    existing = env_file.read_text(encoding="utf-8") if env_file.exists() else ""
    if not existing.strip():
        example = ROOT / ".env.example"
        existing = example.read_text(encoding="utf-8") if example.exists() else ""
    env_file.write_text(updated_env(existing, {**values, "PAYPAL_MODE": "sandbox"}), encoding="utf-8")
    if os.name != "nt":
        env_file.chmod(0o600)  # readable by you only


def report_check(client_id: str, secret: str) -> int:
    ok, reason = check_sandbox(client_id, secret)
    print(("Sandbox check passed: " if ok else "Sandbox check FAILED: ") + reason + ".")
    if ok:
        print("Restart the app (python3 scripts/dev.py) to use PayPal sandbox features.")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--no-browser", action="store_true", help="do not open the PayPal dashboard")
    parser.add_argument("--no-check", action="store_true", help="skip the sandbox token check")
    parser.add_argument("--from-clipboard", choices=sorted(CLIPBOARD_KEYS),
                        help="save the clipboard as the Client ID or Secret, then clear the clipboard")
    parser.add_argument("--check-only", action="store_true", help="check the credentials already in .env")
    parser.add_argument("--register-webhook", metavar="PUBLIC_URL",
                        help="register PUBLIC_URL/paypal/webhook with PayPal and save PAYPAL_WEBHOOK_ID")
    args = parser.parse_args(argv)
    env_file: Path = args.env_file

    if args.register_webhook:
        saved = env_values(env_file)
        if not all(saved.get(key) for key in KEYS):
            print("Set PAYPAL_CLIENT_ID and PAYPAL_CLIENT_SECRET first.")
            return 1
        if not args.register_webhook.startswith("https://"):
            print("PayPal only delivers webhooks to https:// URLs.")
            return 1
        try:
            webhook_id = register_webhook(saved["PAYPAL_CLIENT_ID"], saved["PAYPAL_CLIENT_SECRET"], args.register_webhook)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:300]
            print(f"PayPal refused the webhook (HTTP {exc.code}): {detail}")
            return 1
        except (OSError, KeyError) as exc:
            print(f"Could not register the webhook ({exc.__class__.__name__}).")
            return 1
        save(env_file, {"PAYPAL_WEBHOOK_ID": webhook_id})
        print(f"Registered {args.register_webhook.rstrip('/')}/paypal/webhook for {', '.join(WEBHOOK_EVENTS)}.")
        print("Saved PAYPAL_WEBHOOK_ID. Restart the API so it verifies incoming webhooks.")
        return 0

    if args.from_clipboard:
        key = CLIPBOARD_KEYS[args.from_clipboard]
        value = read_clipboard()
        # PayPal REST credentials are one long token of letters, digits, "-" and "_"
        if not re.fullmatch(r"[A-Za-z0-9_-]{20,200}", value):
            print(f"The clipboard does not look like a PayPal {key}. Nothing was saved and the clipboard was left as is.")
            return 1
        save(env_file, {key: value})
        clear_clipboard()
        print(f"Saved {key} from the clipboard (value not shown). Clipboard cleared.")
        return 0

    if args.check_only:
        saved = env_values(env_file)
        missing = [key for key in KEYS if not saved.get(key)]
        if missing:
            print("Not set in .env yet: " + ", ".join(missing) + ".")
            return 1
        return report_check(saved["PAYPAL_CLIENT_ID"], saved["PAYPAL_CLIENT_SECRET"])

    print(__doc__.splitlines()[0] + "\n")
    print("In the PayPal developer dashboard (Sandbox, not Live):")
    print("  1. Apps & Credentials -> open your app, or Create App")
    print("  2. Tick: Transaction Search, Payouts, Subscriptions, Invoicing, Orders")
    print("  3. Log in with PayPal -> return URL http://localhost:8000/oauth/callback")
    print("  4. Copy the Client ID, then click Show and copy the Secret\n")
    if not args.no_browser:
        webbrowser.open(DASHBOARD)
        print(f"Opened {DASHBOARD} in your browser.\n")

    values = {"PAYPAL_CLIENT_ID": ask("Client ID"), "PAYPAL_CLIENT_SECRET": ask("Secret")}
    save(env_file, values)
    print(f"\nSaved both values to {env_file} (not shown). The file is git-ignored.")
    return 0 if args.no_check else report_check(values["PAYPAL_CLIENT_ID"], values["PAYPAL_CLIENT_SECRET"])


if __name__ == "__main__":
    sys.exit(main())
