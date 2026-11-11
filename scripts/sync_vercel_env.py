"""Copy production-relevant settings from your local .env into Vercel, without printing any value.

    python3 scripts/sync_vercel_env.py              (Windows: py scripts\\sync_vercel_env.py)

Each value is piped straight from .env into `vercel env add` on stdin, so it never appears on screen, in shell
history, or in logs. Only names and outcomes are printed. Values pointing at localhost are skipped, because they
would break the deployed site, and so are empty values. Credentials are stored as Vercel "sensitive" variables.
Run it from a directory linked with `vercel link`; redeploy afterwards for the values to take effect.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Settings that make sense on the deployed site. URL settings that differ per environment
# (frontend URL, CORS origins, OAuth redirect, checkout return URLs) are set on Vercel directly.
SYNC = ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_MODE", "PAYPAL_API_BASE", "PAYPAL_WEBHOOK_ID",
        "PAYPAL_INR_PER_USD", "OPENAI_API_KEY")
SENSITIVE = {"PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID", "OPENAI_API_KEY"}


def env_values(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--target", default="production", choices=["production", "preview", "development"])
    parser.add_argument("--force", action="store_true", help="overwrite variables that already exist on Vercel")
    args = parser.parse_args(argv)

    vercel = shutil.which("vercel")
    if not vercel:
        print("The Vercel CLI is not installed (npm i -g vercel).")
        return 1
    if not args.env_file.exists():
        print(f"No {args.env_file}. Run scripts/configure_paypal.py first.")
        return 1

    values = env_values(args.env_file)
    failures = 0
    for key in SYNC:
        value = values.get(key, "")
        if not value:
            print(f"  skip   {key} (empty in .env)")
            continue
        if "localhost" in value or "127.0.0.1" in value:
            print(f"  skip   {key} (points at localhost)")
            continue
        cmd = [vercel, "env", "add", key, args.target]
        if key in SENSITIVE and args.target != "development":
            cmd.append("--sensitive")
        if args.force:
            cmd.append("--force")
        result = subprocess.run(cmd, input=value, capture_output=True, text=True, cwd=ROOT)
        output = (result.stdout + result.stderr).lower()
        if result.returncode == 0 and ("added" in output or "overwrote" in output or "updated" in output):
            print(f"  added  {key}" + (" (sensitive)" if "--sensitive" in cmd else ""))
        elif "already exists" in output:
            print(f"  exists {key} (left as is; use --force to overwrite)")
        else:
            failures += 1
            # Never echo CLI output verbatim: report only the exit code
            print(f"  FAILED {key} (vercel exited with {result.returncode})")
    if not failures:
        print(f"Done. Redeploy for the new {args.target} values to take effect: vercel deploy --prod")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
