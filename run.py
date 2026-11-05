#!/usr/bin/env python3
"""
MAAPS Nexus - one command.

    python run.py            start the stack (env check, docker up, wait healthy)
    python run.py status     what's running and what's healthy
    python run.py logs       follow orchestrator logs (Ctrl+C to stop)
    python run.py down       stop everything
    python run.py doctor     figure out why it isn't working
    python run.py test       run the test suite

Stdlib only. No dependencies. Windows/Linux/macOS.
"""

import os
import sys
import time
import shutil
import socket
import subprocess
import urllib.request
import urllib.error

ROOT = os.path.dirname(os.path.abspath(__file__))
COMPOSE = os.path.join(ROOT, "docker-compose.yml")

SERVICES = {
    "orchestrator": {"url": "http://localhost:8080/health"},
    "audio_worker": {"url": "http://localhost:8000/health"},
    "qdrant": {"url": "http://localhost:6333/healthz"},
}

# Required keys that can stay empty for a dev boot, vs ones that matter
ENV_HINTS = {
    "POSTGRES_PASSWORD": "any non-default string",
    "GROQ_API_KEY": "free at console.groq.com - powers AI lead qualification",
    "SMTP_USER": "only needed for outbound email (V2)",
    "SMTP_PASSWORD": "only needed for outbound email (V2)",
}


# ----------------------------------------------------------------------------
# docker plumbing
# ----------------------------------------------------------------------------

def docker_binary() -> str:
    exe = shutil.which("docker")
    if not exe:
        return ""
    # Verify the daemon actually answers (Docker Desktop may be installed but off)
    try:
        r = subprocess.run([exe, "info", "--format", "ok"],
                           capture_output=True, text=True, timeout=15)
        return exe if r.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def compose(*args: str, capture: bool = False) -> subprocess.CompletedProcess:
    cmd = ["docker", "compose", "-f", COMPOSE, *args]
    return subprocess.run(cmd, capture_output=capture, text=True, cwd=ROOT)


# ----------------------------------------------------------------------------
# env
# ----------------------------------------------------------------------------

def ensure_env() -> str:
    """Return path to .env, creating from .env.example if missing."""
    env_path = os.path.join(ROOT, ".env")
    example = os.path.join(ROOT, ".env.example")
    if not os.path.exists(env_path):
        if os.path.exists(example):
            shutil.copyfile(example, env_path)
            print(f"  [env] created .env from .env.example - edit it before production")
        else:
            # Nothing to copy from; write a minimal dev .env
            with open(env_path, "w", encoding="utf-8") as f:
                f.write("POSTGRES_USER=maaps_admin\nPOSTGRES_PASSWORD=dev_only_change_me\nTZ=America/Regina\n")
            print("  [env] created minimal .env (dev defaults)")
    return env_path


def env_empty_keys(env_path: str) -> list:
    keys = []
    try:
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if not v.strip():
                    keys.append(k.strip())
    except OSError:
        pass
    return keys


# ----------------------------------------------------------------------------
# health
# ----------------------------------------------------------------------------

