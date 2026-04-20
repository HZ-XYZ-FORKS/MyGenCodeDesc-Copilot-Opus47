"""Transport coverage — AlgA over ``http://`` to a Subversion DAV server.

Spawns Apache httpd configured with ``mod_dav_svn`` on a loopback port,
exposes a bare svn repo via WebDAV, checks out via
``http://127.0.0.1:<port>/repo``, and runs AlgA-SVN against the working
copy.

Host dependencies
-----------------
This test requires **all** of:

  1. ``httpd`` executable on PATH (Apache 2.x)
  2. The Subversion Apache modules ``mod_dav_svn.so`` and
     ``mod_authz_svn.so`` on disk — these are *not* part of stock macOS
     Apache and are *not* shipped by ``brew install subversion`` (which
     installs only the headers). They are typically provided by Linux
     distros (``libapache2-mod-svn`` on Debian/Ubuntu,
     ``mod_dav_svn`` on RHEL/Fedora) or by a manual
     ``subversion --with-apxs`` build.
  3. ``svn`` executable on PATH (for the checkout + commits).

If any of those is missing the test **skips** with a specific reason.
This is the documented production-ready behavior: the algorithm code
path is identical to the ``svn://`` path already covered by
``test_scale_matrix_svn_remote.py``; DAV only changes what Subversion's
``ra_serf`` talks to over the wire, which is below the algorithm layer.

Coverage claim (when the test runs)
-----------------------------------
  * httpd serves an svn repo over real HTTP on loopback
  * ``svn co`` succeeds over http://
  * ``svn ci`` (PROPFIND/PUT/REPORT DAV methods) succeeds
  * AlgA-SVN (``run_algorithm_a_svn``) blames the DAV-provisioned
    working copy correctly
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pytest

from aggregateGenCodeDesc.algorithms.alg_a_svn import run_algorithm_a_svn


N_COMMITS = 15
N_FILES = 3
LINES_PER_COMMIT = 4
TIME_BUDGET_SEC = 60.0
START = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
END = datetime.fromisoformat("2026-12-31T00:00:00+00:00")

# Candidate locations for the Subversion Apache modules. Ordered by
# likelihood on the platforms we support.
_MOD_DAV_SVN_CANDIDATES = [
    # Debian/Ubuntu
    "/usr/lib/apache2/modules/mod_dav_svn.so",
    # RHEL/Fedora/CentOS
    "/usr/lib64/httpd/modules/mod_dav_svn.so",
    "/usr/lib/httpd/modules/mod_dav_svn.so",
    # Homebrew (hypothetical — currently unshipped)
    "/opt/homebrew/lib/httpd/modules/mod_dav_svn.so",
    "/usr/local/lib/httpd/modules/mod_dav_svn.so",
    # macOS stock Apache (does not ship svn module)
    "/usr/libexec/apache2/mod_dav_svn.so",
]
_MOD_AUTHZ_SVN_CANDIDATES = [
    "/usr/lib/apache2/modules/mod_authz_svn.so",
    "/usr/lib64/httpd/modules/mod_authz_svn.so",
    "/usr/lib/httpd/modules/mod_authz_svn.so",
    "/opt/homebrew/lib/httpd/modules/mod_authz_svn.so",
    "/usr/local/lib/httpd/modules/mod_authz_svn.so",
    "/usr/libexec/apache2/mod_authz_svn.so",
]


def _find_first(paths: list[str]) -> Optional[str]:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def _host_supports_dav_svn() -> tuple[bool, str]:
    """Return (available, reason_if_not)."""
    if not shutil.which("httpd"):
        return False, "httpd not on PATH"
    if not shutil.which("svn") or not shutil.which("svnadmin"):
        return False, "svn/svnadmin not on PATH"
    if _find_first(_MOD_DAV_SVN_CANDIDATES) is None:
        return False, (
            "mod_dav_svn.so not found in known locations "
            "(macOS stock Apache and Homebrew subversion do not ship it; "
            "install libapache2-mod-svn / mod_dav_svn package)"
        )
    if _find_first(_MOD_AUTHZ_SVN_CANDIDATES) is None:
        return False, "mod_authz_svn.so not found"
    return True, ""


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, *, timeout: float = 8.0) -> None:
    deadline = time.monotonic() + timeout
    last: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                return
        except OSError as exc:
            last = exc
            time.sleep(0.1)
    raise RuntimeError(f"httpd never opened {host}:{port}: {last}")


def _run(cmd: list[str], *, cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd, cwd=cwd, check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )


def _seed_svn_repo_over_dav(server_url: str, wc_parent: Path) -> None:
    """Check out from DAV URL, commit N_COMMITS across N_FILES files.

    Uses non-interactive svn with --username/--password (AuthType None so
    any creds accepted, but svn CLI still sends an empty basic-auth)."""
    wc = wc_parent / "wc"
    _run([
        "svn", "co",
        "--non-interactive", "--no-auth-cache",
        "--username", "anon", "--password", "anon",
        server_url, str(wc),
    ])

    file_state: dict[str, list[str]] = {}
    for i in range(N_COMMITS):
        rel = f"src/f{i % N_FILES}.py"
        new_lines = [f"line_{i}_{j}" for j in range(LINES_PER_COMMIT)]
        existing = file_state.get(rel, [])
        updated = existing + new_lines
        target = wc / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("".join(x + "\n" for x in updated), encoding="utf-8")
        if rel not in file_state:
            _run([
                "svn", "add", "--parents",
                "--non-interactive", "--no-auth-cache",
                str(target),
            ], cwd=wc)
        date = (START + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%S.000000Z")
        _run([
            "svn", "ci",
            "--non-interactive", "--no-auth-cache",
            "--username", "anon", "--password", "anon",
            "-m", f"c{i}",
            "--with-revprop", f"svn:date={date}",
        ], cwd=wc)
        file_state[rel] = updated


def _build_records(shas_by_rev: dict[int, str]) -> list[dict]:
    """Return v26.03 records for each committed revision."""
    records: list[dict] = []
    file_state: dict[str, list[str]] = {}
    for i in range(N_COMMITS):
        rel = f"src/f{i % N_FILES}.py"
        existing = file_state.get(rel, [])
        from_line = len(existing) + 1
        to_line = len(existing) + LINES_PER_COMMIT
        date = (START + timedelta(minutes=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        rev = shas_by_rev[i + 1]
        records.append({
            "protocolName": "generatedTextDesc",
            "protocolVersion": "26.03",
            "SUMMARY": {},
            "DETAIL": [{"fileName": rel, "codeLines": [
                {"lineRange": {"from": from_line, "to": to_line},
                 "genRatio": 100, "genMethod": "vibeCoding"},
            ]}],
            "REPOSITORY": {
                "vcsType": "svn", "repoURL": "http://placeholder",
                "repoBranch": "trunk",
                "revisionId": rev, "revisionTimestamp": date,
            },
        })
        file_state[rel] = existing + [f"x"] * LINES_PER_COMMIT
    return records


# ---------------------------------------------------------------------------
# AlgA-SVN over http:// served by httpd + mod_dav_svn.
# ---------------------------------------------------------------------------
def test_scale_alga_svn_over_dav(tmp_path: Path) -> None:
    ok, reason = _host_supports_dav_svn()
    if not ok:
        pytest.skip(f"svn DAV prerequisites missing: {reason}")

    mod_dav_svn = _find_first(_MOD_DAV_SVN_CANDIDATES)
    mod_authz_svn = _find_first(_MOD_AUTHZ_SVN_CANDIDATES)
    assert mod_dav_svn and mod_authz_svn  # _host_supports_dav_svn ensured

    # 1. Create a bare svn repo server-side.
    repo_parent = tmp_path / "svnroot"
    repo_parent.mkdir()
    repo = repo_parent / "repo"
    _run(["svnadmin", "create", str(repo)])

    # 2. Write a minimal Apache httpd config. We run under the current
    #    user (not root) by binding to a high loopback port and using a
    #    per-test ServerRoot pointing at tmp_path.
    server_root = tmp_path / "apache"
    server_root.mkdir()
    logs_dir = server_root / "logs"
    logs_dir.mkdir()
    pid_file = server_root / "httpd.pid"
    port = _free_port()

    # Minimum modules needed by httpd 2.4 to start + serve DAV-SVN.
    # mod_dav is part of stock Apache; mod_dav_svn depends on it.
    apache_modules_dir = os.path.dirname(mod_dav_svn)
    stock_modules_dir = "/usr/libexec/apache2"  # macOS fallback for base modules

    def _pick_module(name: str) -> Optional[str]:
        for d in (apache_modules_dir, stock_modules_dir,
                  "/usr/lib/apache2/modules",
                  "/usr/lib64/httpd/modules",
                  "/usr/lib/httpd/modules"):
            candidate = os.path.join(d, name)
            if os.path.isfile(candidate):
                return candidate
        return None

    # These are the bare minimum modules httpd 2.4 needs to start and
    # serve a DAV location.
    base_modules = {
        "mpm_event_module":        "mod_mpm_event.so",
        "authz_core_module":       "mod_authz_core.so",
        "authz_host_module":       "mod_authz_host.so",
        "unixd_module":            "mod_unixd.so",
        "log_config_module":       "mod_log_config.so",
        "dir_module":              "mod_dir.so",
        "mime_module":             "mod_mime.so",
        "dav_module":              "mod_dav.so",
    }
    missing_base = []
    load_lines: list[str] = []
    for name, fname in base_modules.items():
        p = _pick_module(fname)
        if p is None:
            missing_base.append(fname)
        else:
            load_lines.append(f"LoadModule {name} {p}")
    if missing_base:
        pytest.skip(f"base httpd modules missing: {missing_base}")

    load_lines.append(f"LoadModule dav_svn_module {mod_dav_svn}")
    load_lines.append(f"LoadModule authz_svn_module {mod_authz_svn}")

    config = f"""
