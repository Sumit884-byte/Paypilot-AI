"""Set up and run the API and the frontend with one command, on Windows, macOS, or Linux.

    python scripts/dev.py            (Windows: py scripts\\dev.py)

First run creates .venv, installs Python and npm dependencies, then starts both servers.
Later runs reinstall only when requirements.txt or frontend/package-lock.json change.
Ctrl+C stops both servers. Standard library only, so it runs before anything is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
VENV = ROOT / ".venv"
IS_WINDOWS = os.name == "nt"
VENV_PYTHON = VENV / ("Scripts/python.exe" if IS_WINDOWS else "bin/python")
MIN_PYTHON = (3, 10)
# Vite 8 requires Node ^20.19 or >=22.12
MIN_NODE = {20: (20, 19), 22: (22, 12)}


def say(message: str) -> None:
    print(f"[dev] {message}", flush=True)


def fail(message: str) -> None:
    print(f"[dev] ERROR: {message}", file=sys.stderr, flush=True)
    sys.exit(1)


def run(cmd: list[str], **kwargs) -> None:
    say("$ " + " ".join(str(c) for c in cmd))
    if subprocess.call([str(c) for c in cmd], **kwargs) != 0:
        fail(f"command failed: {' '.join(str(c) for c in cmd)}")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


def stamp_matches(stamp: Path, value: str) -> bool:
    return stamp.exists() and stamp.read_text(encoding="utf-8").strip() == value


def check_python() -> None:
    if sys.version_info < MIN_PYTHON:
        fail(f"Python {MIN_PYTHON[0]}.{MIN_PYTHON[1]}+ is required (found {platform.python_version()}).")


def check_node() -> str:
    node = shutil.which("node")
    if not node:
        fail("Node.js is not installed. Install Node 22 LTS from https://nodejs.org and run this again.")
    version = subprocess.run([node, "--version"], capture_output=True, text=True).stdout.strip().lstrip("v")
    major, minor = (int(part) for part in version.split(".")[:2])
    ok = major >= 23 or (major in MIN_NODE and (major, minor) >= MIN_NODE[major])
    if not ok:
        fail(f"Node {version} is too old for Vite 8. Install Node 20.19+ or 22.12+ (22 LTS recommended).")
    return node


def setup_python(skip: bool) -> None:
    if not VENV_PYTHON.exists():
        say("Creating .venv")
        run([sys.executable, "-m", "venv", str(VENV)])
    stamp = VENV / ".requirements.sha256"
    wanted = digest(ROOT / "requirements.txt")
    if skip or stamp_matches(stamp, wanted):
        return
    say("Installing Python dependencies")
    run([VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip"])
    run([VENV_PYTHON, "-m", "pip", "install", "-r", ROOT / "requirements.txt"])
    stamp.write_text(wanted, encoding="utf-8")


def check_lightgbm() -> None:
    probe = subprocess.run([VENV_PYTHON, "-c", "import lightgbm"], capture_output=True, text=True)
    if probe.returncode == 0:
        return
    hint = {
        "Darwin": "LightGBM needs OpenMP on macOS. Install it with:  brew install libomp",
        "Windows": "LightGBM needs the Microsoft Visual C++ Redistributable (x64): "
                   "https://aka.ms/vs/17/release/vc_redist.x64.exe",
        "Linux": "LightGBM needs the OpenMP runtime, e.g.  sudo apt install libgomp1",
    }.get(platform.system(), "")
    fail(f"LightGBM could not be imported.\n{probe.stderr.strip().splitlines()[-1] if probe.stderr else ''}\n{hint}")


def setup_frontend(skip: bool) -> None:
    npm = shutil.which("npm")
    if not npm:
        fail("npm is not installed. It ships with Node.js: https://nodejs.org")
    stamp = FRONTEND / "node_modules" / ".package-lock.sha256"
    wanted = digest(FRONTEND / "package-lock.json")
    if skip and (FRONTEND / "node_modules").exists():
        return
    if stamp_matches(stamp, wanted):
        return
    say("Installing frontend dependencies")
    run([npm, "ci" if (FRONTEND / "package-lock.json").exists() else "install"], cwd=FRONTEND)
    stamp.write_text(wanted, encoding="utf-8")


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("127.0.0.1", port)) != 0


def wait_for(url: str, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def smoke_test(web_url: str) -> None:
    """The frontend page, the API through the frontend's proxy, and a demo deep link must all answer."""
    for label, url in (("frontend", web_url), ("API via proxy", f"{web_url}/health"),
                       ("demo link", f"{web_url}/try/priya")):
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                body = response.read().decode("utf-8", "replace")
        except OSError as exc:
            fail(f"smoke test: {label} at {url} failed: {exc}")
        if label == "API via proxy" and '"status":"ok"' not in body.replace(" ", ""):
            fail(f"smoke test: {label} returned an unexpected body: {body[:200]}")
        say(f"smoke test: {label} OK")
    say("Smoke test passed.")


