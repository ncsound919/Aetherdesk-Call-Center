#!/usr/bin/env python3
"""Start Metabase, LiteLLM, and Obscura locally WITHOUT Docker.

Runs the three AI/analytics infra services as plain processes on the host:

  * LiteLLM  -> `litellm --config config/litellm/config.yaml --port 4000`
  * Metabase -> `java -jar tools/metabase.jar`   (downloaded on first run)
  * Obscura  -> `tools/obscura/<bin> serve --port 9222`

Usage:
    python scripts/dev/infra.py                  # start all three
    python scripts/dev/infra.py --only litellm   # subset by name
    python scripts/dev/infra.py --refresh        # re-download binaries
"""

import argparse
import importlib.util
import os
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
LOG_DIR = REPO_ROOT / "logs" / "infra"

LITELLM_CONFIG = REPO_ROOT / "config" / "litellm" / "config.yaml"
LITELLM_VENV = TOOLS_DIR / "venv-litellm"
METABASE_VERSION = os.getenv("METABASE_VERSION", "0.63.2")
METABASE_JAR = TOOLS_DIR / "metabase.jar"
OBSCURA_DIR = TOOLS_DIR / "obscura"

SERVICES = ("litellm", "metabase", "obscura")


def _download(url: str, dest: Path) -> None:
    print(f"downloading {url} -> {dest}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=120) as resp, open(tmp, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            chunk = resp.read(1024 * 256)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if total:
                pct = done * 100 // total
                print(f"\r  {pct}% ({done // 1048576}MB / {total // 1048576}MB)", end="", flush=True)
    print()
    tmp.replace(dest)


def _obscura_asset() -> tuple[str, str]:
    if sys.platform == "win32":
        return "obscura-x86_64-windows.zip", "obscura.exe"
    arch = "aarch64" if sys.platform == "darwin" else "x86_64"
    plat = "macos" if sys.platform == "darwin" else "linux"
    return f"obscura-{arch}-{plat}.tar.gz", "obscura"


def ensure_metabase(refresh: bool) -> Path:
    if METABASE_JAR.exists() and not refresh:
        return METABASE_JAR
    url = f"https://downloads.metabase.com/v{METABASE_VERSION}/metabase.jar"
    _download(url, METABASE_JAR)
    return METABASE_JAR


def ensure_obscura(refresh: bool) -> Path:
    binary = OBSCURA_DIR / _obscura_asset()[1]
    if binary.exists() and not refresh:
        return binary
    asset_name, _ = _obscura_asset()
    url = f"https://github.com/h4ckf0r0day/obscura/releases/latest/download/{asset_name}"
    archive = TOOLS_DIR / asset_name
    _download(url, archive)
    OBSCURA_DIR.mkdir(parents=True, exist_ok=True)
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as z:
            z.extractall(OBSCURA_DIR)
    else:
        with tarfile.open(archive) as t:
            t.extractall(OBSCURA_DIR)
    return binary


def _ensure_litellm_venv() -> str:
    python = LITELLM_VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.exists():
        return str(python)
    print("[litellm] creating venv + installing litellm[proxy] (one-time, may take a while)...")
    subprocess.run([sys.executable, "-m", "venv", str(LITELLM_VENV)], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], check=True)
    subprocess.run([str(python), "-m", "pip", "install", "--quiet", "litellm[proxy]"], check=True)
    subprocess.run(
        [str(python), "-m", "pip", "install", "--quiet", "fastapi<0.116"], check=True
    )
    return str(python)


def _litellm_command() -> list[str]:
    python = _ensure_litellm_venv()
    return [
        python,
        "-m",
        "uvicorn",
        "litellm.proxy.proxy_server:app",
        "--host",
        "0.0.0.0",
        "--port",
        "4000",
    ]


def _litellm_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("LITELLM_MASTER_KEY", "sk-aetherdesk-local")
    if LITELLM_CONFIG.exists():
        env["LITELLM_CONFIG_FILE_PATH"] = str(LITELLM_CONFIG)
    return env


def _metabase_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "MB_DB_TYPE": "h2",
            "MB_JETTY_PORT": "3002",
            "MB_EMBEDDING_APP_ALLOW_EMBEDDING": "true",
            "MB_EMBEDDING_APP_ORIGIN": os.getenv("METABASE_EMBED_ORIGIN", "http://localhost:3001"),
        }
    )
    if os.getenv("METABASE_SECRET_KEY"):
        env["MB_EMBEDDING_SECRET_KEY"] = os.environ["METABASE_SECRET_KEY"]
    return env


def _spawn(name: str, cmd: list[str], env: dict[str, str] | None, url: str) -> subprocess.Popen:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = open(LOG_DIR / f"{name}.log", "a", encoding="utf-8")
    print(f"[{name}] starting: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(REPO_ROOT),
        env=env or os.environ.copy(),
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    print(f"[{name}] url: {url}")
    return proc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="*", choices=SERVICES, default=list(SERVICES))
    parser.add_argument("--refresh", action="store_true", help="re-download binaries")
    args = parser.parse_args()

    procs: dict[str, subprocess.Popen] = {}

    if "litellm" in args.only:
        procs["litellm"] = _spawn("litellm", _litellm_command(), _litellm_env(), "http://localhost:4000")

    if "metabase" in args.only:
        jar = ensure_metabase(args.refresh)
        java = shutil.which("java")
        if not java:
            print("[metabase] java not found on PATH; install OpenJDK 17+ and retry")
        else:
            procs["metabase"] = _spawn("metabase", [java, "-jar", str(jar)], _metabase_env(), "http://localhost:3002")

    if "obscura" in args.only:
        binary = ensure_obscura(args.refresh)
        procs["obscura"] = _spawn("obscura", [str(binary), "serve", "--port", "9222"], None, "ws://localhost:9222/devtools/browser")

    if not procs:
        print("no services selected; use --only litellm metabase obscura")
        return 1

    print("\nPress Ctrl+C to stop all services. Logs: logs/infra/")
    try:
        while True:
            time.sleep(2)
            for name, proc in list(procs.items()):
                code = proc.poll()
                if code is not None:
                    print(f"[{name}] exited with code {code}")
                    del procs[name]
            if not procs:
                print("all services exited")
                break
    except KeyboardInterrupt:
        print("\nstopping services...")
    finally:
        for proc in procs.values():
            proc.terminate()
        for proc in procs.values():
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    return 0


if __name__ == "__main__":
    sys.exit(main())
