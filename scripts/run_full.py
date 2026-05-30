from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run backend and frontend together")
    parser.add_argument("--backend-dir", default="backend")
    parser.add_argument("--frontend-dir", default="frontend")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8010")
    parser.add_argument("--frontend-host", default="127.0.0.1")
    parser.add_argument("--frontend-port", default="5173")
    return parser.parse_args()


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def run_backend_migrations(backend_dir: Path) -> int:
    cmd = [sys.executable, "manage.py", "migrate", "--noinput"]
    print("Applying backend migrations:", " ".join(cmd))
    return subprocess.run(cmd, cwd=backend_dir, env=backend_env()).returncode


def backend_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    return env


def main() -> int:
    args = parse_args()

    root = Path.cwd()
    backend_dir = root / args.backend_dir
    frontend_dir = root / args.frontend_dir

    if not backend_dir.exists():
        print(f"Backend directory not found: {backend_dir}")
        return 1
    if not frontend_dir.exists():
        print(f"Frontend directory not found: {frontend_dir}")
        return 1

    npx = "npx.cmd" if os.name == "nt" else "npx"
    backend_cmd = [
        sys.executable,
        "manage.py",
        "runserver",
        f"{args.host}:{args.port}",
    ]
    frontend_cmd = [
        npx,
        "vite",
        "--host",
        args.frontend_host,
        "--port",
        str(args.frontend_port),
    ]

    backend_url = f"http://{args.host}:{args.port}"
    frontend_url = f"http://{args.frontend_host}:{args.frontend_port}"

    started_procs: list[subprocess.Popen] = []

    if is_port_in_use(args.host, int(args.port)):
        migration_code = run_backend_migrations(backend_dir)
        if migration_code != 0:
            return migration_code
        print(f"Backend already running on {backend_url}; reusing existing service.")
    else:
        migration_code = run_backend_migrations(backend_dir)
        if migration_code != 0:
            return migration_code
        print("Starting backend:", " ".join(backend_cmd))
        started_procs.append(subprocess.Popen(backend_cmd, cwd=backend_dir, env=backend_env()))

    if is_port_in_use(args.frontend_host, int(args.frontend_port)):
        print(f"Frontend already running on {frontend_url}; reusing existing service.")
    else:
        print("Starting frontend:", " ".join(frontend_cmd))
        started_procs.append(subprocess.Popen(frontend_cmd, cwd=frontend_dir))

    print(f"Backend  -> {backend_url}")
    print(f"Frontend -> {frontend_url}")

    if not started_procs:
        print("No new services were started. Both ports are already in use.")
        return 0

    exit_code = 0
    try:
        while True:
            exited = [proc for proc in started_procs if proc.poll() is not None]
            if exited:
                exit_code = exited[0].returncode or 0
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("Stopping services...")
    finally:
        for proc in started_procs:
            if proc.poll() is None:
                proc.terminate()
        time.sleep(0.5)
        for proc in started_procs:
            if proc.poll() is None:
                proc.kill()

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