def check_url(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return 200 <= r.status < 500  # some healthz endpoints return 404 until ready
    except (urllib.error.URLError, socket.timeout, ConnectionError, OSError):
        return False


def wait_healthy(timeout_s: float = 120.0) -> dict:
    """Poll service health endpoints until up or timeout. Returns {name: bool}."""
    results = {name: False for name in SERVICES}
    deadline = time.time() + timeout_s
    pending = dict(SERVICES)
    while time.time() < deadline and pending:
        for name, meta in list(pending.items()):
            if check_url(meta["url"]):
                results[name] = True
                del pending[name]
                print(f"  [up] {name}")
        if pending:
            time.sleep(2.0)
    for name in pending:
        print(f"  [TIMEOUT] {name} - not healthy after {int(timeout_s)}s")
    return results


# ----------------------------------------------------------------------------
# commands
# ----------------------------------------------------------------------------

def cmd_start() -> int:
    print("MAAPS Nexus - starting\n")

    # 1. Docker
    docker = docker_binary()
    if not docker:
        print("  [x] Docker daemon not reachable.")
        print("      Install Docker Desktop: https://www.docker.com/products/docker-desktop/")
        print("      Then run this again. Nothing else is required.")
        return 1
    print("  [ok] Docker")

    # 2. Env
    env_path = ensure_env()
    empty = env_empty_keys(env_path)
    important = [k for k in empty if k in ENV_HINTS]
    if important:
        print(f"  [env] empty optional keys: {', '.join(important)}")
        print("        (fine for a first boot - see run.py doctor for hints)")

    # 3. Up
    print("  [..] docker compose up -d (first run pulls ~6GB of images - be patient)")
    r = compose("up", "-d")
    if r.returncode != 0:
        print(r.stderr or r.stdout)
        print("  [x] compose failed. Try: python run.py doctor")
        return 1

    # 4. Health
    print("  [..] waiting for services to go healthy...")
    results = wait_healthy()
    print()

    # 5. Report
    up = [n for n, ok in results.items() if ok]
    if up:
        print("MAAPS Nexus is up:")
        print("  • Orchestrator   http://localhost:8080/health")
        print("  • Audio Worker   http://localhost:8000/status")
        print("  • Live telemetry ws://localhost:8000/ws/monitor")
        print("  • Qdrant         http://localhost:6333/dashboard")
    failed = [n for n, ok in results.items() if not ok]
    if failed:
        print(f"\n  [!] unhealthy: {', '.join(failed)} - run: python run.py logs")
        return 1
    return 0


def cmd_status() -> int:
    r = compose("ps", capture=True)
    print(r.stdout or "(no containers)")
    print("- health -")
    for name, meta in SERVICES.items():
        state = "up" if check_url(meta["url"]) else "DOWN"
        print(f"  {name:<14} {state}")
    return 0 if all(check_url(m["url"]) for m in SERVICES.values()) else 1


def cmd_logs(service: str = "orchestrator") -> int:
    r = compose("logs", "-f", "--tail", "100", service, capture=False)
    return r.returncode


def cmd_down() -> int:
    print("Stopping MAAPS Nexus...")
    r = compose("down")
    print("Done. Volumes are kept - data survives. (docker compose down -v nukes it.)")
    return r.returncode


def cmd_doctor() -> int:
    print("MAAPS doctor\n")
    problems = 0

    if shutil.which("docker"):
        print("  [ok] docker CLI found")
        if docker_binary():
            print("  [ok] docker daemon reachable")
        else:
            print("  [x] docker daemon NOT reachable - start Docker Desktop")
            problems += 1
    else:
        print("  [x] docker not installed - https://www.docker.com/products/docker-desktop/")
        problems += 1

    for port, what in [(5432, "postgres"), (6333, "qdrant"), (8000, "audio worker"), (8080, "orchestrator")]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        busy = s.connect_ex(("localhost", port)) == 0
        s.close()
        if busy:
            print(f"  [..] port {port:<5} in use ({what}) - service may already be running")
        else:
            print(f"  [..] port {port:<5} free")

    env_path = ensure_env()
    empty = env_empty_keys(env_path)
    if empty:
        print(f"  [env] empty keys in .env:")
        for k in empty:
            hint = ENV_HINTS.get(k, "")
            print(f"        {k}{' - ' + hint if hint else ''}")
    else:
        print("  [ok] .env has no empty keys")

    if problems:
        print(f"\n{problems} blocker(s) found. Fix and run: python run.py")
    else:
        print("\nNo blockers. python run.py should work.")
    return problems


def cmd_test() -> int:
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-v"], cwd=ROOT)
    return r.returncode


# ----------------------------------------------------------------------------

def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "start"

    if cmd == "start":
        return cmd_start()
    if cmd == "status":
        return cmd_status()
    if cmd == "logs":
        return cmd_logs(args[1] if len(args) > 1 else "orchestrator")
    if cmd == "down":
        return cmd_down()
    if cmd == "doctor":
        return cmd_doctor()
    if cmd == "test":
        return cmd_test()

    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