def stop(procs: list[subprocess.Popen]) -> None:
    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
    for proc in procs:
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _interrupt(*_: object) -> None:
    raise KeyboardInterrupt


def main() -> None:
    # A plain terminate (closed terminal, process manager) also stops both servers instead of orphaning them
    signal.signal(signal.SIGTERM, _interrupt)
    parser = argparse.ArgumentParser(description="Set up and run Paypilot AI locally.")
    parser.add_argument("--skip-install", action="store_true", help="do not install or update dependencies")
    parser.add_argument("--api-port", type=int, default=8000)
    parser.add_argument("--web-port", type=int, default=5173)
    parser.add_argument("--smoke", action="store_true",
                        help="start both servers, check the app responds, then stop (for CI or to verify an install)")
    args = parser.parse_args()

    check_python()
    node = check_node()
    setup_python(args.skip_install)
    check_lightgbm()
    setup_frontend(args.skip_install)

    for port in (args.api_port, args.web_port):
        if not port_free(port):
            fail(f"Port {port} is already in use. Stop the other process or pass --api-port/--web-port.")
    if not (ROOT / ".env").exists():
        say("No .env found: running in demo mode. Copy .env.example to .env to enable PayPal sandbox features.")

    web_url = f"http://localhost:{args.web_port}"
    env = {**os.environ, "PAYSCORE_FRONTEND_URL": os.environ.get("PAYSCORE_FRONTEND_URL", web_url)}
    if args.api_port != 8000:
        # Vite's dev proxy targets port 8000; point the browser straight at the API instead
        env.setdefault("VITE_PAYSCORE_API_URL", f"http://127.0.0.1:{args.api_port}")
        env["PAYSCORE_CORS_ORIGINS"] = os.environ.get("PAYSCORE_CORS_ORIGINS", web_url)

    # Vite runs through node directly (not the npm wrapper) so Ctrl+C stops it cleanly on Windows too
    procs = [
        subprocess.Popen([str(VENV_PYTHON), "-m", "uvicorn", "payscore.api:app",
                          "--host", "127.0.0.1", "--port", str(args.api_port)], cwd=ROOT, env=env),
        subprocess.Popen([node, str(FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"),
                          "--host", "localhost", "--port", str(args.web_port), "--strictPort"], cwd=FRONTEND, env=env),
    ]
    try:
        if not wait_for(f"http://127.0.0.1:{args.api_port}/health", 90):
            fail("The API did not start. See the output above.")
        if not wait_for(web_url, 60):
            fail("The frontend did not start. See the output above.")
        say("Ready:")
        say(f"  App                     {web_url}")
        say(f"  Try as Priya            {web_url}/try/priya")
        say(f"  Try as risky borrower   {web_url}/try/rohan")
        say(f"  API docs                http://127.0.0.1:{args.api_port}/docs")
        if args.smoke:
            smoke_test(web_url)
            return
        say("Press Ctrl+C to stop.")
        while all(proc.poll() is None for proc in procs):
            time.sleep(1)
        fail("A server exited unexpectedly. See the output above.")
    except KeyboardInterrupt:
        say("Stopping")
    finally:
        stop(procs)


if __name__ == "__main__":
    main()
