"""Load test: several organisations using a running server at once, with a leak check.

    # against a server you run (an admin token for each of two or more organisations):
    uv run python tools/loadtest.py --base http://127.0.0.1:8000 \\
        --token ipo_aaa --token ipo_bbb --duration 30

    # self-contained: starts a throwaway accounts-mode server with three organisations
    uv run python tools/loadtest.py --selfhost --duration 10

Each worker belongs to one organisation and runs a mix of reads, case creation, comments and
exports. Every created case carries its organisation's tag, and every list a worker reads is
checked: a case with another organisation's tag means isolation failed. The exit status is
non-zero for any 5xx response, any other unexpected status, or any leak. Prints requests per
second and the 50th, 95th and 99th percentile latency per route.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.lat: dict[str, list[float]] = defaultdict(list)
        self.status: dict[tuple[str, int], int] = defaultdict(int)
        self.leaks: list[str] = []
        self.bad: list[str] = []

    def record(self, route: str, code: int, seconds: float) -> None:
        with self.lock:
            self.lat[route].append(seconds)
            self.status[(route, code)] += 1
            if code >= 500 or code in (0, 401, 403, 429):
                self.bad.append(f"{route} -> {code}")


def call(
    base: str, token: str, method: str, path: str, body: dict | None = None
) -> tuple[int, bytes]:
    req = urllib.request.Request(
        base + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except OSError:
        return 0, b""


def worker(
    base: str, token: str, tag: str, others: list[str], stop: float, st: Stats, seed: int
) -> None:
    rnd = random.Random(seed)
    mine: list[str] = []
    n = 0

    def timed(route: str, method: str, path: str, body: dict | None = None) -> tuple[int, bytes]:
        t0 = time.perf_counter()
        code, data = call(base, token, method, path, body)
        st.record(route, code, time.perf_counter() - t0)
        return code, data

    while time.time() < stop:
        pick = rnd.random()
        if pick < 0.15 or not mine:
            n += 1
            code, data = timed(
                "POST /cases", "POST", "/api/v1/cases", {"company_name": f"{tag} case {n}"}
            )
            if code == 201:
                mine.append(json.loads(data)["id"])
        elif pick < 0.45:
            code, data = timed("GET /cases", "GET", "/api/v1/cases?limit=200")
            if code == 200:
                for item in json.loads(data)["items"]:
                    if any(item["company_name"].startswith(o) for o in others):
                        with st.lock:
                            st.leaks.append(f"{tag} saw {item['company_name']!r} in /cases")
        elif pick < 0.60:
            timed("GET /dashboard", "GET", "/api/v1/dashboard")
        elif pick < 0.75:
            timed(
                "POST comment",
                "POST",
                f"/api/v1/cases/{rnd.choice(mine)}/comments",
                {"body": f"{tag} note"},
            )
        elif pick < 0.85:
            code, data = timed("GET exports/cases", "GET", "/api/v1/exports/cases?format=csv")
            if code == 200 and any(o.encode() in data for o in others):
                with st.lock:
                    st.leaks.append(f"{tag} saw another organisation in the CSV export")
        elif pick < 0.92:
            timed("GET onboarding", "GET", "/api/v1/onboarding")
        else:
            timed("GET case", "GET", f"/api/v1/cases/{rnd.choice(mine)}")


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))] * 1000


def report(st: Stats, seconds: float) -> None:
    total = sum(len(v) for v in st.lat.values())
    print(f"\n{total} requests in {seconds:.1f}s = {total / seconds:.0f} requests/second\n")
    print(f"{'route':<22}{'count':>8}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}")
    for route, v in sorted(st.lat.items()):
        print(f"{route:<22}{len(v):>8}{pct(v, 0.5):>9.1f}{pct(v, 0.95):>9.1f}{pct(v, 0.99):>9.1f}")
    print(f"\nleaks: {len(st.leaks)}   unexpected responses: {len(st.bad)}")
    for line in (st.leaks + st.bad)[:10]:
        print("  ", line)


def selfhost(
    orgs: int, workers_dir: Path
) -> tuple[subprocess.Popen[bytes], str, list[str], list[str]]:
    from ipo_engine.screening.api.dependencies import Container
    from ipo_engine.screening.core.config import Settings
    from ipo_engine.screening.core.security import Role

    env = {
        "DATA_DIR": str(workers_dir / "data"),
        "DATABASE_URL": f"sqlite:///{workers_dir / 'load.db'}",
    }
    box = Container.build(Settings(ACCOUNTS_ENABLED="true", **env))  # type: ignore[arg-type]
    tokens, tags = [], []
    for n in range(orgs):
        org = box.accounts.create_org(f"Load Org {n}")["id"]
        user = box.accounts.get_or_create_user(f"admin{n}@load.example")
        box.accounts.add_member(org, user["id"], Role.ADMIN, actor="loadtest", owner=True)
        tokens.append(
            box.accounts.create_token(org_id=org, user_id=user["id"], name="load")["token"]
        )
        tags.append(f"Load Org {n}")
    box.shutdown()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    cmd = [sys.executable, "-m", "uvicorn", "ipo_engine.screening.main:app"]
    cmd += ["--port", str(port), "--log-level", "warning"]
    child_env = {**os.environ, **env, "ACCOUNTS_ENABLED": "true", "APP_ENV": "development"}
    proc = subprocess.Popen(
        cmd, env=child_env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            urllib.request.urlopen(base + "/api/v1/system/health", timeout=1)
            break
        except OSError:
            time.sleep(0.2)
    return proc, base, tokens, tags


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--token", action="append", default=[], help="an admin token per organisation")
    ap.add_argument(
        "--tag", action="append", default=[], help="company-name prefix per organisation"
    )
    ap.add_argument("--duration", type=float, default=20)
    ap.add_argument("--threads-per-org", type=int, default=4)
    ap.add_argument(
        "--selfhost", action="store_true", help="start a throwaway server with 3 organisations"
    )
    a = ap.parse_args()
    proc = None
    tmp = Path(tempfile.mkdtemp())
    try:
        if a.selfhost:
            proc, a.base, a.token, a.tag = selfhost(3, tmp)
        if len(a.token) < 2:
            print(
                "need at least two --token values (one per organisation), or --selfhost",
                file=sys.stderr,
            )
            return 2
        tags = a.tag or [f"Org{n}" for n in range(len(a.token))]
        st = Stats()
        stop = time.time() + a.duration
        threads = []
        for i, (tok, tag) in enumerate(zip(a.token, tags, strict=True)):
            others = [t for t in tags if t != tag]
            for j in range(a.threads_per_org):
                t = threading.Thread(
                    target=worker, args=(a.base, tok, tag, others, stop, st, i * 100 + j)
                )
                t.start()
                threads.append(t)
        started = time.time()
        for t in threads:
            t.join()
        report(st, time.time() - started)
        return 1 if (st.leaks or st.bad) else 0
    finally:
        if proc is not None:
            proc.terminate()
            proc.wait(10)
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