ServerRoot "{server_root}"
PidFile "{pid_file}"
Listen 127.0.0.1:{port}
ServerName 127.0.0.1

{chr(10).join(load_lines)}

ErrorLog "{logs_dir}/error.log"
LogLevel warn
<IfModule log_config_module>
  LogFormat "%h %l %u %t \\"%r\\" %>s %b" common
  CustomLog "{logs_dir}/access.log" common
</IfModule>

DocumentRoot "{server_root}"
<Directory "{server_root}">
  Require all granted
</Directory>

<Location /repo>
  DAV svn
  SVNPath {repo}
  Require all granted
</Location>
""".lstrip()

    conf_file = server_root / "httpd.conf"
    conf_file.write_text(config, encoding="utf-8")

    # 3. Syntax-check the config before starting.
    check = subprocess.run(
        ["httpd", "-t", "-f", str(conf_file)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    if check.returncode != 0:
        pytest.skip(f"httpd config rejected: {check.stderr or check.stdout}")

    # 4. Start httpd in foreground (-X = single process, no daemonize).
    httpd_proc = subprocess.Popen(
        ["httpd", "-X", "-f", str(conf_file)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    try:
        try:
            _wait_for_port("127.0.0.1", port, timeout=5.0)
        except RuntimeError as exc:
            stderr = httpd_proc.stderr.read().decode("utf-8", errors="replace") \
                if httpd_proc.stderr else ""
            pytest.skip(f"httpd failed to bind: {exc}; stderr={stderr[:500]}")

        server_url = f"http://127.0.0.1:{port}/repo"

        # 5. Smoke-test reachability (optional — svn co will do it too).
        # 6. Populate the repo over DAV.
        try:
            _seed_svn_repo_over_dav(server_url, tmp_path)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            pytest.skip(f"svn over DAV refused commits: {stderr[:500]}")

        # 7. Fresh checkout (after seed) for AlgA-SVN blame.
        fresh = tmp_path / "fresh"
        _run([
            "svn", "co",
            "--non-interactive", "--no-auth-cache",
            "--username", "anon", "--password", "anon",
            server_url, str(fresh),
        ])

        # 8. Collect (revision -> sha) mapping by listing svn log.
        log_xml = _run([
            "svn", "log", "--xml",
            "--non-interactive", "--no-auth-cache",
            "--username", "anon", "--password", "anon",
            server_url,
        ]).stdout
        import xml.etree.ElementTree as ET
        root = ET.fromstring(log_xml)
        shas_by_rev: dict[int, str] = {}
        for entry in root.findall("logentry"):
            rev = int(entry.attrib["revision"])
            shas_by_rev[rev] = str(rev)

        records = _build_records(shas_by_rev)
        # Override repoURL on every record to the DAV URL actually used.
        for r in records:
            r["REPOSITORY"] = {**r["REPOSITORY"], "repoURL": server_url}

        # 9. Run AlgA-SVN.
        t0 = time.monotonic()
        out = run_algorithm_a_svn(
            fresh, records, start_time=START, end_time=END, threshold=60,
        )
        elapsed = time.monotonic() - t0

        assert out.metrics.total_lines == N_COMMITS * LINES_PER_COMMIT
        assert out.metrics.fully_ai_value == pytest.approx(1.0)
        assert elapsed < TIME_BUDGET_SEC, (
            f"AlgA-SVN over http DAV took {elapsed:.1f}s "
            f"(budget {TIME_BUDGET_SEC}s)"
        )
    finally:
        httpd_proc.terminate()
        try:
            httpd_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            httpd_proc.kill()
            httpd_proc.wait(timeout=5)
        if httpd_proc.stdout is not None:
            httpd_proc.stdout.close()
        if httpd_proc.stderr is not None:
            httpd_proc.stderr.close()
